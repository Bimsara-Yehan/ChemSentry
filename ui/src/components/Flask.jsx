import { useId } from 'react';
import { motion, useReducedMotion } from 'motion/react';

// Erlenmeyer flask with a sloshing liquid surface and rising bubbles. Used
// as the brand illustration on the login screen and as a loader. The liquid
// is a wide wave path clipped to the flask silhouette and translated
// sideways, so the surface ripples without any per-frame JS.

const FLASK_PATH =
  'M44 6 h32 v6 h-4 v30 l34 58 a10 10 0 0 1 -8.6 15 H22.6 A10 10 0 0 1 14 100 l34 -58 V12 h-4 z';

const BUBBLES = [
  { cx: 48, r: 3.2, delay: 0, dur: 2.6 },
  { cx: 62, r: 2.2, delay: 0.7, dur: 2.2 },
  { cx: 72, r: 2.8, delay: 1.4, dur: 2.9 },
  { cx: 55, r: 1.8, delay: 1.9, dur: 2.0 },
  { cx: 80, r: 1.6, delay: 0.4, dur: 2.4 },
];

export default function Flask({ size = 120, level = 0.55, tone = 'teal', className = '' }) {
  const id = useId().replace(/:/g, '');
  const reduce = useReducedMotion();
  const surfaceY = 112 - level * 70;

  return (
    <svg
      className={`flask flask-${tone} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      aria-hidden="true"
    >
      <defs>
        <clipPath id={`clip-${id}`}>
          <path d={FLASK_PATH} />
        </clipPath>
        <linearGradient id={`liq-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="flask-liquid-top" />
          <stop offset="100%" className="flask-liquid-bottom" />
        </linearGradient>
      </defs>

      <g clipPath={`url(#clip-${id})`}>
        <motion.path
          d={`M-120 ${surfaceY} q15 -6 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 V130 H-120 z`}
          fill={`url(#liq-${id})`}
          animate={reduce ? undefined : { x: [0, 60] }}
          transition={{ duration: 3.2, ease: 'linear', repeat: Infinity }}
        />
        <motion.path
          d={`M-120 ${surfaceY + 3} q15 5 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 V130 H-120 z`}
          className="flask-liquid-back"
          animate={reduce ? undefined : { x: [60, 0] }}
          transition={{ duration: 4.4, ease: 'linear', repeat: Infinity }}
        />
        {!reduce &&
          BUBBLES.map((b, i) => (
            <motion.circle
              key={i}
              cx={b.cx}
              r={b.r}
              className="flask-bubble"
              initial={{ cy: 108, opacity: 0 }}
              animate={{ cy: [108, surfaceY + 4], opacity: [0, 0.9, 0] }}
              transition={{ duration: b.dur, delay: b.delay, repeat: Infinity, ease: 'easeIn' }}
            />
          ))}
      </g>

      <path d={FLASK_PATH} className="flask-glass" />
      <path d="M52 50 l-20 34" className="flask-shine" />
      {[0.25, 0.45, 0.65].map((f) => (
        <line key={f} x1="70" x2="78" y1={112 - f * 70} y2={112 - f * 70} className="flask-tick" />
      ))}
    </svg>
  );
}
