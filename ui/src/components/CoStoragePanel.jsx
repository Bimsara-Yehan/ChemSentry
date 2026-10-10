import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Network } from 'lucide-react';
import { getCoStorageCheck } from '../api';
import { rise, stagger } from './motionVariants';

// Agent B co-storage analysis for one zone (M3). Apriori only finds which
// chemicals are stored together; whether a pair is a reactivity concern comes
// from Agent B's reactivity lookup on the backend
// (agents/agent_b_analysis/apriori_discovery.py). The panel shows both,
// labelled as such, and never presents a mined pattern as a verdict.

// Colour for the backend's status prefix ("VIOLENT REACTION", "REACTIVE",
// "REVIEW", "NO KNOWN WARNING"). "NO KNOWN WARNING" means neither SDS's
// Section 10 names the other chemical or a class it belongs to -- not "safe
// to store together" -- so it is shown neutral, never green: an absence of
// evidence must not look like a safety verdict (CLAUDE.md). "COMPATIBLE" is
// the older backend's word for the same thing.
function classify(status = '') {
  const prefix = (status.split(':')[0] || 'UNCLASSIFIED').trim();
  const s = prefix.toUpperCase();
  if (s.startsWith('NO KNOWN WARNING') || s.startsWith('COMPATIBLE')) {
    return { tone: 'neutral', label: 'No known warning on file' };
  }
  // REACTIVE means an SDS names the other chemical as incompatible -- the
  // strongest evidence the SDS path gives -- so it shares the danger tone.
  // REVIEW (a class match a person must confirm) stays amber.
  const tone = /VIOLENT|TOXIC|EXPLOSIVE|REACTIVE/.test(s) ? 'danger' : 'warning';
  return { tone, label: prefix.charAt(0) + prefix.slice(1).toLowerCase() };
}

// Pairs only, each shown once (A→B and B→A are the same pair). A group of
// three or more is labelled from one of its flagged pairs, and every pair of
// it is already listed on its own, so larger groups would only repeat a row.
function pairsOnly(rules) {
  const seen = new Map();
  for (const r of rules) {
    const members = [...r.antecedents, ...r.consequents];
    if (members.length !== 2) continue;
    const key = [...members].sort().join(' + ');
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

  const pairs = data ? pairsOnly(data.rules) : [];

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
        reactivity lookup. A pair the lookup doesn't list is shown as having no known warning, which is not a
        confirmation that it is safe.
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
                <p className="pair-detail">{detail}</p>
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
