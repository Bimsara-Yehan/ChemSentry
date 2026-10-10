import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, MotionConfig, motion } from 'motion/react';
import { Activity, Bell, ClipboardCheck, LogOut, ScrollText, Search, Users, Warehouse, X } from 'lucide-react';
import './index.css';
import { getHealth, getMe, listAlerts, listZones, login as apiLogin, onUnauthorized, submitZoneTelemetry } from './api';
import LoginScreen from './components/LoginScreen';
import MoleculeField from './components/MoleculeField';
import { useNow } from './components/hooks';
import { ROLE_LABELS, zoneName } from './constants';
import { clearSession, loadTab, loadToken, saveTab, saveToken } from './session';
import { AuditView, UsersView, ZonesView } from './views/AdminViews';
import LiveView from './views/LiveView';
import SearchView from './views/SearchView';
import SignoffView from './views/SignoffView';

function HealthPill({ health }) {
  const tone = !health ? 'checking' : health.status === 'ok' ? 'ok' : health.status === 'down' ? 'down' : 'degraded';
  const label = { checking: 'Checking…', ok: 'All systems nominal', degraded: 'Degraded', down: 'Unreachable' }[tone];
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

function Clock({ now }) {
  const d = new Date(now);
  return (
    <span className="clock" aria-label="Current time">
      {d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
    </span>
  );
}

function App() {
  // Restore a saved session synchronously so the very first render already
  // knows whether to show the "restoring" state instead of a login flash.
  const [token, setToken] = useState(() => loadToken());
  const [currentUser, setCurrentUser] = useState(null);
  const [restoring, setRestoring] = useState(() => Boolean(loadToken()));
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  const [activeTab, setActiveTab] = useState(() => loadTab('live'));
  const [newAlertNotice, setNewAlertNotice] = useState(null);
  const activeTabRef = useRef(activeTab);

  // null until the zone list arrives; the first zone the API reports is
  // selected by default rather than an assumed zone ID.
  const [activeZone, setActiveZone] = useState(null);
  const [zones, setZones] = useState({});
  const [zonesError, setZonesError] = useState('');
  const [zonesLastUpdated, setZonesLastUpdated] = useState(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);

  const [alerts, setAlerts] = useState([]);
  const [alertsError, setAlertsError] = useState('');
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const knownAlertIds = useRef(null);

  const [health, setHealth] = useState(null);
  const now = useNow(Boolean(token));

  const handleLogout = useCallback(() => {
    clearSession();
    setToken(null);
    setCurrentUser(null);
    setZones({});
    setAlerts([]);
    setAlertsLoaded(false);
    knownAlertIds.current = null;
    setActiveTab('live');
    setRestoring(false);
  }, []);

  // Any 401 from the API means the stored session is dead -- sign out cleanly.
  useEffect(() => {
    onUnauthorized(() => {
      setLoginError('Your session has expired. Please sign in again.');
      handleLogout();
    });
    return () => onUnauthorized(null);
  }, [handleLogout]);

  // Page refresh: re-validate the stored token with the server before
  // trusting it, then drop straight back into the app.
  useEffect(() => {
    if (!token || currentUser) return;
    let cancelled = false;
    getMe(token)
      .then((user) => {
        if (!cancelled) setCurrentUser(user);
      })
      .catch(() => {
        if (!cancelled) handleLogout();
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, currentUser, handleLogout]);

  useEffect(() => {
    activeTabRef.current = activeTab;
    saveTab(activeTab);
    if (activeTab === 'supervisor') setNewAlertNotice(null);
  }, [activeTab]);

  useEffect(() => {
    if (!newAlertNotice) return undefined;
    const t = setTimeout(() => setNewAlertNotice(null), 8000);
    return () => clearTimeout(t);
  }, [newAlertNotice]);

  const refreshZones = useCallback(async (authToken) => {
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
  }, []);

  const refreshAlerts = useCallback(async (authToken) => {
    try {
      const list = await listAlerts(authToken);
      if (knownAlertIds.current !== null) {
        const fresh = list.filter((a) => !knownAlertIds.current.has(a.alert_id));
        if (fresh.length > 0 && activeTabRef.current !== 'supervisor') {
          const newest = fresh[0];
          setNewAlertNotice(
            fresh.length === 1
              ? `${newest.chemical_name} exceeded its limit in ${zoneName(newest.zone_id)}`
              : `${fresh.length} new alerts · latest: ${newest.chemical_name}, ${zoneName(newest.zone_id)}`
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
  }, []);

  const handleLogin = async (username, password) => {
    setLoginLoading(true);
    setLoginError('');
    try {
      const { access_token } = await apiLogin(username, password);
      const user = await getMe(access_token);
      saveToken(access_token);
      setToken(access_token);
      setCurrentUser(user);
    } catch (err) {
      setLoginError(err.message);
    } finally {
      setLoginLoading(false);
    }
  };

  const ready = Boolean(token && currentUser);

  // Zone polling while on a tab that shows zone data. 5s matches the ESP32's
  // publish interval, so a real reading never waits more than one cycle.
  useEffect(() => {
    if (!ready || (activeTab !== 'live' && activeTab !== 'zones' && activeTab !== 'reconciliation')) return undefined;
    refreshZones(token);
    const i = setInterval(() => refreshZones(token), 5000);
    return () => clearInterval(i);
  }, [ready, token, activeTab, refreshZones]);

  // Alerts poll on every tab -- spotting a new alert while elsewhere is what
  // drives the toast notification.
  useEffect(() => {
    if (!ready) return undefined;
    refreshAlerts(token);
    const i = setInterval(() => refreshAlerts(token), 5000);
    return () => clearInterval(i);
  }, [ready, token, refreshAlerts]);

  useEffect(() => {
    if (!ready) return undefined;
    const check = () =>
      getHealth()
        .then(setHealth)
        .catch(() => setHealth({ status: 'down' }));
    check();
    const i = setInterval(check, 10000);
    return () => clearInterval(i);
  }, [ready]);

  const handleSendReading = async (zoneId, temperatureCelsius, humidityPercent) => {
    setTelemetryLoading(true);
    try {
      await submitZoneTelemetry(token, zoneId, {
        zone_id: zoneId,
        temperature_celsius: temperatureCelsius,
        humidity_percent: humidityPercent,
        timestamp: new Date().toISOString(),
        device_id: 'ui-demo-control',
      });
      await Promise.all([refreshZones(token), refreshAlerts(token)]);
    } catch (err) {
      setZonesError(err.message);
    } finally {
      setTelemetryLoading(false);
    }
  };

  if (!ready) {
    return (
      <MotionConfig reducedMotion="user">
        <LoginScreen onLogin={handleLogin} loading={loginLoading} error={loginError} restoring={restoring} />
      </MotionConfig>
    );
  }

  const isViewer = currentUser.role === 'viewer';
  const isAdmin = currentUser.role === 'admin';
  const zoneIds = Object.keys(zones).sort();
  const currentZone = zones[activeZone] ? activeZone : zoneIds[0] ?? null;
  const pending = alerts.filter((a) => a.status === 'pending_review').length;
  const allChemicals = [...new Set(Object.values(zones).flatMap((z) => z.chemicals || []))];

  const tabs = [
    { id: 'live', label: 'Live environment', icon: Activity, group: 'Operations' },
    { id: 'reconciliation', label: 'SDS search', icon: Search, group: 'Operations' },
    { id: 'supervisor', label: 'Sign-off queue', icon: ClipboardCheck, count: pending, group: 'Operations' },
    ...(isAdmin
      ? [
          { id: 'users', label: 'Users', icon: Users, group: 'Administration' },
          { id: 'zones', label: 'Zones & documents', icon: Warehouse, group: 'Administration' },
          { id: 'audit', label: 'Audit trail', icon: ScrollText, group: 'Administration' },
        ]
      : []),
  ];
  // A non-admin restoring a saved admin tab (or a stale tab id) lands on Live.
  const currentTab = tabs.some((t) => t.id === activeTab) ? activeTab : 'live';
  const groups = [...new Set(tabs.map((t) => t.group))];

  return (
    <MotionConfig reducedMotion="user">
      <div className="app-shell">
        <MoleculeField density={0.3} className="app-field" />

        <aside className="sidebar">
          <div className="brand-lockup">
            <span className="brand-hex">
              <span>Cs</span>
            </span>
            <span className="brand-name">ChemSentry</span>
          </div>

          <nav className="side-nav" aria-label="Sections">
            {groups.map((g) => (
              <div key={g} className="side-group">
                <span className="side-group-label">{g}</span>
                {tabs
                  .filter((t) => t.group === g)
                  .map((tab) => {
                    const Icon = tab.icon;
                    const active = currentTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        className={`side-link${active ? ' active' : ''}`}
                        onClick={() => setActiveTab(tab.id)}
                        aria-current={active ? 'page' : undefined}
                        aria-label={tab.label}
                        title={tab.label}
                      >
                        {active && (
                          <motion.span layoutId="side-active" className="side-link-bg" transition={{ type: 'spring', stiffness: 400, damping: 34 }} />
                        )}
                        <Icon size={17} aria-hidden="true" />
                        <span className="side-link-label">{tab.label}</span>
                        <AnimatePresence>
                          {tab.count > 0 && (
                            <motion.span
                              key={tab.count}
                              className="side-count"
                              initial={{ scale: 0.4, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              exit={{ scale: 0.4, opacity: 0 }}
                            >
                              {tab.count}
                            </motion.span>
                          )}
                        </AnimatePresence>
                      </button>
                    );
                  })}
              </div>
            ))}
          </nav>

          <div className="side-footer">
            <div className="user-chip">
              <span className={`avatar role-${currentUser.role}`} aria-hidden="true">
                {(currentUser.username || '?').charAt(0).toUpperCase()}
              </span>
              <span className="user-meta">
                <strong>{currentUser.username}</strong>
                <span>{ROLE_LABELS[currentUser.role] || currentUser.role}</span>
              </span>
              <button className="icon-btn" onClick={handleLogout} title="Sign out" aria-label="Sign out">
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </aside>

        <div className="workspace">
          <header className="topbar">
            <div className="topbar-left">
              <span className="topbar-site">Storage facility · {zoneIds.length} zone{zoneIds.length === 1 ? '' : 's'}</span>
            </div>
            <div className="topbar-right">
              <HealthPill health={health} />
              <Clock now={now} />
            </div>
          </header>

          <AnimatePresence>
            {newAlertNotice && (
              <motion.div
                className="toast"
                role="status"
                initial={{ opacity: 0, y: -16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -16, scale: 0.96 }}
                transition={{ type: 'spring', stiffness: 300, damping: 24 }}
              >
                <span className="toast-icon">
                  <Bell size={16} />
                </span>
                <div className="toast-body">
                  <div className="toast-title">New WARNING raised</div>
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
            {/* Entrance-only transition: the new page mounts immediately. An
                exit-then-enter ("wait") transition would block navigation
                whenever the browser pauses animation frames (hidden tab). */}
            <motion.div
                key={currentTab}
                // No `filter: blur` here: a filter on an ancestor disables the
                // cards' backdrop-filter glass effect and is costly to repaint.
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
              >
                {currentTab === 'live' && (
                  <LiveView
                    token={token}
                    zones={zones}
                    zoneIds={zoneIds}
                    activeZone={currentZone}
                    setActiveZone={setActiveZone}
                    zonesError={zonesError}
                    zonesLastUpdated={zonesLastUpdated}
                    now={now}
                    isViewer={isViewer}
                    telemetryLoading={telemetryLoading}
                    onSendReading={handleSendReading}
                  />
                )}
                {currentTab === 'reconciliation' && (
                  <SearchView token={token} isViewer={isViewer} suggestions={allChemicals} />
                )}
                {currentTab === 'supervisor' && (
                  <SignoffView
                    token={token}
                    alerts={alerts}
                    alertsLoaded={alertsLoaded}
                    alertsError={alertsError}
                    setAlertsError={setAlertsError}
                    isAdmin={isAdmin}
                    now={now}
                    refreshAlerts={() => refreshAlerts(token)}
                  />
                )}
                {currentTab === 'users' && isAdmin && <UsersView token={token} />}
                {currentTab === 'zones' && isAdmin && (
                  <ZonesView token={token} zones={zones} refreshZones={() => refreshZones(token)} />
                )}
                {currentTab === 'audit' && isAdmin && <AuditView token={token} />}
              </motion.div>
          </main>
        </div>
      </div>
    </MotionConfig>
  );
}

export default App;
