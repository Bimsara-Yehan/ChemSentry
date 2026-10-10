import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Network } from 'lucide-react';
import { getCoStorageCheck } from '../api';
import { rise, stagger } from './motion';

// Agent B co-storage analysis for one zone (M3). Apriori only finds which
// chemicals are stored together; whether a pair is a reactivity concern comes
// from Agent B's reactivity lookup on the backend
// (agents/agent_b_analysis/apriori_discovery.py). The panel shows both,
// labelled as such, and never presents a mined pattern as a verdict.

// The label is the backend's own status prefix ("VIOLENT REACTION",
// "COMPATIBLE", ...), shown as-is; only its colour is chosen here.
function classify(status = '') {
  const prefix = (status.split(':')[0] || 'UNCLASSIFIED').trim();
  const s = prefix.toUpperCase();
  let tone = 'warning';
  if (s.startsWith('COMPATIBLE')) tone = 'safe';
  else if (/VIOLENT|TOXIC|EXPLOSIVE/.test(s)) tone = 'danger';
  const label = prefix.charAt(0) + prefix.slice(1).toLowerCase();
  return { tone, label };
}

// A rule and its mirror image (A→B, B→A) describe the same pair; show it once.
function dedupe(rules) {
  const seen = new Map();
  for (const r of rules) {
    const key = [...r.antecedents, ...r.consequents].sort().join(' + ');
    if (!seen.has(key) || r.confidence > seen.get(key).confidence) seen.set(key, { ...r, key });
  }
  return [...seen.values()];
}

export default function CoStoragePanel({ token, zoneId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError('');
    getCoStorageCheck(token, zoneId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [token, zoneId]);

  const pairs = data ? dedupe(data.rules) : [];

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <div className="eyebrow">Agent B · co-storage</div>
          <h3 className="card-heading">Storage compatibility</h3>
        </div>
        <Network size={18} className="muted" aria-hidden="true" />
      </div>
      <p className="card-sub">
        Apriori finds chemicals stored together across the site. Each pair is then checked against Agent B's
        reactivity lookup.
      </p>

      {error && <p className="help-text">{error}</p>}
      {!data && !error && <p className="help-text">Analysing inventory…</p>}
      {data && pairs.length === 0 && (
        <p className="help-text">No recurring co-storage pattern involves this zone's inventory.</p>
      )}

      {pairs.length > 0 && (
        <motion.ul className="pair-list" variants={stagger} initial="hidden" animate="show">
          {pairs.map((p) => {
            const c = classify(p.incompatibility_status);
            const detail = p.incompatibility_status.replace(/^[A-Z ]+:\s*/, '');
            return (
              <motion.li key={p.key} className={`pair pair-${c.tone}`} variants={rise}>
                <div className="pair-head">
                  <span className="pair-names">{p.key}</span>
                  <span className={`pair-tag pair-tag-${c.tone}`}>{c.label}</span>
                </div>
                {p.evidence?.length > 0 ? (
                  <ul className="pair-evidence">
                    {p.evidence.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                ) : (
                  c.tone !== 'safe' && <p className="pair-detail">{detail}</p>
                )}
                <div className="pair-metrics">
                  <span>support {p.support.toFixed(2)}</span>
                  <span>confidence {p.confidence.toFixed(2)}</span>
                  <span>lift {p.lift.toFixed(2)}</span>
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}
    </div>
  );
}
