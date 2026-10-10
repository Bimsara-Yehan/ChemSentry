import { motion } from 'motion/react';
import { CircleCheck, CircleHelp, Inbox, TriangleAlert } from 'lucide-react';
import { parseCitation } from '../format';
import Flask from './Flask';

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
      {state === 'WARNING' && <span className="state-ping" aria-hidden="true" />}
      <Icon size={size === 'lg' ? 15 : 12} strokeWidth={2.4} aria-hidden="true" />
      {state}
    </span>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <motion.div
      className="page-header"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 240, damping: 26 }}
    >
      <div>
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </motion.div>
  );
}

export function Loading({ label }) {
  return (
    <div className="loading-state">
      <Flask size={44} level={0.5} />
      {label}
    </div>
  );
}

export function EmptyState({ title, children, icon: Icon = Inbox }) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon size={22} aria-hidden="true" />
      </span>
      <div className="empty-state-title">{title}</div>
      {children && <div className="empty-state-body">{children}</div>}
    </div>
  );
}

export function Notice({ tone = 'info', title, children, icon: Icon }) {
  return (
    <motion.div
      className={`notice notice-${tone}`}
      role={tone === 'error' ? 'alert' : undefined}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {Icon && <Icon size={16} className="notice-icon" aria-hidden="true" />}
      <div>
        {title && <div className="notice-title">{title}</div>}
        {children && <div className="notice-body">{children}</div>}
      </div>
    </motion.div>
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

export function Card({ children, className = '', ...rest }) {
  return (
    <div className={`card ${className}`} {...rest}>
      {children}
    </div>
  );
}
