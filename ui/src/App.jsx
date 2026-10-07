import React, { useEffect, useState } from 'react';
import './index.css';
import {
  getMe,
  listAlerts,
  listZones,
  login as apiLogin,
  queryChemical,
  signOffAlert,
  submitZoneTelemetry,
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

// Mirrors the backend RBAC gates in api/main.py: viewer is read-only on every
// mutating route (telemetry, query, sign-off); analyst adds telemetry + query;
// only admin can sign off an alert (require_role(UserRole.ADMIN)).
const ROLE_INFO = {
  viewer: {
    label: 'Read-only access',
    detail: 'You can monitor live zones and alerts. Submitting readings, running queries, and signing off alerts require an analyst or admin account.',
  },
  analyst: {
    label: 'Analyst access',
    detail: 'You can submit telemetry readings and query retrieved safety data. Alert sign-off requires an admin account.',
  },
  admin: {
    label: 'Admin access',
    detail: 'Full administrative access, including approving or rejecting supervisor alerts.',
  },
};

// SVG Icons helper component
const Icons = {
  Shield: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
  Activity: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  Search: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  AlertTriangle: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  CheckCircle: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  User: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  ),
  Thermometer: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z" />
    </svg>
  ),
  Droplets: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
    </svg>
  ),
  Database: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M21 19c0 1.66-4 3-9 3s-9-1.34-9-3" />
    </svg>
  ),
};

function LoginScreen({ onLogin, loading, error }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    onLogin(username, password);
  };

  const fillDemoAccount = (user, pass) => {
    setUsername(user);
    setPassword(pass);
  };

  return (
    <div
      style={{
        minHeight: '75vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
    >
      <div className="card" style={{ maxWidth: '420px', width: '100%', padding: '32px' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <div
            className="brand-logo-icon"
            style={{ width: '54px', height: '54px', margin: '0 auto 14px' }}
          >
            <Icons.Shield />
          </div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '22px', fontWeight: 700 }}>
            Sign in to ChemSentry
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginTop: '4px' }}>
            Chemical Safety &amp; Evidence Reconciliation Platform
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
              Username
            </label>
            <input
              className="input-field"
              placeholder="e.g. analyst_user"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div>
            <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
              Password
            </label>
            <input
              className="input-field"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button type="submit" className="action-btn" disabled={loading} style={{ width: '100%', marginTop: '8px', padding: '12px' }}>
            {loading ? 'Authenticating…' : 'Sign In'}
          </button>
        </form>

        {error && (
          <div className="provenance-box is-error" style={{ marginTop: '20px' }}>
            <div className="provenance-title">Sign-in failed</div>
            {error}
          </div>
        )}

        <div style={{ marginTop: '28px', borderTop: '1px solid var(--border-color)', paddingTop: '20px' }}>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '10px', textAlign: 'center' }}>
            Quick-fill demo credentials:
          </p>
          <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="demo-chip" onClick={() => fillDemoAccount('viewer_user', 'viewer123')}>
              Viewer
            </button>
            <button className="demo-chip" onClick={() => fillDemoAccount('analyst_user', 'analyst123')}>
              Analyst
            </button>
            <button className="demo-chip" onClick={() => fillDemoAccount('admin_user', 'admin123')}>
              Admin
            </button>
          </div>
        </div>
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

  const refreshZones = async (authToken) => {
    try {
      const zoneList = await listZones(authToken);
      const byId = {};
      for (const z of zoneList) byId[z.zone_id] = z;
      setZones(byId);
      setZonesError('');
    } catch (err) {
      setZonesError(err.message);
    }
  };

  const refreshAlerts = async (authToken) => {
    try {
      const list = await listAlerts(authToken);
      setAlerts(list);
      setAlertsError('');
    } catch (err) {
      setAlertsError(err.message);
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

  // Poll while a tab is actually visible
  useEffect(() => {
    if (!token || activeTab !== 'live') return undefined;
    refreshZones(token);
    const interval = setInterval(() => refreshZones(token), 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeTab]);

  useEffect(() => {
    if (!token || activeTab !== 'supervisor') return undefined;
    refreshAlerts(token);
    const interval = setInterval(() => refreshAlerts(token), 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeTab]);

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

  const handleSearch = async (e, chemicalOverride) => {
    if (e) e.preventDefault();
    const targetQuery = chemicalOverride || searchQuery;
    setQueryLoading(true);
    setQueryError('');
    try {
      const result = await queryChemical(token, targetQuery);
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

  if (!token) {
    return (
      <div className="app-container">
        <header className="app-header">
          <div className="brand-section">
            <div className="brand-logo-icon">
              <Icons.Shield />
            </div>
            <div className="brand-title">
              <h1>ChemSentry</h1>
              <p>Chemical Safety &amp; Evidence Reconciliation Platform</p>
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
      {/* Top Application Header */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo-icon">
            <Icons.Shield />
          </div>
          <div className="brand-title">
            <h1>ChemSentry</h1>
            <p>Chemical Safety &amp; Evidence Reconciliation Platform</p>
          </div>
        </div>

        <div className="header-status">
          <div className="status-badge">
            <span className="pulse-dot"></span>
            System Online
          </div>
          <div className="user-chip">
            <Icons.User />
            <span className="user-chip-name">{currentUser?.username}</span>
            <span className={`role-tag role-tag-${currentUser?.role}`}>{currentUser?.role}</span>
            <button className="logout-btn" onClick={handleLogout}>
              Sign out
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
          <Icons.Activity />
          Live Environment
        </button>
        <button
          className={`tab-btn ${activeTab === 'reconciliation' ? 'active' : ''}`}
          onClick={() => setActiveTab('reconciliation')}
        >
          <Icons.Search />
          Retrieval &amp; Reconciliation
        </button>
        <button
          className={`tab-btn ${activeTab === 'supervisor' ? 'active' : ''}`}
          onClick={() => setActiveTab('supervisor')}
        >
          <Icons.AlertTriangle />
          Sign-Off Queue
          {pendingAlertCount > 0 && <span className="tab-count">{pendingAlertCount}</span>}
        </button>
      </nav>

      {/* Role Access Banner */}
      <div className={`role-banner role-banner-${currentUser?.role}`}>
        <span className="role-banner-label">{ROLE_INFO[currentUser?.role]?.label}</span>
        <span className="role-banner-detail">{ROLE_INFO[currentUser?.role]?.detail}</span>
      </div>

      {/* Tab 1: Live Environment View */}
      {activeTab === 'live' && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  Zone Telemetry Feed
                  <span className="status-badge" style={{ fontSize: '11px', padding: '3px 10px' }}>
                    <span className="pulse-dot"></span> 5s Polling
                  </span>
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
                  <div className="provenance-title">Failed to load zone telemetry</div>
                  {zonesError}
                </div>
              )}

              {currentZoneData ? (
                <>
                  <div style={{ marginBottom: '20px' }}>
                    <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '18px', fontWeight: 600 }}>
                      {ZONE_LABELS[activeZone] || activeZone}
                    </h2>
                    <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Real-time telemetry payload from IoT node ({currentZoneData.last_reading.device_id})
                    </p>
                  </div>

                  <div className="metrics-row">
                    <div className={`metric-box ${currentZoneData.is_excursion ? 'warning' : 'safe'}`}>
                      <div className="metric-label">
                        <span>Temperature</span>
                        <Icons.Thermometer />
                      </div>
                      <div className="metric-value">
                        {currentZoneData.last_reading.temperature_celsius}
                        <span className="metric-unit">°C</span>
                      </div>
                      <div className="metric-subtext">
                        <span>Safety Verdict:</span>
                        <span className={`state-badge state-${currentZoneData.safety_state}`}>
                          {currentZoneData.safety_state}
                        </span>
                      </div>
                    </div>

                    <div className="metric-box">
                      <div className="metric-label">
                        <span>Relative Humidity</span>
                        <Icons.Droplets />
                      </div>
                      <div className="metric-value">
                        {currentZoneData.last_reading.humidity_percent}
                        <span className="metric-unit">%</span>
                      </div>
                      <div className="metric-subtext">
                        <span>No SDS threshold retrieved</span>
                      </div>
                    </div>
                  </div>

                  <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '10px', marginTop: '10px' }}>
                    Deterministic Safety Check Provenance
                  </h3>
                  {currentZoneData.checks.map((check, idx) => (
                    <div
                      className={`provenance-box ${
                        check.state === 'WARNING' ? 'is-warning' : check.state === 'SAFE' ? '' : ''
                      }`}
                      key={idx}
                    >
                      <div className="provenance-title">
                        <span>{check.chemical_name}</span> — <span>{check.metric_name}</span>
                        <span className={`state-badge state-${check.state}`} style={{ marginLeft: 'auto' }}>
                          {check.state}
                        </span>
                      </div>
                      <p style={{ marginTop: '4px' }}>{check.reasoning}</p>
                    </div>
                  ))}
                </>
              ) : (
                <p style={{ color: 'var(--text-muted)', padding: '24px 0', textAlign: 'center' }}>
                  Loading zone telemetry…
                </p>
              )}
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                <Icons.Database />
                Chemicals Inventory Stored in {activeZone.replace('_', ' ')}
              </div>
              <div className="inventory-list">
                {(currentZoneData?.chemicals || []).map((chem, idx) => (
                  <div key={idx} className="inventory-item">
                    <span className="chem-tag">
                      <Icons.Shield />
                      {chem}
                    </span>
                    <button
                      className="demo-chip"
                      onClick={() => {
                        setActiveTab('reconciliation');
                        setSearchQuery(chem);
                        handleSearch(null, chem);
                      }}
                    >
                      Search SDS Evidence
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Control Sidebar */}
          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                Telemetry Control Panel
              </div>
              <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginBottom: '18px', lineHeight: '1.6' }}>
                Simulate environmental readings to test deterministic safety evaluation in real time.
              </p>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  className="action-btn btn-warning"
                  style={{ width: '100%' }}
                  onClick={() => handleSendReading(demoTemps.excursion)}
                  disabled={isViewer || telemetryLoading}
                >
                  <Icons.AlertTriangle />
                  Send Excursion Reading ({demoTemps.excursion} °C)
                </button>
                <button
                  className="action-btn btn-secondary"
                  style={{ width: '100%' }}
                  onClick={() => handleSendReading(demoTemps.safe)}
                  disabled={isViewer || telemetryLoading}
                >
                  <Icons.CheckCircle />
                  Send Normal Reading ({demoTemps.safe} °C)
                </button>
              </div>

              {isViewer && (
                <p className="help-text" style={{ textAlign: 'center' }}>
                  🔒 Viewer role is read-only. Sign in as analyst or admin to submit readings.
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
              <div className="card-title" style={{ marginBottom: '8px' }}>
                <Icons.Search />
                Search SDS Evidence Database
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '20px' }}>
                Retrieve versioned SDS thresholds, authority citations, and Jaccard supplier conflicts.
              </p>

              <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="Enter chemical name (e.g. Ethanol, Toluene, Acetone)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  disabled={isViewer}
                  style={{ flex: 1, minWidth: '220px' }}
                />
                <button type="submit" className="action-btn" disabled={isViewer || queryLoading}>
                  {queryLoading ? 'Searching…' : 'Search SDS'}
                </button>
              </form>

              <div style={{ marginTop: '14px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Quick search:</span>
                {['Toluene', 'Ethanol', 'Acetone'].map((name) => (
                  <button
                    key={name}
                    className="demo-chip"
                    onClick={() => {
                      setSearchQuery(name);
                      handleSearch(null, name);
                    }}
                    disabled={isViewer}
                  >
                    {name}
                  </button>
                ))}
              </div>

              {isViewer && (
                <p className="help-text">
                  🔒 Viewer role cannot query — sign in as analyst or admin.
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
                    Evidence Results for{' '}
                    <span style={{ color: 'var(--accent)', marginLeft: '4px' }}>
                      {queryResult.query.chemical_name}
                    </span>
                  </div>
                  <span className={`state-badge state-${queryResult.evidence.final_safety_state}`}>
                    Safety State: {queryResult.evidence.final_safety_state}
                  </span>
                </div>

                <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '14px' }}>
                  Retrieved SDS Safety Thresholds
                </h4>

                {queryResult.evidence.thresholds.length === 0 ? (
                  <p style={{ color: 'var(--text-muted)', fontSize: '13px', padding: '12px 0' }}>
                    No thresholds resolved for this chemical in the indexed corpus.
                  </p>
                ) : (
                  <div className="inventory-list">
                    {queryResult.evidence.thresholds.map((t, idx) => (
                      <div key={idx} className="inventory-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '6px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                          <span style={{ fontWeight: 600, color: 'var(--text-main)' }}>
                            {t.parameter}
                          </span>
                          <span style={{ fontWeight: 700, color: 'var(--accent)', fontSize: '15px' }}>
                            {t.value} {t.unit}
                          </span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          <strong>Citation:</strong> {t.version} (Doc ID: {t.source_doc_id})
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {queryResult.evidence.conflicts.map((conflict, idx) => (
                  <div key={idx} className="provenance-box is-warning" style={{ marginTop: '16px' }}>
                    <div className="provenance-title">Supplier Conflict Detected</div>
                    {conflict}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Info Sidebar */}
          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '14px' }}>
                IR Pipeline Architecture
              </div>
              <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', lineHeight: '1.7' }}>
                <p style={{ marginBottom: '10px' }}>
                  ChemSentry uses classical Information Retrieval without vector databases or LLM safety decisions:
                </p>
                <ul style={{ paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <li><strong>Positional Inverted Index:</strong> Word &amp; CAS mapping</li>
                  <li><strong>Tolerant Matching:</strong> k-grams + Levenshtein</li>
                  <li><strong>Passage Ranking:</strong> TF-IDF cosine similarity</li>
                  <li><strong>Reconciliation:</strong> Jaccard conflict analysis</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Supervisor Sign-Off Dashboard */}
      {activeTab === 'supervisor' && (
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">
                <Icons.AlertTriangle />
                Supervisor Alert Sign-Off Queue
              </div>
              <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Human-in-the-loop review queue for excursions requiring Admin approval.
              </p>
            </div>
            <div className="stat-summary-bar" style={{ marginBottom: 0 }}>
              <div className="stat-summary-card">
                <span className="stat-summary-num">{alerts.length}</span>
                <span className="stat-summary-label">Total Alerts</span>
              </div>
              <div className="stat-summary-card">
                <span className="stat-summary-num" style={{ color: 'var(--amber-warning)' }}>
                  {pendingAlertCount}
                </span>
                <span className="stat-summary-label">Pending</span>
              </div>
            </div>
          </div>

          {alertsError && (
            <div className="provenance-box is-error">
              <div className="provenance-title">Failed to load alerts queue</div>
              {alertsError}
            </div>
          )}

          <div className="inventory-list" style={{ marginTop: '16px' }}>
            {alerts.length === 0 && !alertsError && (
              <p className="empty-state">No safety alerts currently recorded in the queue.</p>
            )}
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className="card"
                style={{ background: 'var(--bg-subtle)', border: '1px solid var(--border-color)', marginBottom: '16px' }}
              >
                <div className="card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="role-tag role-tag-analyst">{alert.alert_id}</span>
                    <strong style={{ fontSize: '16px', fontFamily: 'var(--font-display)' }}>
                      {alert.chemical_name} excursion in {alert.zone_id}
                    </strong>
                  </div>
                  <span
                    className={`state-badge ${
                      alert.status === 'approved'
                        ? 'state-SAFE'
                        : alert.status === 'rejected'
                        ? 'provenance-box is-error'
                        : 'state-WARNING'
                    }`}
                  >
                    {alert.status.replace('_', ' ').toUpperCase()}
                  </span>
                </div>

                <div className="metrics-row" style={{ marginTop: '8px' }}>
                  <div className="metric-box warning">
                    <div className="metric-label">Observed Value</div>
                    <div className="metric-value" style={{ fontSize: '26px' }}>
                      {alert.current_value} <span className="metric-unit">{alert.unit}</span>
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-label">Retrieved Threshold</div>
                    <div className="metric-value" style={{ fontSize: '26px' }}>
                      {alert.threshold_value != null ? alert.threshold_value : '—'}
                      <span className="metric-unit">{alert.unit}</span>
                    </div>
                  </div>
                </div>

                <div className="provenance-box is-warning">
                  <div className="provenance-title">Safety Machine Reasoning</div>
                  {alert.reasoning}
                </div>

                {alert.status === 'pending_review' ? (
                  isAdmin ? (
                    <div
                      style={{
                        marginTop: '18px',
                        display: 'flex',
                        gap: '12px',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                      }}
                    >
                      <input
                        type="text"
                        className="input-field"
                        placeholder="Add sign-off notes (required for compliance)..."
                        value={signOffNote}
                        onChange={(e) => setSignOffNote(e.target.value)}
                        style={{ flex: 1, minWidth: '200px' }}
                      />
                      <button className="action-btn" onClick={() => handleSignOff(alert.alert_id, true)}>
                        <Icons.CheckCircle /> Approve Alert
                      </button>
                      <button
                        className="action-btn btn-danger"
                        onClick={() => handleSignOff(alert.alert_id, false)}
                      >
                        Reject Alert
                      </button>
                    </div>
                  ) : (
                    <p className="help-text">⏳ Awaiting Administrator sign-off.</p>
                  )
                ) : (
                  <div style={{ marginTop: '14px', fontSize: '13px', color: 'var(--text-muted)', background: 'var(--bg-page)', padding: '10px 14px', borderRadius: '6px' }}>
                    <strong>Sign-off record:</strong> {alert.notes || 'No notes added'} (Signed by: {alert.signed_by})
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
