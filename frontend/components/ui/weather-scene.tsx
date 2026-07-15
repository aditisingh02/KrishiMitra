"use client";
import { motion } from "framer-motion";

/**
 * Ambient animated weather scene that adapts to the day's conditions.
 * Picks a sun / cloud / rain mood from the condition text + rain probability,
 * then fills space with a calm, looping animation (rotating sun rays, drifting
 * clouds, or falling rain). Purely decorative - informative text overlays it.
 */
type Props = {
  condition?: string;
  tempMaxC?: number;
  rainProb?: number;
  className?: string;
};

type Mood = "rain" | "cloud" | "sun";

function moodOf(condition = "", rainProb = 0): Mood {
  const c = condition.toLowerCase();
  if (rainProb >= 50 || /rain|storm|drizzle|shower|thunder/.test(c)) return "rain";
  if (/cloud|overcast|haze|fog|mist|smoke/.test(c)) return "cloud";
  return "sun";
}

const sky: Record<Mood, string> = {
  sun: "from-[#FFF6E6] via-[#FDF8F2] to-[#FBFAF7]",
  cloud: "from-[#EEF3F7] via-[#F4F6F8] to-[#FBFAF7]",
  rain: "from-[#E4ECF3] via-[#EDF2F6] to-[#F7F9FB]",
};

export function WeatherScene({ condition, tempMaxC, rainProb = 0, className }: Props) {
  const mood = moodOf(condition, rainProb);
  return (
    <div
      className={`relative w-full flex-1 overflow-hidden rounded-xl border border-line bg-gradient-to-b ${sky[mood]} ${className ?? ""}`}
    >
      {mood === "sun" && <SunScene hot={(tempMaxC ?? 0) >= 35} />}
      {mood === "cloud" && <CloudScene />}
      {mood === "rain" && <RainScene />}

      {/* caption */}
      <div className="absolute bottom-3 left-4 right-4 flex items-end justify-between">
        <p className="text-sm font-medium capitalize text-charcoal/80">
          {condition || "Clear skies"}
        </p>
        {tempMaxC != null && (
          <p className="font-mono text-xs text-muted">{tempMaxC}° high</p>
        )}
      </div>
    </div>
  );
}

/* --------------------------------- sun ----------------------------------- */
function SunScene({ hot }: { hot: boolean }) {
  return (
    <>
      <div className="absolute -right-6 -top-6 h-40 w-40">
        {/* rotating rays */}
        <motion.svg
          viewBox="0 0 100 100"
          className="absolute inset-0 h-full w-full text-amber-300/70"
          animate={{ rotate: 360 }}
          transition={{ duration: 90, repeat: Infinity, ease: "linear" }}
        >
          {Array.from({ length: 12 }).map((_, i) => (
            <line
              key={i}
              x1="50"
              y1="50"
              x2="50"
              y2="8"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              transform={`rotate(${i * 30} 50 50)`}
            />
          ))}
        </motion.svg>
        {/* core */}
        <motion.div
          className="absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-300"
          style={{ boxShadow: "0 0 36px 10px rgba(251,191,36,0.45)" }}
          animate={{ scale: [1, 1.06, 1], opacity: [0.92, 1, 0.92] }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      {/* heat shimmer near the ground on hot days */}
      {hot &&
        [0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="absolute bottom-9 h-px bg-amber-400/30"
            style={{ left: `${12 + i * 26}%`, width: "20%" }}
            animate={{ opacity: [0, 0.6, 0], x: [0, 6, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut", delay: i * 0.5 }}
          />
        ))}
    </>
  );
}

/* -------------------------------- clouds --------------------------------- */
function Cloud({
  top,
  scale,
  duration,
  delay = 0,
  opacity,
}: {
  top: string;
  scale: number;
  duration: number;
  delay?: number;
  opacity: number;
}) {
  return (
    <motion.div
      className="absolute"
      style={{ top, opacity }}
      initial={{ x: "-30%" }}
      animate={{ x: "130%" }}
      transition={{ duration, repeat: Infinity, ease: "linear", delay }}
    >
      <div style={{ transform: `scale(${scale})` }} className="relative h-8 w-20">
        <div className="absolute bottom-0 h-5 w-20 rounded-full bg-white blur-[1px]" />
        <div className="absolute bottom-1 left-3 h-9 w-9 rounded-full bg-white blur-[1px]" />
        <div className="absolute bottom-2 left-9 h-11 w-11 rounded-full bg-white blur-[1px]" />
      </div>
    </motion.div>
  );
}

function CloudScene() {
  return (
    <>
      {/* faint sun behind */}
      <div className="absolute right-8 top-5 h-14 w-14 rounded-full bg-amber-200/60 blur-[2px]" />
      <Cloud top="14%" scale={1.1} duration={34} opacity={0.95} />
      <Cloud top="40%" scale={0.8} duration={46} delay={6} opacity={0.7} />
      <Cloud top="58%" scale={1.3} duration={28} delay={3} opacity={0.85} />
    </>
  );
}

/* --------------------------------- rain ---------------------------------- */
function RainScene() {
  const drops = Array.from({ length: 22 });
  return (
    <>
      {/* cloud bank */}
      <div className="absolute left-6 top-3 h-7 w-28 rounded-full bg-slate-300/80 blur-[2px]" />
      <div className="absolute left-16 top-1 h-10 w-16 rounded-full bg-slate-300/80 blur-[2px]" />
      <div className="absolute right-8 top-4 h-6 w-24 rounded-full bg-slate-200/80 blur-[2px]" />

      {drops.map((_, i) => {
        const left = (i * 4.5 + 4) % 100;
        const delay = (i % 7) * 0.18;
        const dur = 0.9 + (i % 4) * 0.18;
        return (
          <motion.span
            key={i}
            className="absolute top-8 h-4 w-px rounded-full bg-[#1F6C9F]/45"
            style={{ left: `${left}%` }}
            initial={{ y: 0, opacity: 0 }}
            animate={{ y: ["0%", "560%"], opacity: [0, 0.8, 0] }}
            transition={{ duration: dur, repeat: Infinity, ease: "easeIn", delay }}
          />
        );
      })}
    </>
  );
}
