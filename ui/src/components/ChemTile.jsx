import { motion } from 'motion/react';
import { rise } from './motion';

// Periodic-table-style tile for a stored chemical. The symbol is just the
// name's initials (a display mark, not a chemical formula), and the limit
// line is the SDS-retrieved limit passed in by the caller.
function symbolFor(name) {
  const words = name.replace(/^[\d,-]+/, '').trim().split(/[\s-]+/).filter(Boolean);
  if (words.length >= 2) return words[0][0].toUpperCase() + words[1][0].toLowerCase();
  const w = words[0] || name;
  return w.charAt(0).toUpperCase() + (w.charAt(1) || '').toLowerCase();
}

export default function ChemTile({ index, name, state = 'UNKNOWN', limitText, onClick, selected }) {
  return (
    <motion.button
      type="button"
      variants={rise}
      className={`chem-tile tile-${state}${selected ? ' is-selected' : ''}`}
      onClick={onClick}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.97 }}
      layout
    >
      <span className="chem-tile-index">{String(index).padStart(2, '0')}</span>
      <span className="chem-tile-state" aria-label={state} />
      <span className="chem-tile-symbol">{symbolFor(name)}</span>
      <span className="chem-tile-name">{name}</span>
      <span className="chem-tile-limit">{limitText}</span>
    </motion.button>
  );
}
