const METRIC_LABELS = {
  max_storage_temperature: 'Max storage temp',
  min_storage_temperature: 'Min storage temp',
  temperature_max: 'Max temperature',
  humidity_max: 'Max humidity',
};

export function humanizeMetric(metric) {
  if (!metric) return '';
  if (METRIC_LABELS[metric]) return METRIC_LABELS[metric];
  const words = metric.replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// "alert_created" -> "Alert created"; acronyms such as SDS stay upper-case.
const ACRONYMS = new Set(['sds', 'cas', 'id']);

export function humanizeAction(action) {
  if (!action) return '';
  const words = action.split('_').map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w));
  const text = words.join(' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatUnit(unit) {
  if (unit === 'C' || unit === 'c') return '°C';
  if (unit === 'F' || unit === 'f') return '°F';
  return unit || '';
}

export function formatValue(value, unit) {
  if (value == null) return '—';
  return `${value} ${formatUnit(unit)}`.trim();
}

// Citations arrive as one string ("[216763] Section 7 - Sigma-Aldrich Chemie
// GmbH: ...") from the reconciler. Split it for display only; anything that
// doesn't match falls back to the raw text so a citation is never hidden.
const CITATION_RE = /^\[([^\]]+)\]\s*Section\s+(\d+)\s*-\s*([^:]+):/;

export function parseCitation(citation) {
  if (!citation) return null;
  const m = CITATION_RE.exec(citation);
  if (!m) return { raw: citation };
  return { docId: m[1], section: m[2], supplier: m[3].trim(), raw: citation };
}

export function citationLabel(citation) {
  const c = parseCitation(citation);
  if (!c) return null;
  if (!c.docId) return c.raw;
  return `${c.supplier} · SDS ${c.docId} · §${c.section}`;
}

// ChemicalCheckOut carries no unit field; the citation string does
// ("... threshold = 8.0 C"), so prefer it over guessing from the metric name.
export function unitForCheck(check) {
  const m = /=\s*-?[\d.]+\s*([^\s\]]+)\s*$/.exec(check?.citation || '');
  if (m) return formatUnit(m[1]);
  const metric = check?.metric_name || '';
  if (metric.includes('temperature')) return '°C';
  if (metric.includes('humidity')) return '%';
  return '';
}

// Alert and audit timestamps come back from SQLite as naive UTC strings
// ("2026-10-10T11:44:56") with no offset. `new Date()` would read those as
// *local* time, shifting every alert by the viewer's UTC offset (5.5 h in
// Sri Lanka). Treat an offset-less ISO string as UTC; strings that already
// carry "Z" or "+hh:mm" are left alone.
export function parseTimestamp(iso) {
  if (!iso) return null;
  const s = String(iso);
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/i.test(s);
  return new Date(hasZone || !s.includes('T') ? s : `${s}Z`);
}

export function timeAgo(iso, nowMs = Date.now()) {
  if (!iso) return '';
  const then = parseTimestamp(iso).getTime();
  if (Number.isNaN(then)) return '';
  const s = Math.max(0, Math.round((nowMs - then) / 1000));
  if (s < 45) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  return parseTimestamp(iso).toLocaleDateString();
}

export function formatDateTime(iso) {
  if (!iso) return '—';
  const d = parseTimestamp(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
