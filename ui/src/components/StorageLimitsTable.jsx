import { Fragment, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { SourceCell, StateBadge } from './ui';
import { citationLabel, formatValue, humanizeMetric, unitForCheck } from '../format';

// min_* before max_* so a row reads as a range left to right.
function metricOrder(a, b) {
  const rank = (m) => (m.startsWith('min_') ? 0 : m.startsWith('max_') ? 1 : 2);
  return rank(a) - rank(b) || a.localeCompare(b);
}

// Display-only regrouping of the backend's per-(chemical, metric) checks.
// Each cell shows that check's own state -- the table never derives a
// per-chemical verdict itself; the only aggregate shown anywhere is the
// zone-level safety_state the backend already computed.
function groupChecks(chemicals, checks) {
  const metrics = [...new Set(checks.map((c) => c.metric_name))].sort(metricOrder);
  const byChemical = new Map(chemicals.map((name) => [name, {}]));
  for (const c of checks) {
    if (!byChemical.has(c.chemical_name)) byChemical.set(c.chemical_name, {});
    byChemical.get(c.chemical_name)[c.metric_name] = c;
  }
  return { metrics, rows: [...byChemical.entries()] };
}

function LimitCell({ check }) {
  if (!check) return <span className="muted">—</span>;
  if (check.state === 'UNKNOWN' && check.threshold_value == null) {
    return (
      <span className="limit-cell">
        <StateBadge state="UNKNOWN" size="sm" />
        <span className="muted">Not in SDS</span>
      </span>
    );
  }
  return (
    <span className="limit-cell">
      <StateBadge state={check.state} size="sm" />
      <span className="limit-value">{formatValue(check.threshold_value, unitForCheck(check))}</span>
    </span>
  );
}

export default function StorageLimitsTable({ chemicals = [], checks = [] }) {
  const [expanded, setExpanded] = useState(null);
  const { metrics, rows } = groupChecks(chemicals, checks);

  if (rows.length === 0) {
    return <p className="muted">No chemicals are assigned to this zone.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Chemical</th>
            {metrics.map((m) => (
              <th key={m}>{humanizeMetric(m)}</th>
            ))}
            <th>Source</th>
            <th aria-label="Details" />
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, byMetric]) => {
            const rowChecks = Object.values(byMetric);
            const seen = new Set();
            const sources = rowChecks
              .map((c) => c.citation)
              .filter((cit) => cit && !seen.has(citationLabel(cit)) && seen.add(citationLabel(cit)));
            const isOpen = expanded === name;
            return (
              <Fragment key={name}>
                <tr className={isOpen ? 'is-open' : ''}>
                  <td className="cell-strong">{name}</td>
                  {metrics.map((m) => (
                    <td key={m}>
                      <LimitCell check={byMetric[m]} />
                    </td>
                  ))}
                  <td className="cell-source">
                    {sources.length ? (
                      sources.map((cit) => <SourceCell key={cit} citation={cit} />)
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="cell-action">
                    {rowChecks.length > 0 && (
                      <button
                        className="icon-btn"
                        onClick={() => setExpanded(isOpen ? null : name)}
                        aria-expanded={isOpen}
                        aria-label={`Evaluation details for ${name}`}
                      >
                        <ChevronDown size={16} className={isOpen ? 'rotate-180' : ''} />
                      </button>
                    )}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="detail-row">
                    <td colSpan={metrics.length + 3}>
                      <div className="eval-log">
                        {rowChecks.map((c) => (
                          <div key={c.metric_name} className="eval-log-line">
                            <span className="eval-log-metric">{humanizeMetric(c.metric_name)}</span>
                            <span>{c.reasoning}</span>
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
