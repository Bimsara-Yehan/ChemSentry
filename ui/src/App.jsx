import React, { useEffect, useRef, useState } from 'react';
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
  Zone_A: 'Zone A — Solvent Storage',
  Zone_B: 'Zone B — Acid & Base Storage',
  Zone_C: 'Zone C — Oxidizer Storage',
};

function formatSecondsAgo(sinceDate, nowMs) {
  if (!sinceDate) return null;
  const seconds = Math.max(0, Math.round((nowMs - sinceDate.getTime()) / 1000));
  if (seconds < 1) return 'just now';
  if (seconds === 1) return '1s ago';
  return `${seconds}s ago`;
}

// Mirrors the backend RBAC gates in api/main.py: viewer is read-only on every
// mutating route (telemetry, query, sign-off); analyst adds telemetry + query;
// only admin can sign off an alert (require_role(UserRole.ADMIN)).
const ROLE_INFO = {
  viewer: {
    label: 'Read-only access',
    detail: 'You can monitor zones and alerts. Submitting readings, running queries, and signing off alerts require an analyst or admin account.',
  },
  analyst: {
    label: 'Analyst access',
    detail: 'You can submit telemetry readings and query retrieved safety data. Alert sign-off requires an admin account.',
  },
  admin: {
    label: 'Admin access',
    detail: 'Full access, including approving or rejecting alerts.',
  },
};

function LoginScreen({ onLogin, loading, error }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onLogin(username, password);
  };

  return (
    <div
      style={{
        minHeight: '80vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div className="card" style={{ maxWidth: '380px', width: '100%' }}>
        <div className="card-title" style={{ marginBottom: '4px' }}>
          Sign in to ChemSentry
        </div>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '18px' }}>
          Enter your credentials to access the monitoring dashboard.
        </p>
        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}
        >
          <input
            className="input-field"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="input-field"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button type="submit" className="action-btn" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        {error && (
          <div className="provenance-box is-error" style={{ marginTop: '16px' }}>
            <div className="provenance-title">Sign-in failed</div>
            {error}
          </div>
        )}
        <p className="help-text">
          Demo accounts — viewer_user / viewer123 · analyst_user / analyst123 ·
          admin_user / admin123
        </p>
      </div>
    </div>
  );
}

function App() {
  const [token, setToken] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  const [activeTab, setActiveTab] = useState('live');
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
  const [newAlertNotice, setNewAlertNotice] = useState(null);

  const refreshAlerts = async (authToken) => {
    try {
      const list = await listAlerts(authToken);

      if (knownAlertIds.current !== null) {
        const newOnes = list.filter((a) => !knownAlertIds.current.has(a.alert_id));
        if (newOnes.length > 0 && activeTabRef.current !== 'supervisor') {
          const newest = newOnes[0];
          setNewAlertNotice(
            newOnes.length === 1
              ? `New alert: ${newest.chemical_name} excursion in ${newest.zone_id}`
              : `${newOnes.length} new alerts, most recent: ${newest.chemical_name} in ${newest.zone_id}`
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
      const res = await getAuditLog(authToken, 25, offset);
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
    if (activeTab !== 'live') return undefined;
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
      setUserCreateSuccess(`User '${res.username}' (${res.role}) created successfully.`);
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
      setZoneManageSuccess(`Zone '${newZoneId}' created successfully.`);
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
      setZoneManageSuccess(`Chemical '${addChemName}' added to ${selectedZoneForChem}.`);
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
      setZoneManageSuccess(`Chemical '${chemName}' removed from ${zoneId}.`);
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
      setUploadSuccess(`SDS '${res.document_id}' for '${res.chemical_name}' uploaded & indexed.`);
      setUploadFile(null);
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
      <div className="app-container">
        <header className="app-header">
          <div className="brand-section">
            <div className="brand-logo">CS</div>
            <div className="brand-title">
              <h1>ChemSentry</h1>
              <p>Chemical Safety Monitoring</p>
            </div>
          </div>
        </header>
        <LoginScreen onLogin={handleLogin} loading={loginLoading} error={loginError} />
      </div>
    );
  }

  const currentZoneData = zones[activeZone];
  const demoTemps = DEMO_TEMPERATURES[activeZone] || { safe: 20.0, excursion: 40.0 };
  const pendingAlertCount = alerts.filter((a) => a.status === 'pending_review').length;
  const isViewer = currentUser?.role === 'viewer';
  const isAdmin = currentUser?.role === 'admin';

  return (
    <div className="app-container">
      {/* App Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">CS</div>
          <div className="brand-title">
            <h1>ChemSentry</h1>
            <p>Chemical Safety Monitoring</p>
          </div>
        </div>
        <div className="header-status">
          <div
            className={`status-badge${
              health && health.status !== 'ok' ? ` is-${health.status === 'down' ? 'down' : 'degraded'}` : ''
            }`}
            title={
              health && health.status !== 'ok'
                ? `database: ${health.database ?? 'unknown'} · mqtt_broker: ${health.mqtt_broker ?? 'unknown'}`
                : undefined
            }
          >
            <span className="pulse-dot"></span>
            {!health
              ? 'Checking…'
              : health.status === 'ok'
              ? 'System Online'
              : health.status === 'degraded'
              ? 'Degraded'
              : 'Unreachable'}
          </div>
          <div className="user-chip">
            <span>
              <strong>{currentUser?.username}</strong>
            </span>
            <span className="role-tag">{currentUser?.role}</span>
            <button className="logout-btn" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="nav-tabs">
        <button
          className={`tab-btn ${activeTab === 'live' ? 'active' : ''}`}
          onClick={() => setActiveTab('live')}
        >
          Live Environment
        </button>
        <button
          className={`tab-btn ${activeTab === 'reconciliation' ? 'active' : ''}`}
          onClick={() => setActiveTab('reconciliation')}
        >
          Retrieval &amp; Reconciliation
        </button>
        <button
          className={`tab-btn ${activeTab === 'supervisor' ? 'active' : ''}`}
          onClick={() => setActiveTab('supervisor')}
        >
          Sign-Off Queue
          {pendingAlertCount > 0 && <span className="tab-count">{pendingAlertCount}</span>}
        </button>
        {isAdmin && (
          <>
            <button
              className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('users');
                refreshUsers(token);
              }}
            >
              User Management
            </button>
            <button
              className={`tab-btn ${activeTab === 'zones' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('zones');
                refreshZones(token);
              }}
            >
              Zone Inventory
            </button>
            <button
              className={`tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
              onClick={() => {
                setActiveTab('audit');
                refreshAuditLogs(token, 0);
              }}
            >
              Audit Trail
            </button>
          </>
        )}
      </nav>

      <div className={`role-banner role-banner-${currentUser?.role}`}>
        <span className="role-banner-label">{ROLE_INFO[currentUser?.role]?.label}</span>
        <span className="role-banner-detail">{ROLE_INFO[currentUser?.role]?.detail}</span>
      </div>

      {newAlertNotice && (
        <div className="new-alert-toast">
          <span className="state-badge state-WARNING">New</span>
          <span>{newAlertNotice}</span>
          <button
            className="new-alert-toast-view"
            onClick={() => setActiveTab('supervisor')}
          >
            View
          </button>
          <button
            className="new-alert-toast-dismiss"
            aria-label="Dismiss"
            onClick={() => setNewAlertNotice(null)}
          >
            ×
          </button>
        </div>
      )}

      {/* Tab 1: Live Environment View */}
      {activeTab === 'live' && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  Zone Telemetry
                  <span className="status-badge" style={{ marginLeft: '10px' }}>
                    <span className="pulse-dot"></span>
                    Live
                  </span>
                  {zonesLastUpdated && (
                    <span
                      style={{
                        marginLeft: '8px',
                        fontSize: '12px',
                        color: 'var(--text-dim)',
                        fontWeight: 400,
                      }}
                    >
                      updated {formatSecondsAgo(zonesLastUpdated, nowTick)}
                    </span>
                  )}
                </div>
                <div className="zone-selector">
                  {Object.keys(ZONE_LABELS).map((z) => (
                    <button
                      key={z}
                      className={`zone-chip ${activeZone === z ? 'active' : ''}`}
                      onClick={() => setActiveZone(z)}
                    >
                      {z.replace('_', ' ')}
                    </button>
                  ))}
                </div>
              </div>

              {zonesError && (
                <div className="provenance-box is-error">
                  <div className="provenance-title">Failed to load zone data</div>
                  {zonesError}
                </div>
              )}

              {currentZoneData ? (
                <>
                  <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                    {ZONE_LABELS[activeZone] || activeZone}
                  </h2>
                  <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '18px' }}>
                    Latest reading from this zone's sensor feed
                  </p>

                  <div className="metrics-row">
                    <div
                      className={`metric-box ${currentZoneData.is_excursion ? 'warning' : ''}`}
                    >
                      <div className="metric-label">Temperature</div>
                      <div className="metric-value">
                        {currentZoneData.last_reading.temperature_celsius}{' '}
                        <span className="metric-unit">°C</span>
                      </div>
                      <div className="metric-subtext">
                        <span className={`state-badge state-${currentZoneData.safety_state}`}>
                          {currentZoneData.safety_state}
                        </span>
                      </div>
                    </div>

                    <div className="metric-box">
                      <div className="metric-label">Relative Humidity</div>
                      <div className="metric-value">
                        {currentZoneData.last_reading.humidity_percent}{' '}
                        <span className="metric-unit">%</span>
                      </div>
                      <div className="metric-subtext">Not evaluated — no threshold retrieved</div>
                    </div>
                  </div>

                  {currentZoneData.checks.map((check, idx) => (
                    <div
                      className={`provenance-box ${check.state === 'WARNING' ? 'is-warning' : ''}`}
                      key={idx}
                    >
                      <div className="provenance-title">
                        {check.chemical_name} — {check.metric_name}{' '}
                        <span className={`state-badge state-${check.state}`}>{check.state}</span>
                      </div>
                      {check.reasoning}
                    </div>
                  ))}
                </>
              ) : (
                <p className="loading-state">
                  <span className="loading-spinner"></span>
                  Loading zone data…
                </p>
              )}
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                Chemicals Stored in This Zone
              </div>
              <div className="inventory-list">
                {(currentZoneData?.chemicals || []).map((chem, idx) => (
                  <div key={idx} className="inventory-item">
                    <span className="chem-tag">{chem}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '10px' }}>
                Send a Test Reading
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Submits a live reading to this zone and shows the resulting safety
                evaluation, retrieved and cited in real time.
              </p>
              <button
                className="action-btn btn-warning"
                style={{ width: '100%', marginBottom: '10px' }}
                onClick={() => handleSendReading(demoTemps.excursion)}
                disabled={isViewer || telemetryLoading}
              >
                Send Excursion Reading ({demoTemps.excursion} °C)
              </button>
              <button
                className="action-btn btn-secondary"
                style={{ width: '100%' }}
                onClick={() => handleSendReading(demoTemps.safe)}
                disabled={isViewer || telemetryLoading}
              >
                Send Normal Reading ({demoTemps.safe} °C)
              </button>
              {isViewer && (
                <p className="help-text">
                  Viewer role is read-only; sign in as analyst or admin to submit telemetry.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: SDS Retrieval & Reconciliation View */}
      {activeTab === 'reconciliation' && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '4px' }}>
                Search Retrieved Safety Data
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Look up a chemical to see its retrieved thresholds, citations, and any
                conflicts between supplier documents.
              </p>
              <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="Enter chemical name (e.g. Ethanol, Sodium hydroxide)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  disabled={isViewer}
                />
                <button type="submit" className="action-btn" disabled={isViewer || queryLoading}>
                  {queryLoading ? 'Searching…' : 'Search'}
                </button>
              </form>
              {isViewer && (
                <p className="help-text">
                  Viewer role cannot query — sign in as analyst or admin.
                </p>
              )}
            </div>

            {queryError && (
              <div className="card">
                <div className="provenance-box is-error">
                  <div className="provenance-title">Query failed</div>
                  {queryError}
                </div>
              </div>
            )}

            {queryResult && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    Results for{' '}
                    <span style={{ color: 'var(--accent)' }}>
                      {queryResult.query.chemical_name}
                    </span>
                  </div>
                  <span className={`state-badge state-${queryResult.evidence.final_safety_state}`}>
                    {queryResult.evidence.final_safety_state}
                  </span>
                </div>

                <h4 style={{ marginBottom: '12px', fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)' }}>
                  Retrieved thresholds
                </h4>
                {queryResult.evidence.thresholds.length === 0 && (
                  <p style={{ color: 'var(--text-dim)', fontSize: '13px', marginBottom: '4px' }}>
                    No thresholds resolved for this chemical name in the current corpus.
                  </p>
                )}
                {queryResult.evidence.thresholds.map((t, idx) => (
                  <div key={idx} className="inventory-item" style={{ marginBottom: '8px' }}>
                    <div>
                      <strong>{t.parameter}</strong>:{' '}
                      <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>
                        {t.value} {t.unit}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                      Citation: {t.version}
                    </div>
                  </div>
                ))}

                {queryResult.evidence.conflicts.map((conflict, idx) => (
                  <div key={idx} className="provenance-box is-warning">
                    <div className="provenance-title">Supplier conflict detected</div>
                    {conflict}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                How This Works
              </div>
              <ul
                style={{
                  fontSize: '13px',
                  color: 'var(--text-muted)',
                  lineHeight: '1.8',
                  paddingLeft: '16px',
                }}
              >
                <li><strong>Inverted index:</strong> positional word mapping (Lab 03)</li>
                <li><strong>Tolerant matching:</strong> k-grams + Levenshtein (Lab 04)</li>
                <li><strong>Ranking:</strong> TF-IDF cosine similarity (Lab 05)</li>
                <li><strong>Reconciliation:</strong> Jaccard conflict filter (Lab 06A)</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Supervisor Sign-Off Dashboard */}
      {activeTab === 'supervisor' && (
        <div className="card">
          <div className="card-header">
            <div className="card-title">Alert Review &amp; Sign-Off</div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Every WARNING alert requires admin sign-off before it's final
            </span>
          </div>

          {alertsError && (
            <div className="provenance-box is-error">
              <div className="provenance-title">Failed to load alerts</div>
              {alertsError}
            </div>
          )}

          <div className="inventory-list">
            {!alertsLoaded && !alertsError && (
              <p className="loading-state">
                <span className="loading-spinner"></span>
                Loading alerts…
              </p>
            )}
            {alertsLoaded && alerts.length === 0 && !alertsError && (
              <p className="empty-state">No alerts recorded yet.</p>
            )}
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className="card"
                style={{ background: 'var(--bg-subtle)', marginBottom: '16px' }}
              >
                <div className="card-header">
                  <div>
                    <span className="role-tag" style={{ marginRight: '10px' }}>
                      {alert.alert_id}
                    </span>
                    <strong style={{ fontSize: '15px' }}>
                      {alert.chemical_name} excursion in {alert.zone_id}
                    </strong>
                  </div>
                  <span
                    style={{
                      fontSize: '12.5px',
                      fontWeight: 600,
                      color:
                        alert.status === 'approved'
                          ? 'var(--green-safe)'
                          : alert.status === 'rejected'
                          ? 'var(--red-danger)'
                          : 'var(--amber-warning)',
                    }}
                  >
                    {alert.status.replace('_', ' ').toUpperCase()}
                  </span>
                </div>

                <div className="metrics-row" style={{ marginTop: '4px' }}>
                  <div className="metric-box warning">
                    <div className="metric-label">Observed Value</div>
                    <div className="metric-value" style={{ fontSize: '22px' }}>
                      {alert.current_value} {alert.unit}
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-label">Retrieved Threshold</div>
                    <div className="metric-value" style={{ fontSize: '22px' }}>
                      {alert.threshold_value != null ? `${alert.threshold_value} ${alert.unit}` : '—'}
                    </div>
                  </div>
                </div>

                <div className="provenance-box is-warning">
                  <div className="provenance-title">Reasoning</div>
                  {alert.reasoning}
                </div>

                {alert.status === 'pending_review' ? (
                  isAdmin ? (
                    <div
                      style={{
                        marginTop: '16px',
                        display: 'flex',
                        gap: '12px',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                      }}
                    >
                      <input
                        type="text"
                        className="input-field"
                        placeholder="Add sign-off notes..."
                        value={signOffNote}
                        onChange={(e) => setSignOffNote(e.target.value)}
                        style={{ flex: 1, minWidth: '160px' }}
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
                  <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--text-muted)' }}>
                    <strong>Sign-off notes:</strong> {alert.notes} (by {alert.signed_by})
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: User Management (ADMIN only) */}
      {activeTab === 'users' && isAdmin && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-header">
                <div className="card-title">User Accounts Directory</div>
                <button
                  className="demo-chip"
                  onClick={() => refreshUsers(token)}
                >
                  Refresh Directory
                </button>
              </div>

              {usersError && (
                <div className="provenance-box is-error">
                  <div className="provenance-title">Error loading users</div>
                  {usersError}
                </div>
              )}

              <div className="inventory-list" style={{ marginTop: '16px' }}>
                {!usersLoaded && !usersError && (
                  <p className="loading-state">
                    <span className="loading-spinner"></span>
                    Loading users…
                  </p>
                )}
                {usersLoaded && users.length === 0 && !usersError && (
                  <p className="empty-state">No DB-backed user accounts registered yet. Demo accounts (viewer_user, analyst_user, admin_user) are active via fallback.</p>
                )}
                {users.map((u) => (
                  <div key={u.user_id} className="inventory-item">
                    <div>
                      <strong style={{ fontSize: '15px', color: 'var(--text-main)' }}>
                        {u.username}
                      </strong>
                      <span className="role-tag" style={{ marginLeft: '10px' }}>
                        {u.role.toUpperCase()}
                      </span>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                        ID: {u.user_id} • Created: {new Date(u.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    <span
                      style={{
                        padding: '3px 8px',
                        borderRadius: '4px',
                        fontSize: '11px',
                        fontWeight: 600,
                        backgroundColor: u.is_active ? 'var(--green-tint)' : 'var(--red-tint)',
                        color: u.is_active ? 'var(--green-safe)' : 'var(--red-danger)',
                        border: `1px solid ${u.is_active ? 'var(--green-border)' : 'var(--red-border)'}`,
                      }}
                    >
                      {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                Register New User
              </div>

              <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Username
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. jsmith"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Password
                  </label>
                  <input
                    type="password"
                    className="input-field"
                    placeholder="••••••••"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Role Assignment
                  </label>
                  <select
                    className="input-field"
                    value={newUserRole}
                    onChange={(e) => setNewUserRole(e.target.value)}
                  >
                    <option value="viewer">Viewer (Read-only)</option>
                    <option value="analyst">Analyst (Telemetry &amp; Queries)</option>
                    <option value="admin">Admin (Full Control &amp; Sign-offs)</option>
                  </select>
                </div>

                <button type="submit" className="action-btn" style={{ marginTop: '8px' }}>
                  Create Account
                </button>
              </form>

              {userCreateSuccess && (
                <div className="provenance-box" style={{ marginTop: '16px', borderColor: 'var(--green-border)', background: 'var(--green-tint)', color: 'var(--green-safe)' }}>
                  <div className="provenance-title">Success</div>
                  {userCreateSuccess}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: Zone Inventory Management (ADMIN only) */}
      {activeTab === 'zones' && isAdmin && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-header">
                <div className="card-title">Zone Chemical Inventories</div>
                <button className="demo-chip" onClick={() => refreshZones(token)}>
                  Refresh Zones
                </button>
              </div>

              {zoneManageSuccess && (
                <div className="provenance-box" style={{ marginBottom: '16px', borderColor: 'var(--green-border)', background: 'var(--green-tint)', color: 'var(--green-safe)' }}>
                  <div className="provenance-title">Success</div>
                  {zoneManageSuccess}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
                {Object.entries(zones).map(([zId, zData]) => (
                  <div key={zId} className="card" style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-color)' }}>
                    <div className="card-header">
                      <div>
                        <strong style={{ fontSize: '15px', color: 'var(--text-main)' }}>
                          {zId}
                        </strong>
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '8px' }}>
                          ({(zData.chemicals || []).length} chemicals)
                        </span>
                      </div>
                    </div>

                    <div className="inventory-list" style={{ marginTop: '10px' }}>
                      {(zData.chemicals || []).map((chem) => (
                        <div key={chem} className="inventory-item">
                          <span style={{ fontWeight: 500 }}>{chem}</span>
                          <button
                            className="logout-btn"
                            style={{ color: 'var(--red-danger)', borderColor: 'var(--red-border)' }}
                            onClick={() => handleRemoveChemical(zId, chem)}
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="side-content" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                Add Chemical to Zone
              </div>

              <form onSubmit={handleAddChemical} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Target Zone
                  </label>
                  <select
                    className="input-field"
                    value={selectedZoneForChem}
                    onChange={(e) => setSelectedZoneForChem(e.target.value)}
                  >
                    {Object.keys(zones).map((zId) => (
                      <option key={zId} value={zId}>
                        {zId}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Chemical Name
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Isopropanol"
                    value={addChemName}
                    onChange={(e) => setAddChemName(e.target.value)}
                    required
                  />
                </div>

                <button type="submit" className="action-btn">
                  Add to Inventory
                </button>
              </form>
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                Create Monitored Zone
              </div>

              <form onSubmit={handleCreateZone} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Zone ID
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Zone_D"
                    value={newZoneId}
                    onChange={(e) => setNewZoneId(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Initial Chemicals (Comma-separated)
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="e.g. Acetone, Methanol"
                    value={newZoneChems}
                    onChange={(e) => setNewZoneChems(e.target.value)}
                  />
                </div>

                <button type="submit" className="action-btn">
                  Create Zone
                </button>
              </form>
            </div>
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                Upload New SDS Document
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '12px' }}>
                Upload an SDS PDF to extract safety thresholds &amp; index into corpus dynamically.
              </p>

              <form onSubmit={handleUploadSds} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Select SDS PDF
                  </label>
                  <input
                    type="file"
                    accept=".pdf"
                    className="input-field"
                    onChange={(e) => setUploadFile(e.target.files[0] || null)}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Chemical Name (Optional override)
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Auto-detected if blank"
                    value={uploadChemName}
                    onChange={(e) => setUploadChemName(e.target.value)}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                    Supplier (Optional override)
                  </label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Auto-detected if blank"
                    value={uploadSupplier}
                    onChange={(e) => setUploadSupplier(e.target.value)}
                  />
                </div>

                <button type="submit" className="action-btn" disabled={uploadLoading}>
                  {uploadLoading ? 'Uploading & Indexing…' : 'Upload SDS PDF'}
                </button>
              </form>

              {uploadSuccess && (
                <div className="provenance-box" style={{ marginTop: '12px', borderColor: 'var(--green-border)', background: 'var(--green-tint)', color: 'var(--green-safe)' }}>
                  <div className="provenance-title">Success</div>
                  {uploadSuccess}
                </div>
              )}

              {uploadError && (
                <div className="provenance-box is-error" style={{ marginTop: '12px' }}>
                  <div className="provenance-title">Upload Failed</div>
                  {uploadError}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 6: Compliance Audit Trail (ADMIN only) */}
      {activeTab === 'audit' && isAdmin && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">System Audit Trail</div>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Security log of system actions and sign-offs (Total entries: {auditTotal}).
              </p>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className="demo-chip"
                disabled={auditOffset === 0}
                onClick={() => refreshAuditLogs(token, Math.max(0, auditOffset - 25))}
              >
                Previous
              </button>
              <button
                className="demo-chip"
                disabled={auditOffset + 25 >= auditTotal}
                onClick={() => refreshAuditLogs(token, auditOffset + 25)}
              >
                Next
              </button>
            </div>
          </div>

          {auditError && (
            <div className="provenance-box is-error">
              <div className="provenance-title">Failed to load audit logs</div>
              {auditError}
            </div>
          )}

          <div className="inventory-list" style={{ marginTop: '16px' }}>
            {!auditLoaded && !auditError && (
              <p className="loading-state">
                <span className="loading-spinner"></span>
                Loading audit log…
              </p>
            )}
            {auditLoaded && auditLogs.length === 0 && !auditError && (
              <p className="empty-state">No audit log entries recorded yet.</p>
            )}
            {auditLogs.map((log) => (
              <div key={log.id} className="inventory-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="role-tag" style={{ fontSize: '11px' }}>
                      #{log.id}
                    </span>
                    <strong style={{ fontSize: '14px', color: 'var(--text-main)' }}>
                      {log.action}
                    </strong>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      by {log.user_id}
                    </span>
                  </div>
                  <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                    {new Date(log.timestamp).toLocaleString()}
                  </span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  <strong>Resource:</strong> {log.resource || 'N/A'}
                  {log.details && (
                    <span style={{ marginLeft: '12px' }}>
                      <strong>Details:</strong> {typeof log.details === 'object' ? JSON.stringify(log.details) : log.details}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

