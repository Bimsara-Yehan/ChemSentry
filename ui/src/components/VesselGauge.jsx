import { useId } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { AnimatedNumber } from './motion';

// Storage-vessel gauge: the liquid level tracks the zone's latest temperature
// reading. Limit lines are drawn ONLY from thresholds the backend retrieved
// from an SDS (passed in via `limits`) -- nothing here is a hardcoded safety
// value. The scale is purely a display range wrapped around the reading and
// whatever limits exist, so the picture never implies a limit that isn't
// on file.

const TOP = 18;
const BOTTOM = 206;

// Axis bounds wrapped around whatever is actually known (the reading and the
// retrieved limits), padded so neither sits on the edge. With nothing known
// the axis just spans 0-40 so the empty vessel still has a scale.
function scaleFor(value, limits) {
  const pts = [value, ...limits.map((l) => l.value)].filter((v) => v != null);
  const lo = Math.floor(Math.min(0, ...pts) - 5);
  const hi = Math.ceil(Math.max(40, ...pts) + 5);
  return { lo, hi };
}

export default function VesselGauge({ value, unit = '°C', state = 'UNKNOWN', limits = [] }) {
  const id = useId().replace(/:/g, '');
  const reduce = useReducedMotion();
  const { lo, hi } = scaleFor(value, limits);
  const y = (v) => BOTTOM - ((v - lo) / (hi - lo)) * (BOTTOM - TOP);
  const surface = value == null ? BOTTOM : y(value);
  const ticks = [];
  const stepSize = hi - lo > 60 ? 20 : 10;
  for (let t = Math.ceil(lo / stepSize) * stepSize; t <= hi; t += stepSize) ticks.push(t);

  return (
    <div className={`vessel vessel-${state}`}>
      <svg viewBox="0 0 150 224" className="vessel-svg" role="img" aria-label={`Temperature ${value ?? 'unknown'} ${unit}`}>
        <defs>
          <clipPath id={`v-${id}`}>
            <rect x="34" y={TOP} width="72" height={BOTTOM - TOP} rx="16" />
          </clipPath>
          <linearGradient id={`vl-${id}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" className="vessel-liquid-top" />
            <stop offset="100%" className="vessel-liquid-bottom" />
          </linearGradient>
          <linearGradient id={`vg-${id}`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#fff" stopOpacity="0.10" />
            <stop offset="35%" stopColor="#fff" stopOpacity="0.02" />
            <stop offset="100%" stopColor="#fff" stopOpacity="0.07" />
          </linearGradient>
        </defs>

        {ticks.map((t) => (
          <g key={t} className="vessel-tick">
            <line x1="112" x2="120" y1={y(t)} y2={y(t)} />
            <text x="124" y={y(t) + 3.5}>
              {t}°
            </text>
          </g>
        ))}

        <g clipPath={`url(#v-${id})`}>
          <motion.g
            initial={false}
            animate={{ y: surface - BOTTOM }}
            transition={{ type: 'spring', stiffness: 50, damping: 14 }}
          >
            <motion.path
              d={`M-40 ${BOTTOM} q9 -5 18 0 t18 0 t18 0 t18 0 t18 0 t18 0 t18 0 t18 0 t18 0 t18 0 t18 0 V${BOTTOM + 260} H-40 z`}
              fill={`url(#vl-${id})`}
              animate={reduce ? undefined : { x: [0, 36] }}
              transition={{ duration: 2.4, ease: 'linear', repeat: Infinity }}
            />
          </motion.g>
          <rect x="34" y={TOP} width="72" height={BOTTOM - TOP} fill={`url(#vg-${id})`} />
        </g>
        <rect x="34" y={TOP} width="72" height={BOTTOM - TOP} rx="16" className="vessel-wall" />
        <rect x="56" y="6" width="28" height="12" rx="3" className="vessel-cap" />

        {limits.map((l) => (
          <motion.g
            key={l.metric}
            className={`vessel-limit vessel-limit-${l.kind}`}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
          >
            <line x1="26" x2="114" y1={y(l.value)} y2={y(l.value)} />
            <text x="2" y={y(l.value) + 3.5}>
              {l.kind === 'max' ? 'MAX' : 'MIN'}
            </text>
          </motion.g>
        ))}
      </svg>
      <div className="vessel-readout">
        <span className="vessel-value">
          <AnimatedNumber value={value} />
          <small>{unit}</small>
        </span>
        <span className="vessel-caption">
          {value == null ? 'Awaiting first reading' : limits.length ? 'Limits from SDS' : 'No SDS limit on file'}
        </span>
      </div>
    </div>
  );
}
