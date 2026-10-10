import { motion } from 'motion/react';
import { FlaskConical } from 'lucide-react';
import { rise } from './motionVariants';

// Tile for a stored chemical: an icon tinted by the chemical's own check
// state, its name, and the SDS-retrieved limit passed in by the caller.
// Deliberately no letter "symbol": initials such as "Ca" or "Ac" read as real
// element symbols (calcium, actinium) and would misidentify the substance.
export default function ChemTile({ name, state = 'UNKNOWN', limitText, onClick, selected }) {
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
      <span className="chem-tile-icon" aria-hidden="true">
        <FlaskConical size={18} strokeWidth={2} />
      </span>
      <span className="chem-tile-state" aria-label={state} />
      <span className="chem-tile-name">{name}</span>
      <span className="chem-tile-limit">{limitText}</span>
    </motion.button>
  );
}
