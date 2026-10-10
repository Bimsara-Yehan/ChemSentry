import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Check, ChevronDown, ShieldCheck, TriangleAlert, X } from 'lucide-react';
import { signOffAlert } from '../api';
import { AnimatedNumber } from '../components/motion';
import SafetyCard from '../components/SafetyCard';
import { EmptyState, Loading, Notice, PageHeader } from '../components/ui';
import { zoneName } from '../constants';
import { citationLabel, formatDateTime, formatValue, timeAgo } from '../format';

const FILTERS = [
  { id: 'pending_review', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'all', label: 'All' },
];
const PAGE = 20;

// Alert reasoning embeds its citation as "... Source: [id] Section N - ...
// [policy_version=x]"; pull it out so the expanded row can show the source
// on its own line.
function citationFromReasoning(reasoning) {
  const m = /Source:\s*(\[.*?)(?:\s*\[policy_version=[^\]]*\])?\s*$/.exec(reasoning || '');
  return m ? m[1] : null;
}

// Exceedance as a fraction of the limit, for the severity bar. Display only.
function overshoot(alert) {
  const v = Number(alert.current_value);
  const t = Number(alert.threshold_value);
  if (!Number.isFinite(v) || !Number.isFinite(t) || t === 0) return 0.5;
  return Math.max(0.08, Math.min(1, Math.abs(v - t) / Math.abs(t)));
}

export default function SignoffView({ token, alerts, alertsLoaded, alertsError, setAlertsError, isAdmin, now, refreshAlerts }) {
  const [filter, setFilter] = useState('pending_review');
  const [limit, setLimit] = useState(PAGE);
  const [openId, setOpenId] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const counts = {
    pending_review: alerts.filter((a) => a.status === 'pending_review').length,
    approved: alerts.filter((a) => a.status === 'approved').length,
    rejected: alerts.filter((a) => a.status === 'rejected').length,
    all: alerts.length,
  };
  const filtered = filter === 'all' ? alerts : alerts.filter((a) => a.status === filter);
  const visible = filtered.slice(0, limit);

  const signOff = async (alertId, approved) => {
    setBusy(true);
    try {
      await signOffAlert(token, alertId, approved, note);
      setNote('');
      setOpenId(null);
      await refreshAlerts();
    } catch (err) {
      setAlertsError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Human in the loop"
        title="Sign-off queue"
        subtitle="A WARNING is never final until an admin reviews the evidence and signs it off."
      />

      <div className="stat-row">
        {[
          { k: 'pending_review', label: 'Awaiting review', tone: 'warning' },
          { k: 'approved', label: 'Approved', tone: 'safe' },
          { k: 'rejected', label: 'Rejected', tone: 'danger' },
          { k: 'all', label: 'Total alerts', tone: 'neutral' },
        ].map((s) => (
          <motion.button
            key={s.k}
            className={`stat-tile stat-${s.tone}${filter === s.k ? ' active' : ''}`}
            onClick={() => {
              setFilter(s.k);
              setLimit(PAGE);
              setOpenId(null);
            }}
            whileHover={{ y: -3 }}
            whileTap={{ scale: 0.98 }}
          >
            <span className="stat-label">{s.label}</span>
            <span className="stat-value">
              <AnimatedNumber value={counts[s.k]} decimals={0} />
            </span>
            {filter === s.k && <motion.span layoutId="stat-active" className="stat-active-bar" />}
          </motion.button>
        ))}
      </div>

      {alertsError && (
        <Notice tone="error" icon={TriangleAlert} title="Couldn't load alerts">
          {alertsError}
        </Notice>
      )}

      <div className="card card-flush">
        {!alertsLoaded && !alertsError && <Loading label="Loading alerts…" />}
        {alertsLoaded && filtered.length === 0 && !alertsError && (
          <EmptyState title="All clear" icon={ShieldCheck}>
            No {filter === 'all' ? '' : FILTERS.find((f) => f.id === filter).label.toLowerCase()} alerts.
          </EmptyState>
        )}

        <motion.ul className="alert-list" layout>
          <AnimatePresence initial={false}>
            {visible.map((alert) => {
              const isOpen = openId === alert.alert_id;
              const source = citationLabel(citationFromReasoning(alert.reasoning));
              return (
                <motion.li
                  key={alert.alert_id}
                  layout
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 24, transition: { duration: 0.2 } }}
                  className={`alert-item status-row-${alert.status}${isOpen ? ' is-open' : ''}`}
                >
                  <button
                    className="alert-row"
                    onClick={() => {
                      setOpenId(isOpen ? null : alert.alert_id);
                      setNote('');
                    }}
                    aria-expanded={isOpen}
                  >
                    <span className={`alert-icon status-${alert.status}`}>
                      <TriangleAlert size={15} />
                    </span>
                    <span className="alert-main">
                      <span className="alert-title">{alert.chemical_name}</span>
                      <span className="alert-meta">
                        {zoneName(alert.zone_id)} · {alert.alert_id} · {timeAgo(alert.created_at, now)}
                      </span>
                    </span>
                    <span className="alert-values">
                      <span className="alert-observed">{formatValue(alert.current_value, alert.unit)}</span>
                      <span className="severity-bar" aria-hidden="true">
                        <motion.span
                          initial={{ width: 0 }}
                          animate={{ width: `${overshoot(alert) * 100}%` }}
                          transition={{ type: 'spring', stiffness: 80, damping: 16 }}
                        />
                      </span>
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
                        transition={{ duration: 0.22 }}
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
                          {/* /alerts omits fields by role (api/db_models.py alert_to_dict) */}
                          {alert.reasoning && (
                            <div className="eval-log">
                              <div className="eval-log-line">
                                <span>{alert.reasoning}</span>
                              </div>
                            </div>
                          )}

                          <SafetyCard token={token} alertId={alert.alert_id} />

                          {alert.status === 'pending_review' ? (
                            isAdmin ? (
                              <div className="signoff-bar">
                                <input
                                  type="text"
                                  className="input-field"
                                  placeholder="Sign-off note (optional)"
                                  value={note}
                                  onChange={(e) => setNote(e.target.value)}
                                />
                                <motion.button
                                  className="action-btn btn-safe"
                                  disabled={busy}
                                  whileTap={{ scale: 0.95 }}
                                  onClick={() => signOff(alert.alert_id, true)}
                                >
                                  <Check size={15} /> Approve
                                </motion.button>
                                <motion.button
                                  className="action-btn btn-danger"
                                  disabled={busy}
                                  whileTap={{ scale: 0.95 }}
                                  onClick={() => signOff(alert.alert_id, false)}
                                >
                                  <X size={15} /> Reject
                                </motion.button>
                              </div>
                            ) : (
                              <p className="help-text">Awaiting admin sign-off.</p>
                            )
                          ) : (
                            <p className="signoff-record">
                              <strong>
                                {alert.status === 'approved' ? 'Approved' : 'Rejected'}
                                {alert.signed_by && <> by {alert.signed_by}</>}
                              </strong>
                              {alert.signed_at && <> · {formatDateTime(alert.signed_at)}</>}
                              {alert.notes && <> — “{alert.notes}”</>}
                            </p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </motion.ul>

        {filtered.length > 0 && (
          <div className="list-footer">
            <span>
              Showing {visible.length} of {filtered.length}
            </span>
            {visible.length < filtered.length && (
              <button className="action-btn btn-secondary btn-sm" onClick={() => setLimit((n) => n + PAGE)}>
                Show more
              </button>
            )}
          </div>
        )}
      </div>
    </>
  );
}
