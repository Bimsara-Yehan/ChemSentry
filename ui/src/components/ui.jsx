import { CircleCheck, CircleHelp, TriangleAlert, LoaderCircle, Inbox } from 'lucide-react';
import { parseCitation } from '../format';

export function SourceCell({ citation, fallback }) {
  const c = parseCitation(citation);
  if (!c) return fallback ? <span>{fallback}</span> : <span className="muted">—</span>;
  if (!c.docId) return <span title={c.raw}>{c.raw}</span>;
  return (
    <span className="source" title={c.raw}>
      <span className="source-supplier">{c.supplier}</span>
      <span className="cell-sub">
        SDS {c.docId} · §{c.section}
      </span>
    </span>
  );
}

const STATE_ICONS = {
  SAFE: CircleCheck,
  WARNING: TriangleAlert,
  UNKNOWN: CircleHelp,
};

export function StateBadge({ state, size = 'md' }) {
  const Icon = STATE_ICONS[state] || CircleHelp;
  return (
    <span className={`state-badge state-${state} state-badge-${size}`}>
      <Icon size={size === 'lg' ? 15 : 12} strokeWidth={2.4} aria-hidden="true" />
      {state}
    </span>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="page-header">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}

export function Loading({ label }) {
  return (
    <div className="loading-state">
      <LoaderCircle size={16} className="spin" aria-hidden="true" />
      {label}
    </div>
  );
}

export function EmptyState({ title, children, icon: Icon = Inbox }) {
  return (
    <div className="empty-state">
      <Icon size={22} aria-hidden="true" />
      <div className="empty-state-title">{title}</div>
      {children && <div className="empty-state-body">{children}</div>}
    </div>
  );
}

export function Notice({ tone = 'info', title, children, icon: Icon }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      {Icon && <Icon size={16} className="notice-icon" aria-hidden="true" />}
      <div>
        {title && <div className="notice-title">{title}</div>}
        {children && <div className="notice-body">{children}</div>}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}
