import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FileText, Radio, Thermometer, TriangleAlert } from 'lucide-react';
import ChemTile from '../components/ChemTile';
import CoStoragePanel from '../components/CoStoragePanel';
import StorageLimitsTable from '../components/StorageLimitsTable';
import VesselGauge from '../components/VesselGauge';
import { RingGauge } from '../components/motion';
import { stagger } from '../components/motionVariants';
import { Loading, Notice, PageHeader, StateBadge } from '../components/ui';
import { SENSOR_RANGE, zoneName, zoneSummary } from '../constants';
import { formatUnit, formatValue, humanizeMetric, unitForCheck } from '../format';

function secondsAgo(since, now) {
  if (!since) return null;
  const s = Math.max(0, Math.round((now - since.getTime()) / 1000));
  return s < 1 ? 'just now' : `${s}s ago`;
}

// Worst state across a chemical's own checks, for tile colouring only. This
// is a display grouping of verdicts the backend already made per check -- it
// never upgrades UNKNOWN to SAFE.
function chemicalState(checks) {
  if (checks.some((c) => c.state === 'WARNING')) return 'WARNING';
  if (checks.length && checks.every((c) => c.state === 'SAFE')) return 'SAFE';
  return 'UNKNOWN';
}

// The limits the backend's evaluation used for this zone: every check that
// carries a retrieved threshold, with that threshold's citation. These are
// exactly the values Agent A retrieved from the SDS corpus -- the UI never
// supplies a limit of its own.
function limitsFromChecks(checks) {
  return checks
    .filter((c) => c.threshold_value != null)
    .map((c) => ({
      chemical_name: c.chemical_name,
      metric_name: c.metric_name,
      value: Number(c.threshold_value),
      unit: unitForCheck(c),
      citation: c.citation,
    }));
}

// Distinct temperature limits for the zone. Drawn on the vessel and used to
// derive simulator presets.
function temperatureLimits(limits) {
  const seen = new Map();
  for (const l of limits) {
    const kind = l.metric_name.startsWith('min') ? 'min' : 'max';
    const key = `${kind}-${l.value}`;
    if (!seen.has(key)) seen.set(key, { metric: key, kind, value: Number(l.value) });
  }
  return [...seen.values()];
}

// Simulator presets computed from the zone's retrieved limits: the tightest
// retrieved range, a point inside it, and a point just outside each edge.
// No preset exists when no limit is on file -- there is nothing to test.
function presetsFrom(limits) {
  const maxes = limits.filter((l) => l.kind === 'max').map((l) => l.value);
  const mins = limits.filter((l) => l.kind === 'min').map((l) => l.value);
  const max = maxes.length ? Math.min(...maxes) : null;
  const min = mins.length ? Math.max(...mins) : null;
  const presets = [];
  if (min != null && max != null && min < max) {
    presets.push({ label: 'Inside retrieved range', value: (min + max) / 2, tone: 'ok' });
  }
  if (max != null) presets.push({ label: 'Above retrieved maximum', value: max + 1, tone: 'hot' });
  if (min != null) presets.push({ label: 'Below retrieved minimum', value: min - 1, tone: 'cold' });
  return presets;
}

const midpoint = ({ min, max }) => (min + max) / 2;

export default function LiveView({
  token,
  zones,
  zoneIds,
  activeZone,
  setActiveZone,
  zonesError,
  zonesLastUpdated,
  now,
  isViewer,
  telemetryLoading,
  onSendReading,
}) {
  const zone = activeZone ? zones[activeZone] : null;
  const reading = zone?.last_reading || null;
  const zoneLimits = useMemo(() => limitsFromChecks(zone?.checks || []), [zone]);
  const limits = useMemo(() => temperatureLimits(zoneLimits), [zoneLimits]);
  const presets = useMemo(() => presetsFrom(limits), [limits]);

  const [temp, setTemp] = useState(midpoint(SENSOR_RANGE.temperature));
  const [humidity, setHumidity] = useState(midpoint(SENSOR_RANGE.humidity));
  const [selectedChem, setSelectedChem] = useState(null);

  // When switching zones, start the sliders from that zone's last real
  // reading, if there is one.
  useEffect(() => {
    setSelectedChem(null);
    if (reading) {
      setTemp(reading.temperature_celsius);
      setHumidity(reading.humidity_percent);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeZone]);

  const chemRows = useMemo(() => {
    if (!zone) return [];
    return zone.chemicals.map((name) => {
      const own = zone.checks.filter((c) => c.chemical_name === name);
      // min before max, so the tile reads as a range ("15 °C – 25 °C").
      const ownLimits = zoneLimits
        .filter((l) => l.chemical_name === name)
        .sort((x, y) => (x.metric_name.startsWith('min') ? -1 : 1) - (y.metric_name.startsWith('min') ? -1 : 1));
      return {
        name,
        checks: own,
        hasLimit: ownLimits.length > 0,
        state: chemicalState(own),
        limitText: ownLimits.length
          ? ownLimits.map((l) => formatValue(l.value, l.unit)).join(' – ')
          : 'No limit in SDS',
      };
    });
  }, [zone, zoneLimits]);

  const withoutLimit = chemRows.filter((r) => !r.hasLimit).length;
  const selected = chemRows.find((r) => r.name === selectedChem);
  const tRange = SENSOR_RANGE.temperature;
  const hRange = SENSOR_RANGE.humidity;

  return (
    <>
      <PageHeader
        eyebrow="Process monitoring"
        title="Live environment"
        subtitle="Real-time vessel conditions checked against limits retrieved from each chemical's SDS."
      />

      <motion.div className="zone-switcher" role="tablist" aria-label="Zones" variants={stagger} initial="hidden" animate="show">
        {zoneIds.map((z) => {
          const zd = zones[z];
          const state = zd?.safety_state || 'UNKNOWN';
          const isActive = activeZone === z;
          return (
            <motion.button
              key={z}
              role="tab"
              aria-selected={isActive}
              className={`zone-card zone-${state}${isActive ? ' active' : ''}`}
              onClick={() => setActiveZone(z)}
              whileHover={{ y: -3 }}
              whileTap={{ scale: 0.98 }}
            >
              {isActive && <motion.span layoutId="zone-active" className="zone-card-active" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />}
              <span className="zone-card-top">
                <span className="zone-card-name">{zoneName(z)}</span>
                <span className={`zone-dot zone-dot-${state}`} title={state} />
              </span>
              <span className="zone-card-label">{zoneSummary(zd?.chemicals)}</span>
              <span className="zone-card-reading">
                {zd?.last_reading ? (
                  <>
                    <Thermometer size={13} /> {zd.last_reading.temperature_celsius.toFixed(1)} °C
                    <span className="zone-card-sep">·</span>
                    {zd.last_reading.humidity_percent.toFixed(0)} %
                  </>
                ) : (
                  'No reading yet'
                )}
              </span>
            </motion.button>
          );
        })}
      </motion.div>

      {zonesError && (
        <Notice tone="error" icon={TriangleAlert} title="Couldn't load zone data">
          {zonesError}
        </Notice>
      )}

      {!zone ? (
        !zonesError && <Loading label="Loading zones…" />
      ) : (
        <motion.div
          key={activeZone}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="dashboard-grid"
        >
          <div className="main-col">
            <div className={`card instrument-card glow-${zone.safety_state}`}>
              <div className="card-head">
                <div>
                  <div className="eyebrow">
                    {zoneName(activeZone)} · {reading ? `device ${reading.device_id}` : 'awaiting first reading'}
                  </div>
                  <h3 className="card-heading">{zoneSummary(zone.chemicals)}</h3>
                </div>
                <div className="card-head-right">
                  {zonesLastUpdated && (
                    <span className="live-indicator">
                      <span className="live-dot" />
                      <Radio size={12} /> {secondsAgo(zonesLastUpdated, now)}
                    </span>
                  )}
                  <StateBadge state={zone.safety_state} size="lg" />
                </div>
              </div>

              <div className="instrument">
                <VesselGauge value={reading?.temperature_celsius ?? null} state={zone.safety_state} limits={limits} />
                <div className="instrument-side">
                  <RingGauge value={reading?.humidity_percent ?? null} label="Humidity" tone="cyan" />
                  <dl className="instrument-stats">
                    <div>
                      <dt>Excursion</dt>
                      <dd className={zone.is_excursion ? 'text-warning' : ''}>
                        {!reading ? '—' : zone.is_excursion ? 'Detected' : 'None'}
                      </dd>
                    </div>
                    <div>
                      <dt>Checks run</dt>
                      <dd>{zone.checks.length}</dd>
                    </div>
                    <div>
                      <dt>Limits on file</dt>
                      <dd>{zoneLimits.length}</dd>
                    </div>
                  </dl>
                  {reading ? (
                    <p className="instrument-note">
                      Reading taken {new Date(reading.timestamp).toLocaleTimeString()}. Humidity is shown but not
                      evaluated: no SDS in the corpus states a humidity limit.
                    </p>
                  ) : (
                    <p className="instrument-note">
                      No sensor has reported for this zone since the server started. The zone stays UNKNOWN until a
                      real reading arrives.
                    </p>
                  )}
                </div>
              </div>

              {withoutLimit > 0 && (
                <Notice tone="neutral" icon={FileText}>
                  {withoutLimit === zone.chemicals.length
                    ? `None of the ${withoutLimit} chemicals here has a storage-temperature limit in the SDS corpus`
                    : `${withoutLimit} of ${zone.chemicals.length} chemicals here have no storage-temperature limit in the SDS corpus`}
                  , so they are reported UNKNOWN rather than assumed safe.
                </Notice>
              )}
            </div>

            <div className="card">
              <div className="card-head">
                <div>
                  <div className="eyebrow">Inventory</div>
                  <h3 className="card-heading">Stored chemicals</h3>
                </div>
                <span className="muted small">Select a tile for its evaluation trace</span>
              </div>
              <motion.div className="chem-grid" variants={stagger} initial="hidden" animate="show">
                {chemRows.map((r) => (
                  <ChemTile
                    key={r.name}
                    name={r.name}
                    state={r.state}
                    limitText={r.limitText}
                    selected={selectedChem === r.name}
                    onClick={() => setSelectedChem(selectedChem === r.name ? null : r.name)}
                  />
                ))}
              </motion.div>
              <AnimatePresence>
                {selected && (
                  <motion.div
                    className="eval-log"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                  >
                    {selected.checks.length === 0 && (
                      <div className="eval-log-line">
                        {reading ? 'No checks were run for this chemical.' : 'Not evaluated yet: no reading received for this zone.'}
                      </div>
                    )}
                    {selected.checks.map((c) => (
                      <div key={c.metric_name} className="eval-log-line">
                        <span className="eval-log-metric">{humanizeMetric(c.metric_name)}</span>
                        <span>{c.reasoning}</span>
                      </div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div className="card">
              <div className="section-title">Storage limits by source</div>
              <StorageLimitsTable chemicals={zone.chemicals || []} limits={zoneLimits} checks={zone.checks || []} />
            </div>
          </div>

          <div className="side-col">
            <div className="card">
              <div className="eyebrow">Sensor simulator</div>
              <h3 className="card-heading">Inject a reading</h3>
              <p className="card-sub">Runs the same evaluation path as a live ESP32 reading for {zoneName(activeZone)}.</p>

              <div className={`slider-field slider-temp${isViewer ? ' is-disabled' : ''}`}>
                <div className="slider-head">
                  <span>
                    <Thermometer size={14} /> Temperature
                  </span>
                  <strong>{temp.toFixed(1)} °C</strong>
                </div>
                <input
                  type="range"
                  min={tRange.min}
                  max={tRange.max}
                  step={0.5}
                  value={temp}
                  onChange={(e) => setTemp(Number(e.target.value))}
                  disabled={isViewer}
                  style={{ '--pct': `${((temp - tRange.min) / (tRange.max - tRange.min)) * 100}%` }}
                  aria-label="Temperature"
                />
              </div>
              <div className={`slider-field slider-hum${isViewer ? ' is-disabled' : ''}`}>
                <div className="slider-head">
                  <span>Humidity</span>
                  <strong>{humidity}%</strong>
                </div>
                <input
                  type="range"
                  min={hRange.min}
                  max={hRange.max}
                  step={1}
                  value={humidity}
                  onChange={(e) => setHumidity(Number(e.target.value))}
                  disabled={isViewer}
                  style={{ '--pct': `${((humidity - hRange.min) / (hRange.max - hRange.min)) * 100}%` }}
                  aria-label="Humidity"
                />
              </div>

              {presets.length > 0 ? (
                <div className="preset-row">
                  {presets.map((p) => (
                    <button
                      key={p.label}
                      className={`chip-btn${p.tone === 'hot' ? ' chip-hot' : ''}`}
                      disabled={isViewer}
                      onClick={() => setTemp(p.value)}
                      title="Derived from the retrieved SDS limits for this zone"
                    >
                      {p.label} · {p.value.toFixed(1)}
                      {formatUnit('C')}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="help-text">
                  No storage-temperature limit is on file for this zone, so any reading will evaluate UNKNOWN.
                </p>
              )}

              <motion.button
                className="action-btn btn-block btn-glow"
                onClick={() => onSendReading(activeZone, temp, humidity)}
                disabled={isViewer || telemetryLoading}
                whileTap={{ scale: 0.97 }}
              >
                <Radio size={15} /> {telemetryLoading ? 'Transmitting…' : 'Transmit reading'}
              </motion.button>
              {isViewer && <p className="help-text">Your role is read-only.</p>}
            </div>

            <CoStoragePanel token={token} zoneId={activeZone} />

            <div className="card">
              <div className="eyebrow">Legend</div>
              <h3 className="card-heading">Safety states</h3>
              <ul className="legend">
                <li>
                  <StateBadge state="SAFE" size="sm" />
                  <span>Within every retrieved limit</span>
                </li>
                <li>
                  <StateBadge state="WARNING" size="sm" />
                  <span>A retrieved limit is exceeded. Needs admin sign-off</span>
                </li>
                <li>
                  <StateBadge state="UNKNOWN" size="sm" />
                  <span>No reading or no limit on file, so it is never assumed safe</span>
                </li>
              </ul>
            </div>
          </div>
        </motion.div>
      )}
    </>
  );
}
