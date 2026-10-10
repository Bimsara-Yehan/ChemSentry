import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { FileText, GitMerge, LoaderCircle, Search, TriangleAlert } from 'lucide-react';
import { queryChemical } from '../api';
import ProcessPipeline from '../components/ProcessPipeline';
import { rise, stagger } from '../components/motionVariants';
import { EmptyState, Notice, PageHeader, SourceCell, StateBadge } from '../components/ui';
import { formatValue, humanizeMetric } from '../format';

export default function SearchView({ token, isViewer, suggestions }) {
  const [query, setQuery] = useState('Ethanol');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const run = async (name) => {
    const q = (name ?? query).trim();
    if (!q) return;
    setQuery(q);
    setLoading(true);
    setError('');
    try {
      setResult(await queryChemical(token, q));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Information retrieval"
        title="SDS search"
        subtitle="Look up a chemical's retrieved storage limits and the exact documents they came from."
      />
      <div className="dashboard-grid">
        <div className="main-col">
          <div className="card search-card">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                run();
              }}
              className="search-bar"
            >
              <span className="input-with-icon search-input">
                <Search size={18} aria-hidden="true" />
                <input
                  type="text"
                  className="input-field"
                  placeholder="Chemical name, e.g. Ethanol"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={isViewer}
                  aria-label="Chemical name"
                />
              </span>
              <motion.button type="submit" className="action-btn btn-glow" disabled={isViewer || loading} whileTap={{ scale: 0.96 }}>
                {loading ? <LoaderCircle size={15} className="spin" /> : <Search size={15} />}
                Retrieve
              </motion.button>
            </form>
            {suggestions.length > 0 && !isViewer && (
              <div className="suggestion-row">
                <span className="muted small">Inventory:</span>
                {suggestions.slice(0, 8).map((s) => (
                  <button key={s} type="button" className="chip-btn" onClick={() => run(s)} disabled={loading}>
                    {s}
                  </button>
                ))}
              </div>
            )}
            {isViewer && <p className="help-text">Search requires an analyst or admin role.</p>}
          </div>

          {error && (
            <Notice tone="error" icon={TriangleAlert} title="Search failed">
              {error}
            </Notice>
          )}

          <AnimatePresence initial={false}>
            {result && !loading && (
              <motion.div
                key={result.query.chemical_name + result.evidence.thresholds.length}
                className="card"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
              >
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Retrieved evidence</div>
                    <h3 className="card-heading">{result.query.chemical_name}</h3>
                  </div>
                  <span className="lookup-tag" title="A search has no sensor reading, so no SAFE/WARNING verdict is made.">
                    <StateBadge state={result.evidence.final_safety_state} size="sm" />
                    Lookup only
                  </span>
                </div>

                {result.evidence.thresholds.length === 0 && result.evidence.suggested_chemical ? (
                  // Limits only come from an exact name match, so a near-miss
                  // is offered here rather than searched automatically: the
                  // closest spelling can be a different substance (Methanol
                  // -> Ethanol), and its limits must not appear under this name.
                  <EmptyState title="No SDS under this name" icon={FileText}>
                    <p>
                      Did you mean{' '}
                      <button type="button" className="chip-btn" onClick={() => run(result.evidence.suggested_chemical)}>
                        {result.evidence.suggested_chemical}
                      </button>
                      ?
                    </p>
                    <p className="muted small">
                      Only search it if it is the same substance. Otherwise upload this chemical&apos;s SDS under
                      Zones &amp; documents.
                    </p>
                  </EmptyState>
                ) : result.evidence.thresholds.length === 0 ? (
                  <EmptyState title="No limits found" icon={FileText}>
                    The current corpus has no storage limits for this name. Upload its SDS under Zones &amp; documents.
                  </EmptyState>
                ) : (
                  <motion.div className="evidence-grid" variants={stagger} initial="hidden" animate="show">
                    {result.evidence.thresholds.map((t, idx) => (
                      <motion.div key={idx} className="evidence-card" variants={rise}>
                        <span className="evidence-param">{humanizeMetric(t.parameter)}</span>
                        <span className="evidence-value">{formatValue(t.value, t.unit)}</span>
                        <span className="evidence-source">
                          <SourceCell citation={t.version} fallback={t.source_doc_id} />
                        </span>
                      </motion.div>
                    ))}
                  </motion.div>
                )}

                {result.evidence.conflicts.map((conflict, idx) => (
                  <Notice key={idx} tone="warning" icon={GitMerge} title="Supplier conflict">
                    {conflict}
                  </Notice>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="side-col">
          <div className="card">
            <div className="eyebrow">Process flow</div>
            <h3 className="card-heading">Retrieval pipeline</h3>
            <ProcessPipeline running={loading} />
          </div>
        </div>
      </div>
    </>
  );
}
