"use client";
import { api } from "@/lib/api";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { FarmLayout } from "@/components/ui/farm-layout";
import { CropCalendar } from "@/components/planner/crop-calendar";
import { motion, AnimatePresence } from "framer-motion";
import { CalendarCheck, StackSimple, CircleNotch } from "@phosphor-icons/react";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n-runtime";

type Tab = "calendar" | "cropping";

// useSearchParams (used by CropCalendar + the ?tab= deep link) needs a Suspense
// boundary above it.
export default function PlannerPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><CircleNotch className="h-6 w-6 animate-spin text-faint" /></div>}>
      <Planner />
    </Suspense>
  );
}

function Planner() {
  const t = useT();
  const params = useSearchParams();
  const initial = (params.get("tab") as Tab) || "calendar";
  const [tab, setTab] = useState<Tab>(
    ["calendar", "cropping"].includes(initial) ? initial : "calendar",
  );
  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" className="mb-3">{t("Personalised coach")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Farm Planner")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Every crop's sowing→harvest calendar in one place, plus a multilayer cropping designer.")}
        </p>
      </div>

      <div className="flex rounded-md border border-line p-1">
        {([
          ["calendar", "Calendar", CalendarCheck],
          ["cropping", "Cropping", StackSimple],
        ] as const).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`relative flex flex-1 items-center justify-center gap-2 rounded py-2.5 text-sm font-medium transition-colors ${
              tab === key ? "text-ink" : "text-faint"
            }`}
          >
            {tab === key && (
              <motion.span layoutId="planner-tab" className="absolute inset-0 rounded bg-bone" transition={{ type: "spring", stiffness: 400, damping: 34 }} />
            )}
            <span className="relative flex items-center gap-2">
              <Icon className="h-4 w-4" /> {t(label)}
            </span>
          </button>
        ))}
      </div>

      {tab === "calendar" ? <CropCalendar /> : <CroppingDesigner />}
    </div>
  );
}

function CroppingDesigner() {
  const t = useT();
  const [land, setLand] = useState("2 acres");
  const [location, setLocation] = useState("Hisar, Haryana");
  const [goals, setGoals] = useState("Start natural farming with mixed income and soil building");
  const [design, setDesign] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function generate() {
    setLoading(true);
    setDesign(null);
    try {
      setDesign((await api.croppingDesign(land, location, goals)).design);
    } catch {
      alert(t("Failed. Is the backend running?"));
    } finally {
      setLoading(false);
    }
  }

  // muted band tints matched to the farm-layout palette
  const bandTint = ["bg-field-50", "bg-pale-green", "bg-pale-yellow", "bg-bone"];

  return (
    <div className="space-y-4">
      <Card interactive={false} className="space-y-3">
        <Field label={t("Land available")} value={land} onChange={setLand} />
        <Field label={t("Location")} value={location} onChange={setLocation} />
        <Field label={t("Your goals")} value={goals} onChange={setGoals} textarea />
        <Button onClick={generate} disabled={loading} size="lg" className="w-full">
          {loading ? <CircleNotch className="h-5 w-5 animate-spin" /> : <StackSimple className="h-5 w-5" />}
          {t("Design my multilayer farm")}
        </Button>
      </Card>

      <AnimatePresence>
        {design && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            {design.layers?.length > 0 && (
              <Card interactive={false}>
                <p className="overline mb-3">{t("Aerial farm plan")}</p>
                <FarmLayout layers={design.layers} />
              </Card>
            )}

            <Card interactive={false}>
              <p className="overline mb-4">{t("Your 4-layer food forest")}</p>
              <div className="space-y-2">
                {design.layers?.map((l: any, i: number) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, scale: 0.99 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.08 }}
                    className={`flex items-center justify-between rounded-md border border-line px-4 py-3 ${bandTint[i] ?? "bg-bone"}`}
                    style={{ marginLeft: `${i * 10}px` }}
                  >
                    <div>
                      <p className="overline">{t(l.layer)}</p>
                      <p className="text-sm font-medium text-ink">{t(l.crop)}</p>
                      <p className="text-sm text-muted">{t(l.role)}</p>
                    </div>
                    {l.spacing && <span className="font-mono text-xs text-charcoal">{l.spacing}</span>}
                  </motion.div>
                ))}
              </div>
            </Card>

            {design.rationale_en && (
              <Card interactive={false}>
                <p className="text-[15px] leading-relaxed text-charcoal">{t(design.rationale_en)}</p>
                {design.rationale_hi && (
                  <p className="mt-3 border-t border-line pt-3 text-[15px] leading-relaxed text-muted">{design.rationale_hi}</p>
                )}
              </Card>
            )}

            {design.first_steps?.length > 0 && (
              <Card interactive={false}>
                <p className="overline mb-2">{t("First steps")}</p>
                <ul className="space-y-1.5">
                  {design.first_steps.map((s: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-charcoal">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-field-600" /> {t(s)}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Field({ label, value, onChange, textarea }: any) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-muted">{label}</label>
      {textarea ? (
        <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={2} className="w-full resize-none rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-ink focus:border-faint/50 focus:outline-none" />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} className="w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-ink focus:border-faint/50 focus:outline-none" />
      )}
    </div>
  );
}
