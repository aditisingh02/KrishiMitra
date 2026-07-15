"use client";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/** Minimal circular gauge - flat charcoal/green strokes, no glow. */
export function Gauge({
  value,
  size = 150,
  stroke = 8,
  label,
  className,
}: {
  value: number;
  size?: number;
  stroke?: number;
  label?: string;
  sublabel?: string;
  className?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  const offset = c - (pct / 100) * c;
  // restrained: deep field green when good, amber-ish ink otherwise
  const color = pct >= 70 ? "#346538" : pct >= 45 ? "#956400" : "#9F2F2D";

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#EAEAEA" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          whileInView={{ strokeDashoffset: offset }}
          viewport={{ once: true }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="display text-4xl text-ink">{Math.round(pct)}</span>
        {label && <span className="overline mt-0.5">{label}</span>}
      </div>
    </div>
  );
}
