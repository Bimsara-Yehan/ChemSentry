import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Filter, GitMerge, ScanSearch, ShieldCheck, Sigma } from 'lucide-react';

// The retrieval chain drawn like a process & instrumentation diagram: each
// stage is a unit operation, joined by pipes with fluid flowing through
// them. While a search is running a pulse travels stage to stage; clicking a
// stage explains the technique. Stage descriptions mirror CLAUDE.md's
// architecture, so this doubles as a viva-friendly explainer.

const STAGES = [
  {
    id: 'match',
    tag: 'T-101',
    icon: ScanSearch,
    title: 'Tolerant match',
    short: 'k-gram · Levenshtein · Soundex',
    body: 'The query is normalised by the same preprocessing as the corpus, then misspellings and variants are resolved with a 3-gram index, edit distance and phonetic codes, so "hydrogen peroxde" still finds hydrogen peroxide.',
  },
  {
    id: 'filter',
    tag: 'F-102',
    icon: Filter,
    title: 'Boolean filter',
    short: 'Inverted index · elimination',
    body: 'Candidate documents come from the hand-built inverted index. Index elimination drops documents that cannot match before any scoring, keeping lookups fast as the corpus grows.',
  },
  {
    id: 'rank',
    tag: 'R-103',
    icon: Sigma,
    title: 'TF-IDF ranking',
    short: 'Cosine similarity',
    body: 'Survivors are ranked by TF-IDF cosine similarity to the query, so the most specific Safety Data Sheet comes first.',
  },
  {
    id: 'reconcile',
    tag: 'E-104',
    icon: GitMerge,
    title: 'Reconcile evidence',
    short: 'Authority · Jaccard conflicts',
    body: 'When suppliers disagree, the source-authority hierarchy picks the governing document and Jaccard similarity flags the conflict for you to see. Nothing is silently discarded.',
  },
  {
    id: 'verdict',
    tag: 'S-105',
    icon: ShieldCheck,
    title: 'Deterministic verdict',
    short: 'SAFE · WARNING · UNKNOWN',
    body: 'A rule-based layer compares readings with the retrieved, cited limits. No LLM is on this path. Missing or conflicting evidence gives UNKNOWN, never an assumed SAFE.',
  },
];

export default function ProcessPipeline({ running = false, orientation = 'vertical' }) {
  const [active, setActive] = useState(null);
  const [pulse, setPulse] = useState(-1);

  // Walk the pulse through the stages while a query is in flight, then
  // light the whole line briefly when it completes.
  useEffect(() => {
    if (!running) {
      setPulse((p) => (p >= 0 ? STAGES.length : -1));
      const done = setTimeout(() => setPulse(-1), 1400);
      return () => clearTimeout(done);
    }
    setPulse(0);
    const t = setInterval(() => setPulse((p) => (p + 1) % STAGES.length), 380);
    return () => clearInterval(t);
  }, [running]);

  const selected = STAGES.find((s) => s.id === active);

  return (
    <div className={`pid pid-${orientation}`}>
      <ol className="pid-line">
        {STAGES.map((s, i) => {
          const Icon = s.icon;
          const lit = pulse === STAGES.length || pulse === i;
          return (
            <li key={s.id} className="pid-stage">
              {i > 0 && (
                <span className={`pid-pipe${running ? ' is-flowing' : ''}`} aria-hidden="true">
                  <span className="pid-fluid" />
                </span>
              )}
              <motion.button
                type="button"
                className={`pid-unit${lit ? ' is-lit' : ''}${active === s.id ? ' is-selected' : ''}`}
                onClick={() => setActive(active === s.id ? null : s.id)}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                aria-expanded={active === s.id}
              >
                <span className="pid-icon">
                  <Icon size={16} />
                </span>
                <span className="pid-text">
                  <span className="pid-tag">{s.tag}</span>
                  <strong>{s.title}</strong>
                  <span className="pid-short">{s.short}</span>
                </span>
              </motion.button>
            </li>
          );
        })}
      </ol>
      <AnimatePresence initial={false}>
        {selected ? (
          <motion.p
            key={selected.id}
            className="pid-explain"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
          >
            <span className="pid-tag">{selected.tag}</span> {selected.body}
          </motion.p>
        ) : (
          <motion.p key="hint" className="pid-hint" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            Select a stage for details.
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
