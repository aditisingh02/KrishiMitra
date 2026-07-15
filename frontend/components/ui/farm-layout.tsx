"use client";
import { motion } from "framer-motion";

/**
 * Generative top-down "aerial" farm plan rendered as SVG from the cropping
 * design. Each of the 4 layers becomes a band of plants sized by storey:
 * canopy (big) → middle → shrub → ground cover (texture). Deterministic layout
 * so it's stable across renders. No external image API needed.
 */

type Layer = { layer: string; crop: string; role?: string; spacing?: string };

const PALETTE = [
  { fill: "#2B5430", ring: "#346538", r: 16 }, // canopy  - deep field green
  { fill: "#5A7D3C", ring: "#6f9a4a", r: 11 }, // middle  - sage
  { fill: "#A98B3E", ring: "#956400", r: 7 }, //  shrub   - ochre
  { fill: "#9CB07E", ring: "#7d946a", r: 4 }, //  ground  - pale moss
];

// deterministic pseudo-random in [0,1) from an integer seed
function rng(seed: number) {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

const W = 640;
const H = 380;
const PAD = 28;

function plantsForLayer(idx: number, count: number) {
  const bandH = (H - PAD * 2) / 4;
  const top = PAD + idx * bandH;
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i < count; i++) {
    const seed = idx * 100 + i;
    const x = PAD + rng(seed) * (W - PAD * 2);
    const y = top + 6 + rng(seed + 50) * (bandH - 12);
    pts.push({ x, y });
  }
  return pts;
}

export function FarmLayout({ layers }: { layers: Layer[] }) {
  const top4 = layers.slice(0, 4);
  // denser plants as the storey gets lower
  const counts = [7, 12, 20, 46];

  return (
    <div className="overflow-hidden rounded-xl border border-line">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Aerial farm layout">
        <defs>
          <filter id="soft">
            <feGaussianBlur stdDeviation="0.3" />
          </filter>
        </defs>

        {/* field - warm bone paper */}
        <rect x="0" y="0" width={W} height={H} fill="#F7F6F3" />

        {/* furrows / grid */}
        {Array.from({ length: 16 }).map((_, i) => (
          <line
            key={`v${i}`}
            x1={PAD + (i * (W - PAD * 2)) / 15}
            y1={PAD}
            x2={PAD + (i * (W - PAD * 2)) / 15}
            y2={H - PAD}
            stroke="#000000"
            strokeOpacity={0.04}
          />
        ))}

        {/* layer band dividers + labels */}
        {top4.map((l, idx) => {
          const bandH = (H - PAD * 2) / 4;
          const y = PAD + idx * bandH;
          return (
            <g key={`band${idx}`}>
              <line x1={PAD} y1={y} x2={W - PAD} y2={y} stroke="#000000" strokeOpacity={0.05} />
              <text x={PAD + 4} y={y + 14} fontSize="10" fill="#9B9A97" style={{ textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "var(--font-mono)" }}>
                {l.layer}
              </text>
            </g>
          );
        })}

        {/* plants */}
        {top4.map((l, idx) => {
          const p = PALETTE[idx];
          return plantsForLayer(idx, counts[idx]).map((pt, i) => (
            <motion.circle
              key={`${idx}-${i}`}
              cx={pt.x}
              cy={pt.y}
              r={p.r}
              fill={p.fill}
              stroke={p.ring}
              strokeWidth={1}
              filter="url(#soft)"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: idx === 3 ? 0.85 : 1 }}
              transition={{
                delay: idx * 0.15 + i * 0.015,
                type: "spring",
                stiffness: 260,
                damping: 18,
              }}
            />
          ));
        })}
      </svg>

      {/* legend */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line bg-surface p-3 sm:grid-cols-4">
        {top4.map((l, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <span
              className="h-3 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: PALETTE[idx].fill }}
            />
            <span className="truncate text-xs text-charcoal">{l.crop}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
