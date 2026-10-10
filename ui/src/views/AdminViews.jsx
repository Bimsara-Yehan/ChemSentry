import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronLeft, ChevronRight, FileUp, LoaderCircle, Plus, RefreshCw, ScrollText, ShieldCheck, TriangleAlert, Users, X } from 'lucide-react';
import { addChemicalToZone, createUser, createZone, getAuditLog, listUsers, removeChemicalFromZone, uploadSdsDocument } from '../api';
import { rise, stagger } from '../components/motionVariants';
import { EmptyState, Field, Loading, Notice, PageHeader } from '../components/ui';
import { ROLE_LABELS, zoneName, zoneSummary } from '../constants';
import { formatDateTime, humanizeAction, humanizeMetric } from '../format';

const AUDIT_PAGE = 25;

export function UsersView({ token }) {
  const [users, setUsers] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('analyst');

  const refresh = async () => {
    try {
      setUsers((await listUsers(token)) || []);
      setError('');
      setLoaded(true);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const create = async (e) => {
    e.preventDefault();
    setSuccess('');
    setError('');
    try {
      const res = await createUser(token, username, password, role);
      setSuccess(`${res.username} was added as ${ROLE_LABELS[res.role] || res.role}.`);
      setUsername('');
      setPassword('');
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Users"
        subtitle="Accounts and their access level. Only admins can close out a WARNING."
        actions={
          <button className="action-btn btn-secondary btn-sm" onClick={refresh}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />
      {error && (
        <Notice tone="error" icon={TriangleAlert} title="Something went wrong">
          {error}
        </Notice>
      )}
      <div className="dashboard-grid">
        <div className="main-col">
          <div className="card card-flush">
            {!loaded && !error && <Loading label="Loading users…" />}
            {loaded && users.length === 0 && !error && (
              <EmptyState title="No accounts yet" icon={Users}>
                Built-in demo accounts remain available until you add your own.
              </EmptyState>
            )}
            {users.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <motion.tbody variants={stagger} initial="hidden" animate="show">
                    {users.map((u) => (
                      <motion.tr key={u.user_id} variants={rise}>
                        <td>
                          <span className="user-cell">
                            <span className={`avatar avatar-sm role-${u.role}`}>{u.username.charAt(0).toUpperCase()}</span>
                            <span>
                              <span className="cell-strong">{u.username}</span>
                              <span className="cell-sub">{u.user_id}</span>
                            </span>
                          </span>
                        </td>
                        <td>
                          <span className={`role-tag role-${u.role}`}>{ROLE_LABELS[u.role] || u.role}</span>
                        </td>
                        <td>
                          <span className={`status-pill ${u.is_active ? 'status-approved' : 'status-rejected'}`}>
                            {u.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="muted">{u.created_at ? formatDateTime(u.created_at) : '—'}</td>
                      </motion.tr>
                    ))}
                  </motion.tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="side-col">
          <div className="card">
            <div className="eyebrow">Provision</div>
            <h3 className="card-heading">Add user</h3>
            <form onSubmit={create} className="form-stack">
              <Field label="Username">
                <input type="text" className="input-field" placeholder="jsmith" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </Field>
              <Field label="Password">
                <input type="password" className="input-field" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              <Field label="Role">
                <div className="role-picker" role="radiogroup">
                  {['viewer', 'analyst', 'admin'].map((r) => (
                    <button
                      type="button"
                      key={r}
                      role="radio"
                      aria-checked={role === r}
                      className={`role-option${role === r ? ' active' : ''}`}
                      onClick={() => setRole(r)}
                    >
                      {role === r && <motion.span layoutId="role-pick" className="role-option-bg" />}
                      <span>{ROLE_LABELS[r]}</span>
                    </button>
                  ))}
                </div>
              </Field>
              <button type="submit" className="action-btn btn-block">
                <Plus size={15} /> Create account
              </button>
            </form>
            {success && (
              <Notice tone="success" icon={ShieldCheck}>
                {success}
              </Notice>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

export function ZonesView({ token, zones, refreshZones }) {
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [newZoneId, setNewZoneId] = useState('');
  const [newZoneChems, setNewZoneChems] = useState('');
  const [addChem, setAddChem] = useState('');
  const [targetZone, setTargetZone] = useState('');
  // Falls back to the first zone the API reports until the admin picks one.
  const zoneForChemical = zones[targetZone] ? targetZone : Object.keys(zones).sort()[0] || '';

  const [file, setFile] = useState(null);
  const [chemName, setChemName] = useState('');
  const [supplier, setSupplier] = useState('');
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    refreshZones();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const wrap = (fn) => async (e) => {
    e?.preventDefault?.();
    setSuccess('');
    setError('');
    try {
      await fn();
      await refreshZones();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreateZone = wrap(async () => {
    const chems = newZoneChems.split(',').map((c) => c.trim()).filter(Boolean);
    await createZone(token, newZoneId, chems);
    setSuccess(`${zoneName(newZoneId)} created.`);
    setNewZoneId('');
    setNewZoneChems('');
  });

  const handleAddChemical = wrap(async () => {
    await addChemicalToZone(token, zoneForChemical, addChem);
    setSuccess(`${addChem} added to ${zoneName(zoneForChemical)}.`);
    setAddChem('');
  });

  const removeChemical = (zoneId, chem) =>
    wrap(async () => {
      await removeChemicalFromZone(token, zoneId, chem);
      setSuccess(`${chem} removed from ${zoneName(zoneId)}.`);
    })();

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setSuccess('');
    setError('');
    try {
      const res = await uploadSdsDocument(token, file, chemName, supplier);
      setSuccess(`${res.chemical_name} (SDS ${res.document_id}) extracted and indexed.`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = '';
      setChemName('');
      setSupplier('');
      await refreshZones();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && (f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))) setFile(f);
    else setError('Only PDF Safety Data Sheets can be uploaded.');
  };

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Zones & documents"
        subtitle="Manage storage-zone inventories and feed new Safety Data Sheets into the corpus."
        actions={
          <button className="action-btn btn-secondary btn-sm" onClick={() => refreshZones()}>
            <RefreshCw size={14} /> Refresh
          </button>
        }
      />
      {error && (
        <Notice tone="error" icon={TriangleAlert} title="Something went wrong">
          {error}
        </Notice>
      )}
      {success && (
        <Notice tone="success" icon={ShieldCheck}>
          {success}
        </Notice>
      )}
      <div className="dashboard-grid">
        <motion.div className="main-col" variants={stagger} initial="hidden" animate="show">
          {Object.entries(zones).map(([zId, zData]) => (
            <motion.div key={zId} className={`card zone-admin zone-${zData.safety_state}`} variants={rise}>
              <div className="card-head">
                <div>
                  <div className="eyebrow">{zoneName(zId)}</div>
                  <h3 className="card-heading">{zoneSummary(zData.chemicals)}</h3>
                </div>
                <span className="muted">
                  {(zData.chemicals || []).length} chemical{(zData.chemicals || []).length === 1 ? '' : 's'}
                </span>
              </div>
              <motion.div className="chip-list" layout>
                {(zData.chemicals || []).length === 0 && <span className="muted">No chemicals assigned.</span>}
                <AnimatePresence>
                  {(zData.chemicals || []).map((chem) => (
                    <motion.span
                      key={chem}
                      className="chip"
                      layout
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                    >
                      {chem}
                      <button
                        className="chip-remove"
                        onClick={() => removeChemical(zId, chem)}
                        aria-label={`Remove ${chem} from ${zoneName(zId)}`}
                        title="Remove"
                      >
                        <X size={13} />
                      </button>
                    </motion.span>
                  ))}
                </AnimatePresence>
              </motion.div>
            </motion.div>
          ))}
        </motion.div>

        <div className="side-col">
          <div className="card">
            <div className="eyebrow">Corpus intake</div>
            <h3 className="card-heading">Upload SDS</h3>
            <p className="card-sub">Sections are split, limits extracted with regex and the document is indexed on upload.</p>
            <form onSubmit={upload} className="form-stack">
              <label
                className={`dropzone${file ? ' has-file' : ''}${dragOver ? ' is-over' : ''}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
              >
                <input ref={fileRef} type="file" accept=".pdf,application/pdf" onChange={(e) => setFile(e.target.files[0] || null)} />
                <motion.span className="dropzone-icon" animate={dragOver ? { y: -4, scale: 1.1 } : { y: 0, scale: 1 }}>
                  <FileUp size={22} aria-hidden="true" />
                </motion.span>
                <span className="dropzone-title">{file ? file.name : 'Drop a PDF here or browse'}</span>
                <span className="dropzone-hint">{file ? `${(file.size / 1024).toFixed(0)} KB` : 'Safety Data Sheet, .pdf'}</span>
                {uploading && <span className="dropzone-progress" />}
              </label>
              <Field label="Chemical name" hint="Optional, detected from Section 1">
                <input type="text" className="input-field" value={chemName} onChange={(e) => setChemName(e.target.value)} />
              </Field>
              <Field label="Supplier" hint="Optional, detected from Section 1">
                <input type="text" className="input-field" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
              </Field>
              <button type="submit" className="action-btn btn-block btn-glow" disabled={uploading || !file}>
                {uploading ? (
                  <>
                    <LoaderCircle size={15} className="spin" /> Extracting &amp; indexing
                  </>
                ) : (
                  <>
                    <FileUp size={15} /> Upload to corpus
                  </>
                )}
              </button>
            </form>
          </div>

          <div className="card">
            <div className="eyebrow">Inventory</div>
            <h3 className="card-heading">Add chemical</h3>
            <form onSubmit={handleAddChemical} className="form-stack">
              <Field label="Zone">
                <select className="input-field" value={zoneForChemical} onChange={(e) => setTargetZone(e.target.value)}>
                  {Object.keys(zones).map((zId) => (
                    <option key={zId} value={zId}>
                      {zoneName(zId)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Chemical name">
                <input type="text" className="input-field" placeholder="Isopropanol" value={addChem} onChange={(e) => setAddChem(e.target.value)} required />
              </Field>
              <button type="submit" className="action-btn btn-block">
                <Plus size={15} /> Add to zone
              </button>
            </form>
          </div>

          <div className="card">
            <div className="eyebrow">Inventory</div>
            <h3 className="card-heading">New zone</h3>
            <form onSubmit={handleCreateZone} className="form-stack">
              <Field label="Zone ID">
                <input type="text" className="input-field" placeholder="Zone_D" value={newZoneId} onChange={(e) => setNewZoneId(e.target.value)} required />
              </Field>
              <Field label="Chemicals" hint="Comma-separated, optional">
                <input type="text" className="input-field" placeholder="Acetone, Methanol" value={newZoneChems} onChange={(e) => setNewZoneChems(e.target.value)} />
              </Field>
              <button type="submit" className="action-btn btn-secondary btn-block">
                Create zone
              </button>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}

const DETAIL_LABELS = { zone_id: '', chemical_name: 'Chemical', metric_name: 'Metric' };

function formatDetailValue(key, value) {
  if (value == null || value === '') return '—';
  if (Array.isArray(value)) return value.length ? value.map((v) => humanizeMetric(String(v))).join(', ') : '—';
  if (typeof value === 'object') {
    const parts = Object.entries(value).map(([k, v]) => `${humanizeMetric(k)}: ${v}`);
    return parts.length ? parts.join(' · ') : '—';
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (key === 'zone_id') return zoneName(String(value));
  if (key === 'metric_name') return humanizeMetric(String(value));
  // A full SHA-256 is unreadable inline; the first 12 hex chars identify the
  // file, and the full value is kept in the tooltip.
  if (key === 'sha256') return `${String(value).slice(0, 12)}…`;
  return String(value);
}

export function AuditView({ token }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');

  const load = async (off) => {
    try {
      const res = await getAuditLog(token, AUDIT_PAGE, off);
      setLogs(res?.entries || []);
      setTotal(res?.total || 0);
      setOffset(off);
      setError('');
      setLoaded(true);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <>
      <PageHeader
        eyebrow="Compliance"
        title="Audit trail"
        subtitle="Every system action and sign-off, newest first. Append-only and encrypted at rest."
        actions={
          <div className="pager">
            <span className="muted">
              {total === 0 ? '0' : `${offset + 1}–${Math.min(offset + AUDIT_PAGE, total)}`} of {total}
            </span>
            <button className="icon-btn icon-btn-bordered" disabled={offset === 0} onClick={() => load(Math.max(0, offset - AUDIT_PAGE))} aria-label="Previous page">
              <ChevronLeft size={16} />
            </button>
            <button className="icon-btn icon-btn-bordered" disabled={offset + AUDIT_PAGE >= total} onClick={() => load(offset + AUDIT_PAGE)} aria-label="Next page">
              <ChevronRight size={16} />
            </button>
          </div>
        }
      />
      {error && (
        <Notice tone="error" icon={TriangleAlert} title="Couldn't load the audit trail">
          {error}
        </Notice>
      )}
      <div className="card card-flush">
        {!loaded && !error && <Loading label="Loading audit trail…" />}
        {loaded && logs.length === 0 && !error && <EmptyState title="No entries yet" icon={ScrollText} />}
        {logs.length > 0 && (
          <ol className="timeline" key={offset}>
            {logs.map((log, i) => (
              <motion.li
                key={log.id}
                className="timeline-item"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: Math.min(i * 0.025, 0.5) }}
              >
                <span className="timeline-node" aria-hidden="true" />
                <div className="timeline-body">
                  <div className="timeline-head">
                    <span className="action-tag">{humanizeAction(log.action)}</span>
                    <span className="timeline-user">{log.user_id}</span>
                    {log.resource && <span className="mono muted">{log.resource}</span>}
                    <span className="timeline-time">{formatDateTime(log.timestamp)}</span>
                  </div>
                  {log.details && (
                    <div className="cell-details">
                      {typeof log.details === 'object'
                        ? Object.entries(log.details).map(([k, v]) => (
                            <span key={k} className="kv">
                              {DETAIL_LABELS[k] !== '' && <span className="kv-key">{DETAIL_LABELS[k] || humanizeMetric(k)}</span>}
                              <span title={typeof v === 'string' ? v : undefined}>{formatDetailValue(k, v)}</span>
                            </span>
                          ))
                        : log.details}
                    </div>
                  )}
                </div>
              </motion.li>
            ))}
          </ol>
        )}
      </div>
    </>
  );
}
