import { useEffect, useRef } from 'react';

// Ambient background: drifting "atoms" that form bonds when they come close,
// like a molecular-dynamics view. The pointer acts as a weak attractor so
// the field reacts as you move. Pure decoration -- aria-hidden, sits behind
// content, pauses when the tab is hidden, and draws a single static frame
// when the user prefers reduced motion.

// CPK-ish element colours, muted so the field never competes with data.
const ATOMS = [
  { color: '94, 234, 212', r: 2.6, weight: 5 }, // teal (carbon stand-in)
  { color: '125, 211, 252', r: 2.2, weight: 3 }, // cyan (nitrogen)
  { color: '251, 113, 133', r: 2.4, weight: 2 }, // rose (oxygen)
  { color: '226, 232, 240', r: 1.6, weight: 4 }, // pale (hydrogen)
];

function pickAtom() {
  const total = ATOMS.reduce((s, a) => s + a.weight, 0);
  let n = Math.random() * total;
  for (const a of ATOMS) {
    n -= a.weight;
    if (n <= 0) return a;
  }
  return ATOMS[0];
}

export default function MoleculeField({ density = 1, className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const pointer = { x: -9999, y: -9999 };
    let width = 0;
    let height = 0;
    let atoms = [];
    let frame = 0;
    const BOND = 120;

    const seed = () => {
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.round(Math.min(90, (width * height) / 16000) * density);
      atoms = Array.from({ length: count }, () => ({
        ...pickAtom(),
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        phase: Math.random() * Math.PI * 2,
      }));
    };

    const draw = (t) => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < atoms.length; i++) {
        const a = atoms[i];
        for (let j = i + 1; j < atoms.length; j++) {
          const b = atoms[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d = Math.hypot(dx, dy);
          if (d < BOND) {
            const alpha = (1 - d / BOND) * 0.28;
            ctx.strokeStyle = `rgba(94, 234, 212, ${alpha})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }
      for (const a of atoms) {
        const pulse = 0.65 + 0.35 * Math.sin(t / 900 + a.phase);
        ctx.fillStyle = `rgba(${a.color}, ${0.35 + 0.45 * pulse})`;
        ctx.beginPath();
        ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const step = (t) => {
      for (const a of atoms) {
        const dx = pointer.x - a.x;
        const dy = pointer.y - a.y;
        const d = Math.hypot(dx, dy);
        if (d < 180 && d > 1) {
          a.vx += (dx / d) * 0.012;
          a.vy += (dy / d) * 0.012;
        }
        a.vx *= 0.985;
        a.vy *= 0.985;
        // Brownian jitter keeps the field alive without a pointer.
        a.vx += (Math.random() - 0.5) * 0.02;
        a.vy += (Math.random() - 0.5) * 0.02;
        a.x += a.vx;
        a.y += a.vy;
        if (a.x < -10) a.x = width + 10;
        if (a.x > width + 10) a.x = -10;
        if (a.y < -10) a.y = height + 10;
        if (a.y > height + 10) a.y = -10;
      }
      draw(t);
      frame = requestAnimationFrame(step);
    };

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };
    const onVisibility = () => {
      cancelAnimationFrame(frame);
      if (!document.hidden && !reduced) frame = requestAnimationFrame(step);
    };

    seed();
    if (reduced) draw(0);
    else frame = requestAnimationFrame(step);

    const ro = new ResizeObserver(() => {
      seed();
      if (reduced) draw(0);
    });
    ro.observe(canvas);
    window.addEventListener('pointermove', onMove);
    document.addEventListener('pointerleave', onLeave);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      window.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerleave', onLeave);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [density]);

  return <canvas ref={canvasRef} className={`molecule-field ${className}`} aria-hidden="true" />;
}
