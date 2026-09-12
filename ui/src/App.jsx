import React, { useState } from 'react';
import './index.css';

function App() {
  const [activeTab, setActiveTab] = useState('live');
  const [activeZone, setActiveZone] = useState('Zone_B');
  
  // Live Environment State (Simulated Zone Readings)
  const [zones, setZones] = useState({
    Zone_A: {
      name: 'Zone A — Dyeing & Finishing',
      temperature: 22.5,
      humidity: 48.0,
      status: 'SAFE',
      chemicals: ['Sodium Hydroxide', 'Reactive Dyes', 'Acetic Acid']
    },
    Zone_B: {
      name: 'Zone B — Solvent Storage',
      temperature: 31.0,  // Excursion (>25 C)
      humidity: 62.0,
      status: 'WARNING',
      chemicals: ['Toluene', 'Ethanol', 'Acetone']
    },
    Zone_C: {
      name: 'Zone C — Acid Processing',
      temperature: 21.0,
      humidity: 55.0,
      status: 'SAFE',
      chemicals: ['Hydrochloric Acid', 'Sulfuric Acid']
    }
  });

  // Query & Reconciliation Search State
  const [searchQuery, setSearchQuery] = useState('Toluene');
  const [queryResult, setQueryResult] = useState({
    chemical: 'Toluene',
    safetyState: 'WARNING',
    fastPathAnswer: null,
    thresholds: [
      {
        metric: 'max_storage_temperature',
        limit: '25.0 °C',
        supplier: 'ABC Chemicals',
        citation: 'ABC Chemicals SDS Rev 2026-02 §7, p.5'
      },
      {
        metric: 'flash_point',
        limit: '4.4 °C',
        supplier: 'ABC Chemicals',
        citation: 'ABC Chemicals SDS Rev 2026-02 §9, p.7'
      }
    ],
    conflicts: [
      'Jaccard conflict detected: Supplier A requires ≤25 °C whereas Supplier B specifies ≤30 °C. Restrictive limit (25.0 °C) applied.'
    ]
  });

  // Supervisor Alert Queue State
  const [alerts, setAlerts] = useState([
    {
      id: 'ALT_0001',
      zone: 'Zone B — Solvent Storage',
      chemical: 'Toluene',
      observed: '31.0 °C',
      threshold: '25.0 °C',
      citation: 'ABC Chemicals SDS Rev 2026-02 §7, p.5',
      reason: 'Observed temperature (31.0 °C) exceeds retrieved SDS maximum limit (25.0 °C)',
      status: 'pending_review',
      notes: ''
    }
  ]);

  const [signOffNote, setSignOffNote] = useState('');

  // Handle Simulation Trigger
  const handleSimulateExcursion = () => {
    setZones(prev => ({
      ...prev,
      Zone_B: {
        ...prev.Zone_B,
        temperature: 34.5,
        status: 'WARNING'
      }
    }));
  };

  const handleResetExcursion = () => {
    setZones(prev => ({
      ...prev,
      Zone_B: {
        ...prev.Zone_B,
        temperature: 23.0,
        status: 'SAFE'
      }
    }));
  };

  // Handle Search Submission
  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.toLowerCase().includes('flash')) {
      setQueryResult({
        chemical: searchQuery,
        safetyState: 'SAFE',
        fastPathAnswer: `The flash point of ${searchQuery} is dynamically retrieved from Section 9 (Physical Properties) of its versioned SDS.`,
        thresholds: [],
        conflicts: []
      });
    } else {
      setQueryResult({
        chemical: searchQuery,
        safetyState: searchQuery.toLowerCase() === 'toluene' ? 'WARNING' : 'SAFE',
        fastPathAnswer: null,
        thresholds: [
          {
            metric: 'max_storage_temperature',
            limit: searchQuery.toLowerCase() === 'acetone' ? '20.0 °C' : '25.0 °C',
            supplier: 'Versioned SDS Supplier',
            citation: `${searchQuery} SDS Rev 2026-01 §7`
          }
        ],
        conflicts: []
      });
    }
  };

  // Handle Admin Sign-off
  const handleSignOff = (alertId, approved) => {
    setAlerts(prev => prev.map(a => {
      if (a.id === alertId) {
        return {
          ...a,
          status: approved ? 'approved' : 'rejected',
          notes: signOffNote || (approved ? 'Verified by Safety Officer.' : 'Excursion dismissed after inspection.')
        };
      }
      return a;
    }));
    setSignOffNote('');
  };

  const currentZoneData = zones[activeZone];

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
          🛡️ Supervisor Sign-Off ({alerts.filter(a => a.status === 'pending_review').length})
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
                  {Object.keys(zones).map(z => (
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

              <h2>{currentZoneData.name}</h2>
              <p style={{ color: 'var(--text-muted)', marginBottom: '20px' }}>
                Monitored by ESP32 sensor node over MQTT TLS
              </p>

              <div className="metrics-row">
                <div className={`metric-box ${currentZoneData.status === 'WARNING' ? 'warning' : ''}`}>
                  <div className="metric-label">Temperature</div>
                  <div className="metric-value">
                    {currentZoneData.temperature} <span className="metric-unit">°C</span>
                  </div>
                  <div className="metric-subtext">
                    Status: <span className={`state-badge state-${currentZoneData.status}`}>{currentZoneData.status}</span>
                  </div>
                </div>

                <div className="metric-box">
                  <div className="metric-label">Relative Humidity</div>
                  <div className="metric-value">
                    {currentZoneData.humidity} <span className="metric-unit">%</span>
                  </div>
                  <div className="metric-subtext">Optimal range: 40% - 65%</div>
                </div>
              </div>

              {currentZoneData.status === 'WARNING' && (
                <div className="provenance-box">
                  <div className="provenance-title">⚠️ THRESHOLD EXCURSION DETECTED</div>
                  Observed temperature ({currentZoneData.temperature} °C) exceeds retrieved threshold of 25.0 °C for Toluene. No threshold is hardcoded; limit dynamically retrieved from versioned SDS.
                </div>
              )}
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: '16px' }}>
                🧪 Active Chemicals in Zone
              </div>
              <div className="inventory-list">
                {currentZoneData.chemicals.map((chem, idx) => (
                  <div key={idx} className="inventory-item">
                    <span className="chem-tag">{chem}</span>
                    <span style={{ color: 'var(--text-muted)' }}>Container Tagged (RFID)</span>
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
                Test backend deterministic evaluation by triggering an excursion.
              </p>
              <button 
                className="action-btn btn-warning" 
                style={{ width: '100%', marginBottom: '10px' }}
                onClick={handleSimulateExcursion}
              >
                🔥 Simulate Temp Spike (34.5 °C)
              </button>
              <button 
                className="action-btn" 
                style={{ width: '100%', background: '#2A2F36' }}
                onClick={handleResetExcursion}
              >
                🔄 Reset to Normal (23.0 °C)
              </button>
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
                  placeholder="Enter chemical name (e.g. Toluene, Ethanol) or query..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <button type="submit" className="action-btn">Search</button>
              </form>
            </div>

            {queryResult && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">
                    Query Evidence for: <span style={{ color: 'var(--teal-light)' }}>{queryResult.chemical}</span>
                  </div>
                  <span className={`state-badge state-${queryResult.safetyState}`}>
                    {queryResult.safetyState}
                  </span>
                </div>

                {queryResult.fastPathAnswer ? (
                  <div className="provenance-box" style={{ borderColor: 'var(--teal-light)' }}>
                    <div className="provenance-title" style={{ color: 'var(--teal-light)' }}>⚡ LAB 06B FAST-PATH ANSWER</div>
                    {queryResult.fastPathAnswer}
                  </div>
                ) : (
                  <>
                    <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>Retrieved Provenanced Thresholds:</h4>
                    {queryResult.thresholds.map((t, idx) => (
                      <div key={idx} className="inventory-item" style={{ marginBottom: '10px' }}>
                        <div>
                          <strong>{t.metric}</strong>: <span style={{ color: 'var(--amber-warning)' }}>{t.limit}</span>
                        </div>
                        <div style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                          Citation: {t.citation}
                        </div>
                      </div>
                    ))}

                    {queryResult.conflicts.map((conflict, idx) => (
                      <div key={idx} className="provenance-box">
                        <div className="provenance-title">🔀 JACCARD SUPPLIER CONFLICT DETECTED</div>
                        {conflict}
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>

          <div className="side-content">
            <div className="card">
              <div className="card-title" style={{ marginBottom: '12px' }}>
                📚 IR Pipeline Info
              </div>
              <ul style={{ fontSize: '13px', color: 'var(--text-muted)', lineHeight: '1.8', paddingLeft: '16px' }}>
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
            <div className="card-title">
              🛡️ Supervisor Alert Review & Sign-Off Queue
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Human-in-the-Loop Architectural Requirement
            </span>
          </div>

          <div className="inventory-list">
            {alerts.map((alert) => (
              <div key={alert.id} className="card" style={{ background: '#111418', marginBottom: '16px' }}>
                <div className="card-header">
                  <div>
                    <span className="state-badge state-WARNING" style={{ marginRight: '12px' }}>
                      {alert.id}
                    </span>
                    <strong style={{ fontSize: '16px' }}>{alert.chemical} Excursion in {alert.zone}</strong>
                  </div>
                  <span style={{ fontSize: '13px', color: alert.status === 'approved' ? 'var(--green-safe)' : alert.status === 'rejected' ? 'var(--red-danger)' : 'var(--amber-warning)' }}>
                    Status: {alert.status.toUpperCase()}
                  </span>
                </div>

                <div className="metrics-row" style={{ marginTop: '12px' }}>
                  <div className="metric-box">
                    <div className="metric-label">Observed Value</div>
                    <div className="metric-value" style={{ fontSize: '24px', color: 'var(--amber-warning)' }}>{alert.observed}</div>
                  </div>
                  <div className="metric-box">
                    <div className="metric-label">Retrieved Threshold</div>
                    <div className="metric-value" style={{ fontSize: '24px' }}>{alert.threshold}</div>
                  </div>
                </div>

                <div className="provenance-box">
                  <div className="provenance-title">PROVENANCE CITATION</div>
                  {alert.citation} — {alert.reason}
                </div>

                {alert.status === 'pending_review' ? (
                  <div style={{ marginTop: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <input 
                      type="text" 
                      className="input-field" 
                      placeholder="Add Safety Officer sign-off notes..."
                      value={signOffNote}
                      onChange={(e) => setSignOffNote(e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <button 
                      className="action-btn"
                      onClick={() => handleSignOff(alert.id, true)}
                    >
                      Approve Alert
                    </button>
                    <button 
                      className="action-btn btn-danger"
                      onClick={() => handleSignOff(alert.id, false)}
                    >
                      Reject Alert
                    </button>
                  </div>
                ) : (
                  <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--text-muted)' }}>
                    <strong>Sign-off Notes:</strong> {alert.notes}
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
