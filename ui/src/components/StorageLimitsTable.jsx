import { Fragment, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { SourceCell, StateBadge } from './ui';
import { citationLabel, formatValue, humanizeMetric } from '../format';

// min_* before max_* so a row reads as a range left to right.
function metricOrder(a, b) {
  const rank = (m) => (m.startsWith('min_') ? 0 : m.startsWith('max_') ? 1 : 2);
  return rank(a) - rank(b) || a.localeCompare(b);
}

// Display-only regrouping of the API's per-(chemical, metric) checks. The
// limit is the threshold the backend retrieved for that check; the badge is
// the backend's own verdict. The table never derives a verdict itself.
function group(chemicals, limits, checks) {
  const metrics = [...new Set([...limits, ...checks].map((x) => x.metric_name))].sort(metricOrder);
  const rows = new Map(chemicals.map((name) => [name, { limits: {}, checks: {} }]));
  const row = (name) => {
    if (!rows.has(name)) rows.set(name, { limits: {}, checks: {} });
    return rows.get(name);
  };
  for (const l of limits) row(l.chemical_name).limits[l.metric_name] = l;
  for (const c of checks) row(c.chemical_name).checks[c.metric_name] = c;
  return { metrics, rows: [...rows.entries()] };
}

function LimitCell({ limit, check }) {
  if (!limit && !check) return <span className="muted">Not in SDS</span>;
  return (
    <span className="limit-cell">
      {check && <StateBadge state={check.state} size="sm" />}
      {limit ? (
        <span className="limit-value">{formatValue(limit.value, limit.unit)}</span>
      ) : (
        <span className="muted">Not in SDS</span>
      )}
    </span>
  );
}

export default function StorageLimitsTable({ chemicals = [], limits = [], checks = [] }) {
  const [expanded, setExpanded] = useState(null);
  const { metrics, rows } = group(chemicals, limits, checks);

  if (rows.length === 0) {
    return <p className="muted">No chemicals are assigned to this zone.</p>;
  }
  if (metrics.length === 0) {
    return <p className="muted">No storage-temperature limit for these chemicals is in the SDS corpus.</p>;
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
          {rows.map(([name, data]) => {
            const rowChecks = Object.values(data.checks);
            const seen = new Set();
            const sources = Object.values(data.limits)
              .map((l) => l.citation)
              .filter((cit) => cit && !seen.has(citationLabel(cit)) && seen.add(citationLabel(cit)));
            const isOpen = expanded === name;
            return (
              <Fragment key={name}>
                <tr className={isOpen ? 'is-open' : ''}>
                  <td className="cell-strong">{name}</td>
                  {metrics.map((m) => (
                    <td key={m}>
                      <LimitCell limit={data.limits[m]} check={data.checks[m]} />
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
