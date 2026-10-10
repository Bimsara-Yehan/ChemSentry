import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Languages, LoaderCircle } from 'lucide-react';
import { narrateAlert } from '../api';
import { StateBadge } from './ui';

// Agent B safety card: a plain-language explanation of an alert, optionally
// translated for floor staff. The LLM only explains a verdict that was
// already decided. The badge shown here always comes from the stored
// deterministic result, never from generated text.

const LANGUAGES = [
  { code: '', label: 'English' },
  { code: 'si', label: 'සිංහල' },
  { code: 'ta', label: 'தமிழ்' },
];

const FALLBACK_PREFIX = 'FALLBACK:';
const UNTRANSLATED_PREFIX = '[Translation Unavailable]';

export default function SafetyCard({ token, alertId }) {
  const [language, setLanguage] = useState('');
  const [card, setCard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const generate = async () => {
    setLoading(true);
    setError('');
    try {
      setCard(await narrateAlert(token, alertId, language || undefined));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const llmOffline = card?.explanation?.startsWith(FALLBACK_PREFIX);
  const explanation = llmOffline
    ? card.explanation.slice(FALLBACK_PREFIX.length).replace(/^\s*The safety state is \w+\.\s*/, '')
    : card?.explanation;
  const translated = card?.translation?.reasoning;
  const translationOffline = translated?.startsWith(UNTRANSLATED_PREFIX);

  return (
    <div className="safety-card">
      <div className="safety-card-bar">
        <span className="safety-card-title">
          <Languages size={15} aria-hidden="true" /> Safety card
        </span>
        <div className="lang-switch" role="radiogroup" aria-label="Card language">
          {LANGUAGES.map((l) => (
            <button
              key={l.code || 'en'}
              type="button"
              role="radio"
              aria-checked={language === l.code}
              className={`lang-option${language === l.code ? ' active' : ''}`}
              onClick={() => setLanguage(l.code)}
            >
              {l.label}
            </button>
          ))}
        </div>
        <button type="button" className="action-btn btn-secondary btn-sm" onClick={generate} disabled={loading}>
          {loading && <LoaderCircle size={14} className="spin" />}
          {card ? 'Regenerate' : 'Generate'}
        </button>
      </div>

      {error && <p className="help-text">{error}</p>}

      <AnimatePresence>
        {card && (
          <motion.div
            className="safety-card-body"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <div className="safety-card-verdict">
              <StateBadge state={card.safety_state} size="sm" />
              <span className="muted small">Verdict from the deterministic safety layer</span>
            </div>
            <p>{explanation}</p>
            {translated && !translationOffline && <p className="safety-card-translation">{translated}</p>}
            {(llmOffline || translationOffline) && (
              <p className="help-text">
                Language service unavailable (no MISTRAL_API_KEY configured). Showing the deterministic reasoning
                instead.
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
