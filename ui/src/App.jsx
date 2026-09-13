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
        <div className="card-title" style={{ marginBottom: '16px' }}>
          🔐 ChemSentry Sign-In
        </div>
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
          <div className="provenance-box" style={{ marginTop: '16px' }}>
            <div className="provenance-title">LOGIN FAILED</div>
            {error}
          </div>
        )}
        <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '16px' }}>
          Demo users: viewer_user/viewer123 · analyst_user/analyst123 ·
          admin_user/admin123
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

  useEffect(() => {
    if (token && activeTab === 'supervisor') {
      refreshAlerts(token);
    }
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

  if (!token) {
    return (
      <div className="app-container">
        <header className="app-header">
          <div className="brand-section">
            <div className="brand-logo">CS</div>
            <div className="brand-title">
              <h1>ChemSentry</h1>
              <p>Agentic AI Chemical Safety & Decision-Support System</p>
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
            <p>Agentic AI Chemical Safety & Decision-Support System</p>
          </div>
        </div>
        <div className="header-status">
          <div className="status-badge">
            <span className="pulse-dot"></span>
            SYSTEM ONLINE (API v0.1.0)
          </div>
          <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
            {currentUser?.username} ({currentUser?.role}){' '}
            <button
              className="action-btn"
              style={{ padding: '2px 10px', fontSize: '11px', marginLeft: '8px' }}
              onClick={handleLogout}
            >
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
          🌡️ Live Environment
        </button>
        <button
          className={`tab-btn ${activeTab === 'reconciliation' ? 'active' : ''}`}
          onClick={() => setActiveTab('reconciliation')}
        >
          🔍 SDS Retrieval & Reconciliation
        </button>
        <button
          className={`tab-btn ${activeTab === 'supervisor' ? 'active' : ''}`}
          onClick={() => setActiveTab('supervisor')}
        >
          🛡️ Supervisor Sign-Off ({pendingAlertCount})
        </button>
      </nav>

      {/* Tab 1: Live Environment View */}
      {activeTab === 'live' && (
        <div className="dashboard-grid">
          <div className="main-content">
            <div className="card">
              <div className="card-header">
                <div className="card-title">
                  <span>📍 Storage Zone Telemetry</span>
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
                <div className="provenance-box">
                  <div className="provenance-title">FAILED TO LOAD ZONE DATA</div>
                  {zonesError}
                </div>
              )}

              {currentZoneData ? (
                <>
                  <h2>{ZONE_LABELS[activeZone] || activeZone}</h2>
                  <p style={{ color: 'var(--text-muted)', marginBottom: '20px' }}>
                    Monitored by ESP32 sensor node over MQTT TLS
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
                        Status:{' '}
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
                      <div className="metric-subtext">Not evaluated (no retrieved threshold)</div>
                    </div>
                  </div>

                  {currentZoneData.checks.map((check, idx) => (
                    <div className="provenance-box" key={idx}>
                      <div className="provenance-title">
                        {check.state === 'WARNING' ? '⚠️ ' : ''}
                        {check.chemical_name} — {check.metric_name} [{check.state}]
                      </div>
                      {check.reasoning}
                    </div>
                  ))}
                </>
              ) : (
                <p style={{ color: 'var(--text-muted)' }}>Loading zone data…</p>
              )}
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                🧪 Active Chemicals in Zone
              </div>
              <div className="inventory-list">
                {(currentZoneData?.chemicals || []).map((chem, idx) => (
                  <div key={idx} className="inventory-item">
                    <span className="chem-tag">{chem}</span>
                    <span style={{ color: 'var(--text-muted)' }}>
                      Database-tagged (simulated inventory)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                🎮 Telemetry Simulator
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Sends a real reading to POST /zones/{activeZone}/telemetry and shows the
                real deterministic evaluation returned.
              </p>
              <button
                className="action-btn btn-warning"
                style={{ width: '100%', marginBottom: '10px' }}
                onClick={() => handleSendReading(demoTemps.excursion)}
                disabled={isViewer || telemetryLoading}
              >
                🔥 Send Excursion Reading ({demoTemps.excursion} °C)
              </button>
              <button
                className="action-btn"
                style={{ width: '100%', background: '#2A2F36' }}
                onClick={() => handleSendReading(demoTemps.safe)}
                disabled={isViewer || telemetryLoading}
              >
                🔄 Send Normal Reading ({demoTemps.safe} °C)
              </button>
              {isViewer && (
                <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '10px' }}>
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
              <div className="card-title" style={{ marginBottom: '16px' }}>
                🔍 Classical IR Retrieval & Reconciliation Engine
              </div>
              <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px' }}>
                <input
                  type="text"
                  className="input-field"
                  placeholder="Enter chemical name (e.g. Ethanol, Sodium hydroxide)..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <button type="submit" className="action-btn" disabled={queryLoading}>
                  {queryLoading ? 'Searching…' : 'Search'}
                </button>
              </form>
              {isViewer && (
                <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '10px' }}>
                  Viewer role cannot query -- sign in as analyst or admin.
                </p>
              )}
            </div>

            {queryError && (
              <div className="card">
                <div className="provenance-box">
                  <div className="provenance-title">QUERY FAILED</div>
                  {queryError}
                </div>
              </div>
            )}

            {queryResult && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    Query Evidence for:{' '}
                    <span style={{ color: 'var(--teal-light)' }}>
                      {queryResult.query.chemical_name}
                    </span>
                  </div>
                  <span className={`state-badge state-${queryResult.evidence.final_safety_state}`}>
                    {queryResult.evidence.final_safety_state}
                  </span>
                </div>

                <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
                  Retrieved Provenanced Thresholds:
                </h4>
                {queryResult.evidence.thresholds.length === 0 && (
                  <p style={{ color: 'var(--text-dim)', fontSize: '13px' }}>
                    No thresholds resolved for this chemical name in the current corpus.
                  </p>
                )}
                {queryResult.evidence.thresholds.map((t, idx) => (
                  <div key={idx} className="inventory-item" style={{ marginBottom: '10px' }}>
                    <div>
                      <strong>{t.parameter}</strong>:{' '}
                      <span style={{ color: 'var(--amber-warning)' }}>
                        {t.value} {t.unit}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                      Citation: {t.version}
                    </div>
                  </div>
                ))}

                {queryResult.evidence.conflicts.map((conflict, idx) => (
                  <div key={idx} className="provenance-box">
                    <div className="provenance-title">🔀 SUPPLIER CONFLICT DETECTED</div>
                    {conflict}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                📚 IR Pipeline Info
              </div>
              <ul
                style={{
                  fontSize: '13px',
                  color: 'var(--text-muted)',
                  lineHeight: '1.8',
                  paddingLeft: '16px',
                }}
              >
                <li><strong>Inverted Index:</strong> Positional word mapping (Lab 03)</li>
                <li><strong>Tolerant Matching:</strong> k-grams + Levenshtein (Lab 04)</li>
                <li><strong>Ranking:</strong> TF-IDF Cosine similarity (Lab 05)</li>
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
            <div className="card-title">🛡️ Supervisor Alert Review & Sign-Off Queue</div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Human-in-the-Loop Architectural Requirement
            </span>
          </div>

          {alertsError && (
            <div className="provenance-box">
              <div className="provenance-title">FAILED TO LOAD ALERTS</div>
              {alertsError}
            </div>
          )}

          <div className="inventory-list">
            {alerts.length === 0 && !alertsError && (
              <p style={{ color: 'var(--text-muted)', padding: '12px 0' }}>
                No alerts recorded yet.
              </p>
            )}
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className="card"
                style={{ background: '#111418', marginBottom: '16px' }}
              >
                <div className="card-header">
                  <div>
                    <span className="state-badge state-WARNING" style={{ marginRight: '12px' }}>
                      {alert.alert_id}
                    </span>
                    <strong style={{ fontSize: '16px' }}>
                      {alert.chemical_name} Excursion in {alert.zone_id}
                    </strong>
                  </div>
                  <span
                    style={{
                      fontSize: '13px',
                      color:
                        alert.status === 'approved'
                          ? 'var(--green-safe)'
                          : alert.status === 'rejected'
                          ? 'var(--red-danger)'
                          : 'var(--amber-warning)',
                    }}
                  >
                    Status: {alert.status.toUpperCase()}
                  </span>
                </div>

                <div className="metrics-row" style={{ marginTop: '12px' }}>
                  <div className="metric-box">
                    <div className="metric-label">Observed Value</div>
                    <div className="metric-value" style={{ fontSize: '24px', color: 'var(--amber-warning)' }}>
                      {alert.current_value} {alert.unit}
                    </div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-label">Retrieved Threshold</div>
                    <div className="metric-value" style={{ fontSize: '24px' }}>
                      {alert.threshold_value != null ? `${alert.threshold_value} ${alert.unit}` : '—'}
                    </div>
                  </div>
                </div>

                <div className="provenance-box">
                  <div className="provenance-title">PROVENANCE / REASONING</div>
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
                      }}
                    >
                      <input
                        type="text"
                        className="input-field"
                        placeholder="Add Safety Officer sign-off notes..."
                        value={signOffNote}
                        onChange={(e) => setSignOffNote(e.target.value)}
                        style={{ flex: 1 }}
                      />
                      <button className="action-btn" onClick={() => handleSignOff(alert.alert_id, true)}>
                        Approve Alert
                      </button>
                      <button
                        className="action-btn btn-danger"
                        onClick={() => handleSignOff(alert.alert_id, false)}
                      >
                        Reject Alert
                      </button>
                    </div>
                  ) : (
                    <p style={{ marginTop: '12px', fontSize: '13px', color: 'var(--text-dim)' }}>
                      Awaiting admin sign-off.
                    </p>
                  )
                ) : (
                  <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--text-muted)' }}>
                    <strong>Sign-off Notes:</strong> {alert.notes} (by {alert.signed_by})
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
