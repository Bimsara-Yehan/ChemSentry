import { useEffect, useRef, useState } from 'react';
import { animate, motion, useReducedMotion } from 'motion/react';

// Small motion primitives shared across views.

// Counts from the previous value to the new one, so a live reading visibly
// "moves" when a sensor update arrives rather than snapping.
export function AnimatedNumber({ value, decimals = 1, className = '' }) {
  const ref = useRef(null);
  const prev = useRef(value ?? 0);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (value == null || !ref.current) return undefined;
    if (reduce) {
      ref.current.textContent = Number(value).toFixed(decimals);
      prev.current = value;
      return undefined;
    }
    const controls = animate(prev.current, value, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = v.toFixed(decimals);
      },
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, decimals, reduce]);

  if (value == null) return <span className={className}>—</span>;
  return (
    <span ref={ref} className={className}>
      {Number(prev.current).toFixed(decimals)}
    </span>
  );
}

// Staggered entrance for lists and grids.
export const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

export const rise = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', stiffness: 260, damping: 26 } },
};

// Circular dial (humidity, completion). Arc length animates with a spring.
export function RingGauge({ value, max = 100, size = 112, stroke = 9, tone = 'cyan', label, unit = '%' }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = value == null ? 0 : Math.max(0, Math.min(1, value / max));
  return (
    <div className={`ring-gauge ring-${tone}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} className="ring-track" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          className="ring-value"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring-center">
        <span className="ring-number">
          <AnimatedNumber value={value} decimals={0} />
          <small>{unit}</small>
        </span>
        {label && <span className="ring-label">{label}</span>}
      </div>
    </div>
  );
}

// Ticks once per second; used for "updated Xs ago" text.
export function useNow(active = true) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}
