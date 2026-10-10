import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, MotionConfig, motion } from 'motion/react';
import {
  Activity,
  Bell,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Droplets,
  FileText,
  FlaskConical,
  GitMerge,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  ScrollText,
  Search,
  ShieldCheck,
  Thermometer,
  TriangleAlert,
  Upload,
  Users,
  Warehouse,
  X,
} from 'lucide-react';
import './index.css';
import {
  addChemicalToZone,
  createZone,
  createUser,
  getAuditLog,
  getHealth,
  getMe,
  listAlerts,
  listUsers,
  listZones,
  login as apiLogin,
  queryChemical,
  removeChemicalFromZone,
  signOffAlert,
  submitZoneTelemetry,
  uploadSdsDocument,
} from './api';
import LoginScreen from './components/LoginScreen';
import StorageLimitsTable from './components/StorageLimitsTable';
import { EmptyState, Field, Loading, Notice, PageHeader, SourceCell, StateBadge } from './components/ui';
import {
  citationLabel,
  formatDateTime,
  formatValue,
  humanizeAction,
  humanizeMetric,
  timeAgo,
} from './format';

// Demo reading profiles per zone -- NOT a hardcoded safety threshold (the
// deterministic safety layer never sees these, only the resulting
// temperature reading). Verified against the real corpus while building
// Agent C (agents/agent_c_environment/zone_inventory.py): Hydrogen peroxide
// solution (Zone_C) is the only chemical anywhere in this corpus with a
// real extracted numeric storage-temperature range (2-8 C) -- so only
// Zone_C can ever produce a genuine SAFE/WARNING distinction from real
// evidence. Zone_A/B's chemicals have no such field in their real SDS at
// all and will honestly stay UNKNOWN regardless of the reading sent.
const DEMO_TEMPERATURES = {
  Zone_A: { safe: 20.0, excursion: 40.0 },
  Zone_B: { safe: 20.0, excursion: 40.0 },
  Zone_C: { safe: 5.0, excursion: 15.0 },
};

const ZONE_LABELS = {
  Zone_A: 'Solvent storage',
  Zone_B: 'Acid & base storage',
  Zone_C: 'Oxidizer storage',
};

const ROLE_LABELS = { viewer: 'Viewer', analyst: 'Analyst', admin: 'Admin' };

const ALERT_FILTERS = [
  { id: 'pending_review', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'all', label: 'All' },
];

const ALERT_PAGE_SIZE = 20;
const AUDIT_PAGE_SIZE = 25;

function zoneName(zoneId) {
  return zoneId.replace('_', ' ');
}

const DETAIL_LABELS = { zone_id: '', chemical_name: 'Chemical', metric_name: 'Metric' };

function formatDetailValue(key, value) {
  if (value == null) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  if (key === 'zone_id') return zoneName(String(value));
  if (key === 'metric_name') return humanizeMetric(String(value));
  return String(value);
}

function formatSecondsAgo(sinceDate, nowMs) {
  if (!sinceDate) return null;
  const seconds = Math.max(0, Math.round((nowMs - sinceDate.getTime()) / 1000));
  if (seconds < 1) return 'just now';
  return `${seconds}s ago`;
}

// Alert reasoning embeds its citation as "... Source: [id] Section N - ...
// [policy_version=x]"; pull it out so the expanded row can show the source
// on its own line.
function citationFromReasoning(reasoning) {
  const m = /Source:\s*(\[.*?)(?:\s*\[policy_version=[^\]]*\])?\s*$/.exec(reasoning || '');
  return m ? m[1] : null;
}

function HealthPill({ health }) {
  const tone = !health ? 'checking' : health.status === 'ok' ? 'ok' : health.status === 'down' ? 'down' : 'degraded';
  const label = {
    checking: 'Checking…',
    ok: 'System online',
    degraded: 'Degraded',
    down: 'Unreachable',
  }[tone];
  const title =
    health && health.status !== 'ok'
      ? `database: ${health.database ?? 'unknown'} · mqtt_broker: ${health.mqtt_broker ?? 'unknown'}`
      : undefined;
  return (
    <span className={`health-pill is-${tone}`} title={title}>
      <span className="health-dot" />
      {label}
    </span>
  );
}

function Metric({ icon: Icon, label, value, unit, tone, note }) {
  return (
    <div className={`metric${tone ? ` metric-${tone}` : ''}`}>
      <div className="metric-label">
        <Icon size={14} aria-hidden="true" />
        {label}
      </div>
      <div className="metric-value">
        {value ?? '—'}
        <span className="metric-unit">{unit}</span>
      </div>
      {note && <div className="metric-note">{note}</div>}
    </div>
  );
}

function App() {
  const [token, setToken] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  const [activeTab, setActiveTab] = useState('live');
  const [newAlertNotice, setNewAlertNotice] = useState(null);
  // refreshAlerts is called from a setInterval closure set up once per
  // effect run -- reading `activeTab` directly there would see whatever
  // value was current when that closure was created, not the live one. The
  // ref sidesteps that without needing to tear down and restart the polling
  // interval on every tab switch.
  const activeTabRef = useRef('live');
  useEffect(() => {
    activeTabRef.current = activeTab;
    if (activeTab === 'supervisor') setNewAlertNotice(null);
  }, [activeTab]);

  useEffect(() => {
    if (!newAlertNotice) return undefined;
    const timeout = setTimeout(() => setNewAlertNotice(null), 8000);
    return () => clearTimeout(timeout);
  }, [newAlertNotice]);
  const [activeZone, setActiveZone] = useState('Zone_A');

  const [zones, setZones] = useState({});
  const [zonesError, setZonesError] = useState('');
  const [telemetryLoading, setTelemetryLoading] = useState(false);

  const [searchQuery, setSearchQuery] = useState('Ethanol');
  const [queryResult, setQueryResult] = useState(null);
  const [queryError, setQueryError] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);

  const [alerts, setAlerts] = useState([]);
  const [alertsError, setAlertsError] = useState('');
  const [signOffNote, setSignOffNote] = useState('');
  const [alertFilter, setAlertFilter] = useState('pending_review');
  const [alertLimit, setAlertLimit] = useState(ALERT_PAGE_SIZE);
  const [expandedAlertId, setExpandedAlertId] = useState(null);

  // Admin User Management State
  const [users, setUsers] = useState([]);
  const [usersError, setUsersError] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newUserRole, setNewUserRole] = useState('analyst');
  const [userCreateSuccess, setUserCreateSuccess] = useState('');

  // Admin Zone Management State
  const [newZoneId, setNewZoneId] = useState('');
  const [newZoneChems, setNewZoneChems] = useState('');
  const [addChemName, setAddChemName] = useState('');
  const [selectedZoneForChem, setSelectedZoneForChem] = useState('Zone_A');
  const [zoneManageSuccess, setZoneManageSuccess] = useState('');

  // Admin Audit Log State
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);
  const [auditError, setAuditError] = useState('');

  // SDS Upload State
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadChemName, setUploadChemName] = useState('');
  const [uploadSupplier, setUploadSupplier] = useState('');
  const [uploadSuccess, setUploadSuccess] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [uploadLoading, setUploadLoading] = useState(false);
  const fileInputRef = useRef(null);

  // Header health badge -- real GET /health, not a hardcoded label.
  const [health, setHealth] = useState(null);

  // "Live" badge is meaningless without this -- polling every 5s but never
  // showing when data last actually arrived means a silently-stalled poll
  // still claims to be live. zonesLastUpdated records real fetch success;
  // nowTick just forces a re-render each second so the "Xs ago" text counts
  // up smoothly instead of only moving in 5s jumps.
  const [zonesLastUpdated, setZonesLastUpdated] = useState(null);
  const [nowTick, setNowTick] = useState(() => Date.now());

  const refreshZones = async (authToken) => {
    try {
      const zoneList = await listZones(authToken);
      const byId = {};
      for (const z of zoneList) byId[z.zone_id] = z;
      setZones(byId);
      setZonesError('');
      setZonesLastUpdated(new Date());
    } catch (err) {
      setZonesError(err.message);
    }
  };

  // *Loaded flags are "has a fetch ever succeeded", not "is a fetch in
  // flight" -- alerts polls every 5s, and the point is to show a loading
  // state only before the first real result, not flicker one in on every
  // subsequent poll cycle.
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [auditLoaded, setAuditLoaded] = useState(false);

  // Polling updates `alerts` silently every 5s -- without this, a new
  // WARNING arriving while you're on another tab just appears next time you
  // happen to look at the Sign-Off Queue. knownAlertIds is a ref (not state)
  // so comparing against it never itself triggers a re-render; it only
  // matters at the moment a new fetch resolves.
  const knownAlertIds = useRef(null);

  const refreshAlerts = async (authToken) => {
    try {
      const list = await listAlerts(authToken);

      if (knownAlertIds.current !== null) {
        const newOnes = list.filter((a) => !knownAlertIds.current.has(a.alert_id));
        if (newOnes.length > 0 && activeTabRef.current !== 'supervisor') {
          const newest = newOnes[0];
          setNewAlertNotice(
            newOnes.length === 1
              ? `${newest.chemical_name} exceeded its limit in ${zoneName(newest.zone_id)}`
              : `${newOnes.length} new alerts · latest: ${newest.chemical_name}, ${zoneName(newest.zone_id)}`
          );
        }
      }
      knownAlertIds.current = new Set(list.map((a) => a.alert_id));

      setAlerts(list);
      setAlertsError('');
      setAlertsLoaded(true);
    } catch (err) {
      setAlertsError(err.message);
    }
  };

  const refreshUsers = async (authToken) => {
    try {
      const list = await listUsers(authToken);
      setUsers(list || []);
      setUsersError('');
      setUsersLoaded(true);
    } catch (err) {
      setUsersError(err.message);
    }
  };

  const refreshAuditLogs = async (authToken, offset = 0) => {
    try {
      const res = await getAuditLog(authToken, AUDIT_PAGE_SIZE, offset);
      setAuditLogs(res?.entries || []);
      setAuditTotal(res?.total || 0);
      setAuditOffset(offset);
      setAuditError('');
      setAuditLoaded(true);
    } catch (err) {
      setAuditError(err.message);
    }
  };

  const handleLogin = async (username, password) => {
    setLoginLoading(true);
    setLoginError('');
    try {
      const { access_token } = await apiLogin(username, password);
      const user = await getMe(access_token);
      setToken(access_token);
      setCurrentUser(user);
      await refreshZones(access_token);
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setCurrentUser(null);
    setZones({});
    setAlerts([]);
    setActiveTab('live');
  };

  // Poll while a tab is actually visible, rather than push/WebSocket -- there's
  // no server-side push infrastructure here, and 5s (matching the ESP32's own
  // publish interval) is frequent enough that a real reading never waits more
  // than one cycle to appear, without hammering the API when nobody's looking.
  useEffect(() => {
    if (!token || activeTab !== 'live') return undefined;
    refreshZones(token);
    const interval = setInterval(() => refreshZones(token), 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeTab]);

  useEffect(() => {
    if (activeTab !== 'live' && activeTab !== 'supervisor') return undefined;
    const tick = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [activeTab]);

  // Alerts poll regardless of which tab is active -- unlike zone telemetry,
  // detecting a new alert while the viewer is on a DIFFERENT tab (to surface
  // the notification below) is the whole point of this effect, so it can't
  // be gated to only run while already on the Sign-Off Queue tab.
  useEffect(() => {
    if (!token) return undefined;
    refreshAlerts(token);
    const interval = setInterval(() => refreshAlerts(token), 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Header badge is always visible regardless of tab, so this polls
  // independently of the tab-scoped effects above. 10s (not 5s like the
  // zone/alert polling) -- broker/DB reachability doesn't change as often as
  // a sensor reading, and this check isn't tied to anything time-critical.
  useEffect(() => {
    if (!token) return undefined;
    const check = () =>
      getHealth()
        .then(setHealth)
        .catch(() => setHealth({ status: 'down' }));
    check();
    const interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, [token]);

  const handleSendReading = async (temperatureCelsius) => {
    setTelemetryLoading(true);
    try {
      await submitZoneTelemetry(token, activeZone, {
        zone_id: activeZone,
        temperature_celsius: temperatureCelsius,
        humidity_percent: 45.0,
        timestamp: new Date().toISOString(),
        device_id: 'ui-demo-control',
      });
      await refreshZones(token);
      setZonesError('');
    } catch (err) {
      setZonesError(err.message);
    } finally {
      setTelemetryLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    setQueryLoading(true);
    setQueryError('');
    try {
      const result = await queryChemical(token, searchQuery);
      setQueryResult(result);
    } catch (err) {
      setQueryError(err.message);
      setQueryResult(null);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleSignOff = async (alertId, approved) => {
    try {
      await signOffAlert(token, alertId, approved, signOffNote);
      setSignOffNote('');
      setExpandedAlertId(null);
      await refreshAlerts(token);
    } catch (err) {
      setAlertsError(err.message);
    }
  };

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setUserCreateSuccess('');
    setUsersError('');
    try {
      const res = await createUser(token, newUsername, newPassword, newUserRole);
      setUserCreateSuccess(`${res.username} was added as ${ROLE_LABELS[res.role] || res.role}.`);
      setNewUsername('');
      setNewPassword('');
      await refreshUsers(token);
    } catch (err) {
      setUsersError(err.message);
    }
  };

  const handleCreateZone = async (e) => {
    e.preventDefault();
    setZoneManageSuccess('');
    setZonesError('');
    try {
      const chems = newZoneChems.split(',').map((c) => c.trim()).filter(Boolean);
      await createZone(token, newZoneId, chems);
      setZoneManageSuccess(`${zoneName(newZoneId)} created.`);
      setNewZoneId('');
      setNewZoneChems('');
      await refreshZones(token);
    } catch (err) {
      setZonesError(err.message);
    }
  };

  const handleAddChemical = async (e) => {
    e.preventDefault();
    if (!selectedZoneForChem) return;
    setZoneManageSuccess('');
    setZonesError('');
    try {
      await addChemicalToZone(token, selectedZoneForChem, addChemName);
      setZoneManageSuccess(`${addChemName} added to ${zoneName(selectedZoneForChem)}.`);
      setAddChemName('');
      await refreshZones(token);
    } catch (err) {
      setZonesError(err.message);
    }
  };

  const handleRemoveChemical = async (zoneId, chemName) => {
    setZoneManageSuccess('');
    setZonesError('');
    try {
      await removeChemicalFromZone(token, zoneId, chemName);
      setZoneManageSuccess(`${chemName} removed from ${zoneName(zoneId)}.`);
      await refreshZones(token);
    } catch (err) {
      setZonesError(err.message);
    }
  };

  const handleUploadSds = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadLoading(true);
    setUploadSuccess('');
    setUploadError('');
    try {
      const res = await uploadSdsDocument(token, uploadFile, uploadChemName, uploadSupplier);
      setUploadSuccess(`${res.chemical_name} (SDS ${res.document_id}) indexed.`);
      setUploadFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setUploadChemName('');
      setUploadSupplier('');
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploadLoading(false);
    }
  };

  if (!token) {
    return (
      <MotionConfig reducedMotion="user">
        <LoginScreen onLogin={handleLogin} loading={loginLoading} error={loginError} />
      </MotionConfig>
    );
  }

  const zoneIds = [...new Set([...Object.keys(ZONE_LABELS), ...Object.keys(zones)])];
  const currentZoneData = zones[activeZone];
  const demoTemps = DEMO_TEMPERATURES[activeZone] || { safe: 20.0, excursion: 40.0 };
  const isViewer = currentUser?.role === 'viewer';
  const isAdmin = currentUser?.role === 'admin';

  const alertCounts = {
    pending_review: alerts.filter((a) => a.status === 'pending_review').length,
    approved: alerts.filter((a) => a.status === 'approved').length,
    rejected: alerts.filter((a) => a.status === 'rejected').length,
    all: alerts.length,
  };
  const filteredAlerts =
    alertFilter === 'all' ? alerts : alerts.filter((a) => a.status === alertFilter);
  const visibleAlerts = filteredAlerts.slice(0, alertLimit);

  const unknownChemicals = currentZoneData
    ? currentZoneData.chemicals.filter((chem) => {
        const own = currentZoneData.checks.filter((c) => c.chemical_name === chem);
        return own.length === 0 || own.every((c) => c.threshold_value == null);
      })
    : [];

  const tabs = [
    { id: 'live', label: 'Live environment', icon: Activity },
    { id: 'reconciliation', label: 'SDS search', icon: Search },
    { id: 'supervisor', label: 'Sign-off queue', icon: ClipboardCheck, count: alertCounts.pending_review },
    ...(isAdmin
      ? [
          { id: 'users', label: 'Users', icon: Users, onOpen: () => refreshUsers(token) },
          { id: 'zones', label: 'Zones & documents', icon: Warehouse, onOpen: () => refreshZones(token) },
          { id: 'audit', label: 'Audit trail', icon: ScrollText, onOpen: () => refreshAuditLogs(token, 0) },
        ]
      : []),
  ];

  const openTab = (tab) => {
    setActiveTab(tab.id);
    tab.onOpen?.();
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell">
        <header className="topbar">
          <div className="topbar-inner">
            <div className="topbar-row">
              <div className="brand">
                <span className="brand-mark">
                  <FlaskConical size={16} strokeWidth={2.2} />
                </span>
                <span className="brand-name">ChemSentry</span>
              </div>
              <div className="topbar-right">
                <HealthPill health={health} />
                <div className="user-menu">
                  <span className="avatar" aria-hidden="true">
                    {(currentUser?.username || '?').charAt(0).toUpperCase()}
                  </span>
                  <span className="user-meta">
                    <strong>{currentUser?.username}</strong>
                    <span>{ROLE_LABELS[currentUser?.role] || currentUser?.role}</span>
                  </span>
                  <button className="icon-btn" onClick={handleLogout} title="Log out" aria-label="Log out">
                    <LogOut size={16} />
                  </button>
                </div>
              </div>
            </div>

            <nav className="nav-tabs" aria-label="Sections">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const active = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    className={`tab-btn${active ? ' active' : ''}`}
                    onClick={() => openTab(tab)}
                    aria-current={active ? 'page' : undefined}
                  >
                    <Icon size={15} aria-hidden="true" />
                    {tab.label}
                    {tab.count > 0 && <span className="tab-count">{tab.count}</span>}
                    {active && <motion.span layoutId="tab-underline" className="tab-underline" />}
                  </button>
                );
              })}
            </nav>
          </div>
        </header>

        <AnimatePresence>
          {newAlertNotice && (
            <motion.div
              className="toast"
              role="status"
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12, scale: 0.98 }}
              transition={{ duration: 0.2 }}
            >
              <span className="toast-icon">
                <Bell size={16} />
              </span>
              <div className="toast-body">
                <div className="toast-title">New alert</div>
                <div>{newAlertNotice}</div>
              </div>
              <button className="toast-action" onClick={() => setActiveTab('supervisor')}>
                Review
              </button>
              <button className="icon-btn" aria-label="Dismiss" onClick={() => setNewAlertNotice(null)}>
                <X size={15} />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <main className="page">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            {activeTab === 'live' && (
              <>
                <PageHeader
                  title="Live environment"
                  subtitle="Current readings and storage-limit checks for each zone."
                />

                <div className="zone-switcher" role="tablist" aria-label="Zones">
                  {zoneIds.map((z) => {
                    const state = zones[z]?.safety_state;
                    return (
                      <button
                        key={z}
                        role="tab"
                        aria-selected={activeZone === z}
                        className={`zone-card${activeZone === z ? ' active' : ''}`}
                        onClick={() => setActiveZone(z)}
                      >
                        <span className="zone-card-text">
                          <span className="zone-card-name">{zoneName(z)}</span>
                          <span className="zone-card-label">{ZONE_LABELS[z] || 'Custom zone'}</span>
                        </span>
                        {state && <span className={`zone-dot zone-dot-${state}`} title={state} />}
                      </button>
                    );
                  })}
                </div>

                {zonesError && (
                  <Notice tone="error" icon={TriangleAlert} title="Couldn't load zone data">
                    {zonesError}
                  </Notice>
                )}

                <div className="dashboard-grid">
                  <div className="main-col">
                    <div className="card">
                      {currentZoneData ? (
                        <>
                          <div className="card-head">
                            <div>
                              <div className="eyebrow">{zoneName(activeZone)}</div>
                              <h3 className="card-heading">{ZONE_LABELS[activeZone] || 'Custom zone'}</h3>
                            </div>
                            <div className="card-head-right">
                              {zonesLastUpdated && (
                                <span className="live-indicator">
                                  <span className="live-dot" />
                                  Updated {formatSecondsAgo(zonesLastUpdated, nowTick)}
                                </span>
                              )}
                              <StateBadge state={currentZoneData.safety_state} size="lg" />
                            </div>
                          </div>

                          <div className="metrics-row">
                            <Metric
                              icon={Thermometer}
                              label="Temperature"
                              value={currentZoneData.last_reading.temperature_celsius}
                              unit="°C"
                              tone={currentZoneData.is_excursion ? 'warning' : undefined}
                            />
                            <Metric
                              icon={Droplets}
                              label="Humidity"
                              value={currentZoneData.last_reading.humidity_percent}
                              unit="%"
                              note="Not evaluated — no limit retrieved"
                            />
                          </div>

                          {currentZoneData.safety_state === 'UNKNOWN' && unknownChemicals.length > 0 && (
                            <Notice tone="neutral" icon={FileText}>
                              {unknownChemicals.length === currentZoneData.chemicals.length
                                ? `None of the ${unknownChemicals.length} chemicals here has a storage limit in its SDS`
                                : `${unknownChemicals.length} of ${currentZoneData.chemicals.length} chemicals here have no storage limit in their SDS`}
                              , so the zone stays UNKNOWN rather than being assumed safe.
                            </Notice>
                          )}

                          <div className="section-title">Storage limits</div>
                          <StorageLimitsTable
                            chemicals={currentZoneData.chemicals || []}
                            checks={currentZoneData.checks || []}
                          />
                        </>
                      ) : (
                        !zonesError && <Loading label="Loading zone data…" />
                      )}
                    </div>
                  </div>

                  <div className="side-col">
                    <div className="card">
                      <h3 className="card-heading">Sensor simulator</h3>
                      <p className="card-sub">Send a test reading to {zoneName(activeZone)}.</p>
                      <div className="stack-sm">
                        <button
                          className="action-btn btn-warning btn-block"
                          onClick={() => handleSendReading(demoTemps.excursion)}
                          disabled={isViewer || telemetryLoading}
                        >
                          <Thermometer size={15} />
                          Excursion · {demoTemps.excursion} °C
                        </button>
                        <button
                          className="action-btn btn-secondary btn-block"
                          onClick={() => handleSendReading(demoTemps.safe)}
                          disabled={isViewer || telemetryLoading}
                        >
                          Normal · {demoTemps.safe} °C
                        </button>
                      </div>
                      {isViewer && <p className="help-text">Your role is read-only.</p>}
                    </div>

                    <div className="card">
                      <h3 className="card-heading">Status key</h3>
                      <ul className="legend">
                        <li>
                          <StateBadge state="SAFE" size="sm" />
                          <span>Within every retrieved limit</span>
                        </li>
                        <li>
                          <StateBadge state="WARNING" size="sm" />
                          <span>A retrieved limit is exceeded</span>
                        </li>
                        <li>
                          <StateBadge state="UNKNOWN" size="sm" />
                          <span>No limit on file — never assumed safe</span>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'reconciliation' && (
              <>
                <PageHeader
                  title="SDS search"
                  subtitle="Look up a chemical's retrieved storage limits and their sources."
                />
                <div className="dashboard-grid">
                  <div className="main-col">
                    <div className="card">
                      <form onSubmit={handleSearch} className="search-bar">
                        <span className="input-with-icon">
                          <Search size={16} aria-hidden="true" />
                          <input
                            type="text"
                            className="input-field"
                            placeholder="Chemical name, e.g. Ethanol"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            disabled={isViewer}
                            aria-label="Chemical name"
                          />
                        </span>
                        <button type="submit" className="action-btn" disabled={isViewer || queryLoading}>
                          {queryLoading ? <LoaderCircle size={15} className="spin" /> : null}
                          Search
                        </button>
                      </form>
                      {isViewer && <p className="help-text">Search requires an analyst or admin role.</p>}
                    </div>

                    {queryError && (
                      <Notice tone="error" icon={TriangleAlert} title="Search failed">
                        {queryError}
                      </Notice>
                    )}

                    {queryResult && (
                      <div className="card">
                        <div className="card-head">
                          <div>
                            <div className="eyebrow">Result</div>
                            <h3 className="card-heading">{queryResult.query.chemical_name}</h3>
                          </div>
                          <span className="lookup-tag" title="A search has no sensor reading, so no SAFE/WARNING verdict is made.">
                            <StateBadge state={queryResult.evidence.final_safety_state} size="sm" />
                            Lookup only
                          </span>
                        </div>

                        {queryResult.evidence.thresholds.length === 0 ? (
                          <EmptyState title="No limits found" icon={FileText}>
                            The current corpus has no storage limits for this name.
                          </EmptyState>
                        ) : (
                          <div className="table-wrap">
                            <table className="data-table">
                              <thead>
                                <tr>
                                  <th>Parameter</th>
                                  <th>Limit</th>
                                  <th>Source</th>
                                </tr>
                              </thead>
                              <tbody>
                                {queryResult.evidence.thresholds.map((t, idx) => (
                                  <tr key={idx}>
                                    <td className="cell-strong">{humanizeMetric(t.parameter)}</td>
                                    <td className="limit-value">{formatValue(t.value, t.unit)}</td>
                                    <td className="cell-source">
                                      <SourceCell citation={t.version} fallback={t.source_doc_id} />
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {queryResult.evidence.conflicts.map((conflict, idx) => (
                          <Notice key={idx} tone="warning" icon={GitMerge} title="Supplier conflict">
                            {conflict}
                          </Notice>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="side-col">
                    <div className="card">
                      <h3 className="card-heading">Retrieval pipeline</h3>
                      <ol className="pipeline">
                        <li>
                          <strong>Name matching</strong>
                          <span>Exact, fuzzy and phonetic</span>
                        </li>
                        <li>
                          <strong>Ranking</strong>
                          <span>TF-IDF relevance</span>
                        </li>
                        <li>
                          <strong>Reconciliation</strong>
                          <span>Source authority and conflict checks</span>
                        </li>
                        <li>
                          <strong>Verdict</strong>
                          <span>Deterministic rules only</span>
                        </li>
                      </ol>
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'supervisor' && (
              <>
                <PageHeader
                  title="Sign-off queue"
                  subtitle="WARNING alerts need admin approval before they are final."
                />

                <div className="segmented" role="tablist" aria-label="Filter alerts">
                  {ALERT_FILTERS.map((f) => (
                    <button
                      key={f.id}
                      role="tab"
                      aria-selected={alertFilter === f.id}
                      className={`segmented-btn${alertFilter === f.id ? ' active' : ''}`}
                      onClick={() => {
                        setAlertFilter(f.id);
                        setAlertLimit(ALERT_PAGE_SIZE);
                        setExpandedAlertId(null);
                      }}
                    >
                      {f.label}
                      <span className="segmented-count">{alertCounts[f.id]}</span>
                    </button>
                  ))}
                </div>

                {alertsError && (
                  <Notice tone="error" icon={TriangleAlert} title="Couldn't load alerts">
                    {alertsError}
                  </Notice>
                )}

                <div className="card card-flush">
                  {!alertsLoaded && !alertsError && <Loading label="Loading alerts…" />}
                  {alertsLoaded && filteredAlerts.length === 0 && !alertsError && (
                    <EmptyState title="Nothing here" icon={ShieldCheck}>
                      No {alertFilter === 'all' ? '' : ALERT_FILTERS.find((f) => f.id === alertFilter).label.toLowerCase()}{' '}
                      alerts.
                    </EmptyState>
                  )}

                  <ul className="alert-list">
                    {visibleAlerts.map((alert) => {
                      const isOpen = expandedAlertId === alert.alert_id;
                      const source = citationLabel(citationFromReasoning(alert.reasoning));
                      return (
                        <li key={alert.alert_id} className={`alert-item${isOpen ? ' is-open' : ''}`}>
                          <button
                            className="alert-row"
                            onClick={() => {
                              setExpandedAlertId(isOpen ? null : alert.alert_id);
                              setSignOffNote('');
                            }}
                            aria-expanded={isOpen}
                          >
                            <span className={`alert-icon status-${alert.status}`}>
                              <TriangleAlert size={15} />
                            </span>
                            <span className="alert-main">
                              <span className="alert-title">{alert.chemical_name}</span>
                              <span className="alert-meta">
                                {zoneName(alert.zone_id)} · {alert.alert_id} · {timeAgo(alert.created_at, nowTick)}
                              </span>
                            </span>
                            <span className="alert-values">
                              <span className="alert-observed">{formatValue(alert.current_value, alert.unit)}</span>
                              <span className="alert-limit">limit {formatValue(alert.threshold_value, alert.unit)}</span>
                            </span>
                            <span className={`status-pill status-${alert.status}`}>
                              {alert.status === 'pending_review' ? 'Pending' : alert.status}
                            </span>
                            <ChevronDown size={16} className={`chevron${isOpen ? ' rotate-180' : ''}`} />
                          </button>

                          <AnimatePresence initial={false}>
                            {isOpen && (
                              <motion.div
                                className="alert-detail"
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.2 }}
                              >
                                <div className="alert-detail-inner">
                                  <dl className="detail-grid">
                                    <div>
                                      <dt>Raised by</dt>
                                      <dd>{alert.created_by || '—'}</dd>
                                    </div>
                                    <div>
                                      <dt>Raised at</dt>
                                      <dd>{formatDateTime(alert.created_at)}</dd>
                                    </div>
                                    <div>
                                      <dt>Source</dt>
                                      <dd>{source || '—'}</dd>
                                    </div>
                                  </dl>
                                  <div className="eval-log">
                                    <div className="eval-log-line">
                                      <span>{alert.reasoning}</span>
                                    </div>
                                  </div>

                                  {alert.status === 'pending_review' ? (
                                    isAdmin ? (
                                      <div className="signoff-bar">
                                        <input
                                          type="text"
                                          className="input-field"
                                          placeholder="Sign-off note (optional)"
                                          value={signOffNote}
                                          onChange={(e) => setSignOffNote(e.target.value)}
                                        />
                                        <button className="action-btn" onClick={() => handleSignOff(alert.alert_id, true)}>
                                          Approve
                                        </button>
                                        <button
                                          className="action-btn btn-danger"
                                          onClick={() => handleSignOff(alert.alert_id, false)}
                                        >
                                          Reject
                                        </button>
                                      </div>
                                    ) : (
                                      <p className="help-text">Awaiting admin sign-off.</p>
                                    )
                                  ) : (
                                    <p className="signoff-record">
                                      <strong>
                                        {alert.status === 'approved' ? 'Approved' : 'Rejected'} by {alert.signed_by}
                                      </strong>
                                      {alert.signed_at && <> · {formatDateTime(alert.signed_at)}</>}
                                      {alert.notes && <> — “{alert.notes}”</>}
                                    </p>
                                  )}
                                </div>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </li>
                      );
                    })}
                  </ul>

                  {filteredAlerts.length > 0 && (
                    <div className="list-footer">
                      <span>
                        Showing {visibleAlerts.length} of {filteredAlerts.length}
                      </span>
                      {visibleAlerts.length < filteredAlerts.length && (
                        <button
                          className="action-btn btn-secondary btn-sm"
                          onClick={() => setAlertLimit((n) => n + ALERT_PAGE_SIZE)}
                        >
                          Show more
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}

            {activeTab === 'users' && isAdmin && (
              <>
                <PageHeader
                  title="Users"
                  subtitle="Accounts and their access level."
                  actions={
                    <button className="action-btn btn-secondary btn-sm" onClick={() => refreshUsers(token)}>
                      <RefreshCw size={14} /> Refresh
                    </button>
                  }
                />
                {usersError && (
                  <Notice tone="error" icon={TriangleAlert} title="Couldn't load users">
                    {usersError}
                  </Notice>
                )}
                <div className="dashboard-grid">
                  <div className="main-col">
                    <div className="card card-flush">
                      {!usersLoaded && !usersError && <Loading label="Loading users…" />}
                      {usersLoaded && users.length === 0 && !usersError && (
                        <EmptyState title="No accounts yet" icon={Users}>
                          Built-in demo accounts remain available until you add your own.
                        </EmptyState>
                      )}
                      {users.length > 0 && (
                        <div className="table-wrap">
                          <table className="data-table">
                            <thead>
                              <tr>
                                <th>User</th>
                                <th>Role</th>
                                <th>Status</th>
                                <th>Created</th>
                              </tr>
                            </thead>
                            <tbody>
                              {users.map((u) => (
                                <tr key={u.user_id}>
                                  <td>
                                    <span className="user-cell">
                                      <span className="avatar avatar-sm">{u.username.charAt(0).toUpperCase()}</span>
                                      <span>
                                        <span className="cell-strong">{u.username}</span>
                                        <span className="cell-sub">{u.user_id}</span>
                                      </span>
                                    </span>
                                  </td>
                                  <td>
                                    <span className="role-tag">{ROLE_LABELS[u.role] || u.role}</span>
                                  </td>
                                  <td>
                                    <span className={`status-pill ${u.is_active ? 'status-approved' : 'status-rejected'}`}>
                                      {u.is_active ? 'Active' : 'Inactive'}
                                    </span>
                                  </td>
                                  <td className="muted">{u.created_at ? formatDateTime(u.created_at) : '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="side-col">
                    <div className="card">
                      <h3 className="card-heading">Add user</h3>
                      <form onSubmit={handleCreateUser} className="form-stack">
                        <Field label="Username">
                          <input
                            type="text"
                            className="input-field"
                            placeholder="jsmith"
                            value={newUsername}
                            onChange={(e) => setNewUsername(e.target.value)}
                            required
                          />
                        </Field>
                        <Field label="Password">
                          <input
                            type="password"
                            className="input-field"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            required
                          />
                        </Field>
                        <Field label="Role">
                          <select
                            className="input-field"
                            value={newUserRole}
                            onChange={(e) => setNewUserRole(e.target.value)}
                          >
                            <option value="viewer">Viewer — read only</option>
                            <option value="analyst">Analyst — readings and search</option>
                            <option value="admin">Admin — full access</option>
                          </select>
                        </Field>
                        <button type="submit" className="action-btn btn-block">
                          <Plus size={15} /> Create account
                        </button>
                      </form>
                      {userCreateSuccess && (
                        <Notice tone="success" icon={ShieldCheck}>
                          {userCreateSuccess}
                        </Notice>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'zones' && isAdmin && (
              <>
                <PageHeader
                  title="Zones & documents"
                  subtitle="Manage zone inventories and add SDS documents to the corpus."
                  actions={
                    <button className="action-btn btn-secondary btn-sm" onClick={() => refreshZones(token)}>
                      <RefreshCw size={14} /> Refresh
                    </button>
                  }
                />
                {zonesError && (
                  <Notice tone="error" icon={TriangleAlert} title="Something went wrong">
                    {zonesError}
                  </Notice>
                )}
                {zoneManageSuccess && (
                  <Notice tone="success" icon={ShieldCheck}>
                    {zoneManageSuccess}
                  </Notice>
                )}
                <div className="dashboard-grid">
                  <div className="main-col">
                    {Object.entries(zones).map(([zId, zData]) => (
                      <div key={zId} className="card">
                        <div className="card-head">
                          <div>
                            <div className="eyebrow">{zoneName(zId)}</div>
                            <h3 className="card-heading">{ZONE_LABELS[zId] || 'Custom zone'}</h3>
                          </div>
                          <span className="muted">
                            {(zData.chemicals || []).length} chemical{(zData.chemicals || []).length === 1 ? '' : 's'}
                          </span>
                        </div>
                        <div className="chip-list">
                          {(zData.chemicals || []).length === 0 && <span className="muted">No chemicals assigned.</span>}
                          {(zData.chemicals || []).map((chem) => (
                            <span key={chem} className="chip">
                              {chem}
                              <button
                                className="chip-remove"
                                onClick={() => handleRemoveChemical(zId, chem)}
                                aria-label={`Remove ${chem} from ${zoneName(zId)}`}
                                title="Remove"
                              >
                                <X size={13} />
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="side-col">
                    <div className="card">
                      <h3 className="card-heading">Add chemical</h3>
                      <form onSubmit={handleAddChemical} className="form-stack">
                        <Field label="Zone">
                          <select
                            className="input-field"
                            value={selectedZoneForChem}
                            onChange={(e) => setSelectedZoneForChem(e.target.value)}
                          >
                            {Object.keys(zones).map((zId) => (
                              <option key={zId} value={zId}>
                                {zoneName(zId)}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <Field label="Chemical name">
                          <input
                            type="text"
                            className="input-field"
                            placeholder="Isopropanol"
                            value={addChemName}
                            onChange={(e) => setAddChemName(e.target.value)}
                            required
                          />
                        </Field>
                        <button type="submit" className="action-btn btn-block">
                          <Plus size={15} /> Add to zone
                        </button>
                      </form>
                    </div>

                    <div className="card">
                      <h3 className="card-heading">New zone</h3>
                      <form onSubmit={handleCreateZone} className="form-stack">
                        <Field label="Zone ID">
                          <input
                            type="text"
                            className="input-field"
                            placeholder="Zone_D"
                            value={newZoneId}
                            onChange={(e) => setNewZoneId(e.target.value)}
                            required
                          />
                        </Field>
                        <Field label="Chemicals" hint="Comma-separated, optional">
                          <input
                            type="text"
                            className="input-field"
                            placeholder="Acetone, Methanol"
                            value={newZoneChems}
                            onChange={(e) => setNewZoneChems(e.target.value)}
                          />
                        </Field>
                        <button type="submit" className="action-btn btn-secondary btn-block">
                          Create zone
                        </button>
                      </form>
                    </div>

                    <div className="card">
                      <h3 className="card-heading">Upload SDS</h3>
                      <p className="card-sub">Limits are extracted and indexed on upload.</p>
                      <form onSubmit={handleUploadSds} className="form-stack">
                        <label className={`dropzone${uploadFile ? ' has-file' : ''}`}>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf,application/pdf"
                            onChange={(e) => setUploadFile(e.target.files[0] || null)}
                            required
                          />
                          <Upload size={18} aria-hidden="true" />
                          <span className="dropzone-title">{uploadFile ? uploadFile.name : 'Choose a PDF'}</span>
                          <span className="dropzone-hint">
                            {uploadFile ? `${(uploadFile.size / 1024).toFixed(0)} KB` : 'Safety Data Sheet, .pdf'}
                          </span>
                        </label>
                        <Field label="Chemical name" hint="Optional — detected from the document">
                          <input
                            type="text"
                            className="input-field"
                            value={uploadChemName}
                            onChange={(e) => setUploadChemName(e.target.value)}
                          />
                        </Field>
                        <Field label="Supplier" hint="Optional — detected from the document">
                          <input
                            type="text"
                            className="input-field"
                            value={uploadSupplier}
                            onChange={(e) => setUploadSupplier(e.target.value)}
                          />
                        </Field>
                        <button type="submit" className="action-btn btn-block" disabled={uploadLoading || !uploadFile}>
                          {uploadLoading ? (
                            <>
                              <LoaderCircle size={15} className="spin" /> Indexing
                            </>
                          ) : (
                            <>
                              <Upload size={15} /> Upload
                            </>
                          )}
                        </button>
                      </form>
                      {uploadSuccess && (
                        <Notice tone="success" icon={ShieldCheck}>
                          {uploadSuccess}
                        </Notice>
                      )}
                      {uploadError && (
                        <Notice tone="error" icon={TriangleAlert} title="Upload failed">
                          {uploadError}
                        </Notice>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {activeTab === 'audit' && isAdmin && (
              <>
                <PageHeader
                  title="Audit trail"
                  subtitle="Every system action and sign-off, newest first."
                  actions={
                    <div className="pager">
                      <span className="muted">
                        {auditTotal === 0
                          ? '0'
                          : `${auditOffset + 1}–${Math.min(auditOffset + AUDIT_PAGE_SIZE, auditTotal)}`}{' '}
                        of {auditTotal}
                      </span>
                      <button
                        className="icon-btn icon-btn-bordered"
                        disabled={auditOffset === 0}
                        onClick={() => refreshAuditLogs(token, Math.max(0, auditOffset - AUDIT_PAGE_SIZE))}
                        aria-label="Previous page"
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <button
                        className="icon-btn icon-btn-bordered"
                        disabled={auditOffset + AUDIT_PAGE_SIZE >= auditTotal}
                        onClick={() => refreshAuditLogs(token, auditOffset + AUDIT_PAGE_SIZE)}
                        aria-label="Next page"
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  }
                />
                {auditError && (
                  <Notice tone="error" icon={TriangleAlert} title="Couldn't load the audit trail">
                    {auditError}
                  </Notice>
                )}
                <div className="card card-flush">
                  {!auditLoaded && !auditError && <Loading label="Loading audit trail…" />}
                  {auditLoaded && auditLogs.length === 0 && !auditError && (
                    <EmptyState title="No entries yet" icon={ScrollText} />
                  )}
                  {auditLogs.length > 0 && (
                    <div className="table-wrap">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Action</th>
                            <th>User</th>
                            <th>Resource</th>
                            <th>Details</th>
                          </tr>
                        </thead>
                        <tbody>
                          {auditLogs.map((log) => (
                            <tr key={log.id}>
                              <td className="muted nowrap">{formatDateTime(log.timestamp)}</td>
                              <td>
                                <span className="action-tag">{humanizeAction(log.action)}</span>
                              </td>
                              <td className="nowrap">{log.user_id}</td>
                              <td className="mono">{log.resource || '—'}</td>
                              <td>
                                <div className="cell-details">
                                  {log.details && typeof log.details === 'object'
                                    ? Object.entries(log.details).map(([k, v]) => (
                                        <span key={k} className="kv">
                                          {DETAIL_LABELS[k] !== '' && (
                                            <span className="kv-key">{DETAIL_LABELS[k] || humanizeMetric(k)}</span>
                                          )}
                                          {formatDetailValue(k, v)}
                                        </span>
                                      ))
                                    : log.details}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </motion.div>
        </main>
      </div>
    </MotionConfig>
  );
}

export default App;
