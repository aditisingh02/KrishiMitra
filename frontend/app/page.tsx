"use client";
import { AuroraBackground } from "@/components/ui/aurora-background";
import { AnimatedCounter } from "@/components/ui/animated-counter";
import { Button, Tag } from "@/components/ui/primitives";
import { motion } from "framer-motion";
import {
  Plant,
  Microphone,
  Scan,
  CloudRain,
  TrendUp,
  Bank,
  ShieldWarning,
  Brain,
  ArrowRight,
  Translate,
  Leaf,
  Drop,
  Recycle,
  Bug,
  Flask,
} from "@phosphor-icons/react";
import Link from "next/link";
import { SignedIn, SignedOut, useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { LanguageSelect } from "@/components/ui/language-select";
import { landingCopy, getStoredLang, setStoredLang } from "@/lib/i18n";
import { useT } from "@/lib/i18n-runtime";
import { api } from "@/lib/api";

const AGENTS = [
  { icon: Brain, name: "Planner", desc: "Routes each query to the right specialists" },
  { icon: Scan, name: "Crop Health", desc: "Disease, pest and nutrient diagnosis" },
  { icon: Plant, name: "Natural Farming", desc: "Jeevamrut, neem and organic remedies" },
  { icon: CloudRain, name: "Weather", desc: "Forecast-aware spray and irrigation timing" },
  { icon: TrendUp, name: "Market", desc: "Mandi prices and the best time to sell" },
  { icon: Bank, name: "Finance", desc: "Schemes, subsidies and insurance" },
  { icon: ShieldWarning, name: "Risk", desc: "Predicts outbreaks before they happen" },
  { icon: Plant, name: "Action Planner", desc: "Synthesises one clear daily plan" },
];

const FEATURES = [
  { icon: Microphone, img: "/landing/indian-farmer.png", title: "Voice-first, in Hindi", body: "Farmers speak naturally. The system listens, reasons across agents, and answers aloud in their language." },
  { icon: Scan, img: "/landing/diseased.jpeg", title: "Diagnose from a photo", body: "Snap a leaf. The vision agent names the disease, its severity, and a natural cure." },
  { icon: ShieldWarning, img: "/landing/farm_weather.jpg", title: "Warns before you ask", body: "It watches weather and history, and flags fungal risk before it spreads." },
  { icon: Translate, img: "/landing/farmer-nojargon.jpg", title: "No jargon", body: "Plain, specific guidance written the way a farmer would explain it to a neighbour." },
];

// natural-farming practices the system actually prescribes
const PRACTICES = [
  { icon: Flask, name: "Jeevamrut", desc: "Fermented microbial tonic that wakes up the soil" },
  { icon: Plant, name: "Beejamrut", desc: "Seed treatment that protects young roots" },
  { icon: Drop, name: "Panchagavya", desc: "Growth promoter that builds crop immunity" },
  { icon: Bug, name: "Neem spray", desc: "Organic control for aphids, whitefly and mildew" },
  { icon: Leaf, name: "Mulching", desc: "Holds moisture, blocks weeds, feeds soil life" },
  { icon: Recycle, name: "Vermicompost", desc: "Worm-rich compost for steady nutrition" },
];

// crops the agents are tuned for (prices, diseases, calendars)
const CROPS = [
  { name: "Tomato", img: "/landing/tomato.jpg" },
  { name: "Wheat", img: "/landing/wheat.jpg" },
  { name: "Onion", img: "/landing/onion.jpg" },
  { name: "Turmeric", img: "/landing/turmeric.jpeg" },
  { name: "Banana", img: "/landing/banana.avif" },
  { name: "Cowpea", img: "/landing/cowpea.webp" },
  { name: "Moringa", img: "/landing/moringa.jpeg" },
  { name: "Potato", img: "/landing/potato.jpg" },
  { name: "Chilli", img: "/landing/chilli.jpeg" },
  { name: "Sugarcane", img: "/landing/sugarcane.webp" },
];

export default function Landing() {
  const { isSignedIn } = useAuth();
  const tr = useT();
  const [lang, setLang] = useState("en");
  const t = landingCopy(lang);

  useEffect(() => setLang(getStoredLang()), []);

  async function changeLang(code: string) {
    setLang(code);
    setStoredLang(code);
    if (isSignedIn) {
      try {
        await api.updateProfile({ language: code });
      } catch {
        /* no profile yet - choice is remembered for onboarding */
      }
    }
  }

  return (
    <main className="bg-paper">
      {/* ---------------- HERO ---------------- */}
      <AuroraBackground>
        {/* background video + transparent→white gradient */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <video
            autoPlay
            muted
            loop
            playsInline
            poster="/hero-poster.jpg"
            className="h-full w-full object-cover"
          >
            <source src="/hero.mp4" type="video/mp4" />
          </video>
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to bottom, rgba(0,0,0,0.32) 0%, rgba(0,0,0,0.06) 14%, rgba(0,0,0,0) 24%), " +
                "linear-gradient(to bottom, rgba(251,251,250,0.42) 0%, rgba(251,251,250,0.88) 32%, #FBFBFA 56%)",
            }}
          />
        </div>

        <nav className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <div className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="KrishiMitra" className="h-8 w-8 rounded-md object-contain" />
            <span className="font-serif text-xl text-ink">KrishiMitra</span>
          </div>
          <div className="flex items-center gap-2">
            <LanguageSelect value={lang} onChange={changeLang} />
            <SignedOut>
              <Link href="/sign-in" className="hidden sm:block">
                <Button variant="ghost" size="sm">{t.signin}</Button>
              </Link>
              <Link href="/sign-up">
                <Button size="sm">{t.getstarted} <ArrowRight className="h-4 w-4" /></Button>
              </Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard">
                <Button variant="outline" size="sm">
                  {t.opendash} <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </SignedIn>
          </div>
        </nav>

        <section className="relative z-10 mx-auto max-w-4xl px-6 pb-28 pt-20 text-center md:pt-28">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-7 flex justify-center"
          >
            <Tag tone="green" dot>
              {t.eyebrow}
            </Tag>
          </motion.div>

          <motion.h1
            key={lang}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.05 }}
            className="display text-4xl text-ink md:text-[4.75rem]"
            style={{ lineHeight: lang === "en" ? 1.28 : 1.5 }}
          >
            {t.title}
            <br />
            <span className="mt-2 inline-block italic text-field-600">{t.accent}</span>
          </motion.h1>

          <motion.p
            key={`${lang}-sub`}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.15 }}
            className="mx-auto mt-7 max-w-xl text-[17px] leading-relaxed text-muted"
          >
            {t.sub}
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.25 }}
            className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <SignedOut>
              <Link href="/sign-up">
                <Button size="lg">{t.start} <ArrowRight className="h-5 w-5" /></Button>
              </Link>
              <Link href="/sign-in">
                <Button size="lg" variant="outline">{t.signin}</Button>
              </Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard">
                <Button size="lg">{t.open} <ArrowRight className="h-5 w-5" /></Button>
              </Link>
              <Link href="/consult">
                <Button size="lg" variant="outline">
                  <Microphone className="h-5 w-5" /> {t.talk}
                </Button>
              </Link>
            </SignedIn>
          </motion.div>

          {/* stats */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="mx-auto mt-20 grid max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-4"
          >
            {[
              { v: 8, s: "", l: "Specialist agents" },
              { v: 6, s: "", l: "Crop issues in KB" },
              { v: 100, s: "%", l: "Natural remedies" },
              { v: 8, s: "", l: "Languages" },
            ].map((stat, i) => (
              <div key={i} className="bg-surface px-5 py-6">
                <p className="display text-3xl text-ink">
                  <AnimatedCounter value={stat.v} suffix={stat.s} />
                </p>
                <p className="mt-1 text-xs text-muted">{tr(stat.l)}</p>
              </div>
            ))}
          </motion.div>
        </section>
      </AuroraBackground>

      {/* ---------------- NATURAL FARMING PRACTICES ---------------- */}
      <section className="relative border-y border-line">
        {/* farm photo backdrop, darkened left→right so the heading reads in light text */}
        <div className="absolute inset-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/landing/farm_weather.jpg" alt="" className="h-full w-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-ink/80 via-ink/55 to-ink/25" />
        </div>
        <div className="relative z-10 mx-auto max-w-6xl px-6 py-24 md:py-32">
          <div className="mb-14 flex flex-wrap items-end justify-between gap-4">
            <div className="max-w-2xl">
              <p className="overline mb-3 text-paper/60">{tr("Rooted in natural farming")}</p>
              <h2 className="display text-3xl text-paper md:text-4xl">
                {tr("Real practices, not chemicals.")}
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-paper/85">
                {tr("Every remedy the agents prescribe comes from Subhash Palekar Natural Farming and ICAR practice - grounded in a curated knowledge base, never invented.")}
              </p>
            </div>
            <Leaf className="hidden h-16 w-16 text-paper/25 md:block" weight="thin" />
          </div>

          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {PRACTICES.map((p, i) => {
              const Icon = p.icon;
              return (
                <motion.div
                  key={p.name}
                  initial={{ opacity: 0, y: 14 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: (i % 3) * 0.06 }}
                  className="flex items-start gap-4 bg-surface p-6"
                >
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-line bg-bone text-field-600">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-[15px] font-medium text-ink">{tr(p.name)}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-muted">{tr(p.desc)}</p>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ---------------- CROP COVERAGE (marquee) ---------------- */}
      <section className="py-20 md:py-28">
        <div className="mx-auto mb-10 max-w-6xl px-6 text-center">
          <p className="overline mb-3">{tr("Tuned for your field")}</p>
          <h2 className="display mx-auto max-w-2xl text-3xl text-ink md:text-4xl">
            {tr("Prices, diseases and calendars across India's staple crops.")}
          </h2>
        </div>

        {/* full-bleed marquee with edge fades */}
        <div className="group relative overflow-hidden">
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-24 bg-gradient-to-r from-paper to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-24 bg-gradient-to-l from-paper to-transparent" />
          <div className="flex w-max animate-marquee gap-4 group-hover:[animation-play-state:paused]">
            {[...CROPS, ...CROPS].map((c, i) => (
              <figure
                key={`${c.name}-${i}`}
                className="w-52 shrink-0 overflow-hidden rounded-xl border border-line bg-surface"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={c.img}
                  alt={c.name}
                  loading="lazy"
                  className="h-36 w-full object-cover"
                />
                <figcaption className="flex items-center gap-2 px-4 py-3">
                  <Leaf className="h-4 w-4 text-field-600" />
                  <span className="text-sm font-medium text-ink">{tr(c.name)}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
        <p className="mt-10 text-center text-sm text-muted">{tr("…and more - just add your crops at onboarding.")}</p>
      </section>

      {/* ---------------- FEATURES ---------------- */}
      <section className="mx-auto max-w-6xl px-6 pb-24 md:pb-32">
        <div className="mb-14 max-w-2xl">
          <p className="overline mb-3">{tr("Built for the field")}</p>
          <h2 className="display text-3xl text-ink md:text-4xl">
            {tr("Designed for how farmers actually work.")}
          </h2>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: i * 0.06 }}
                className="card card-interactive overflow-hidden !p-0"
              >
                <div className="relative h-44 w-full overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={f.img} alt={f.title} loading="lazy" className="h-full w-full object-cover" />
                  <div className="absolute left-3 top-3 flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface/90 text-field-600 backdrop-blur">
                    <Icon className="h-[18px] w-[18px]" />
                  </div>
                </div>
                <div className="p-6">
                  <h3 className="text-lg font-medium text-ink">{tr(f.title)}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">{tr(f.body)}</p>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* CTA */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="mt-20 flex flex-col items-center rounded-xl border border-line bg-bone px-8 py-16 text-center"
        >
          <h2 className="display max-w-xl text-3xl text-ink md:text-4xl">
            {tr("See the autonomous agronomist at work.")}
          </h2>
          <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted">
            {tr("Open Ramesh's three-acre farm in Hisar - a live health score, proactive alerts, and a voice consultation running on the multi-agent backend.")}
          </p>
          <SignedOut>
            <Link href="/sign-up" className="mt-8">
              <Button size="lg">{tr("Create your farm")} <ArrowRight className="h-5 w-5" /></Button>
            </Link>
          </SignedOut>
          <SignedIn>
            <Link href="/dashboard" className="mt-8">
              <Button size="lg">{tr("Open the dashboard")} <ArrowRight className="h-5 w-5" /></Button>
            </Link>
          </SignedIn>
        </motion.div>
      </section>

      {/* ---------------- AGENT ARCHITECTURE ---------------- */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:py-32">
        <div className="mb-14 max-w-2xl">
          <p className="overline mb-3">{tr("Not one model - a team")}</p>
          <h2 className="display text-3xl text-ink md:text-4xl">
            {tr("Eight agents, one action plan.")}
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-muted">
            {tr("A Planner breaks every request into a task graph, dispatches specialists in parallel, and an Action Planner synthesises a single prioritised answer.")}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {AGENTS.map((agent, i) => {
            const Icon = agent.icon;
            return (
              <motion.div
                key={agent.name}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: (i % 4) * 0.06 }}
                className="bg-surface p-6"
              >
                <Icon className="h-5 w-5 text-field-600" weight="regular" />
                <h3 className="mt-4 text-[15px] font-medium text-ink">{tr(agent.name)}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{tr(agent.desc)}</p>
              </motion.div>
            );
          })}
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <p className="text-xs text-faint">
            KrishiMitra · {tr("Agentic Agronomy OS for natural farming")} · Fireworks
            (gpt-oss-120b agents · Kimi K2.6 vision · DeepSeek V4)
          </p>
        </div>
      </footer>
    </main>
  );
}
