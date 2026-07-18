"use client";
import { api } from "@/lib/api";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { FarmLayout } from "@/components/ui/farm-layout";
import { CropCalendar } from "@/components/planner/crop-calendar";
import { motion, AnimatePresence } from "framer-motion";
import { CalendarCheck, StackSimple, CircleNotch, Flask, UploadSimple, CheckCircle } from "@phosphor-icons/react";
import { Suspense, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n-runtime";

type Tab = "calendar" | "cropping" | "soil";

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
    ["calendar", "cropping", "soil"].includes(initial) ? initial : "calendar",
  );
  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" className="mb-3">{t("Personalised coach")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Farm Planner")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Every crop's sowing→harvest calendar in one place, plus a cropping designer and soil-card reader.")}
        </p>
      </div>

      <div className="flex rounded-md border border-line p-1">
        {([
          ["calendar", "Calendar", CalendarCheck],
          ["cropping", "Cropping", StackSimple],
          ["soil", "Soil card", Flask],
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

      {tab === "calendar" ? <CropCalendar /> : tab === "cropping" ? <CroppingDesigner /> : <SoilCard />}
    </div>
  );
}

function SoilCard() {
  const t = useT();
  const [preview, setPreview] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function onFile(f: File) {
    if (!f.type.startsWith("image/")) return;
    setFile(f);
    setResult(null);
    const reader = new FileReader();
    reader.onload = () => setPreview(reader.result as string);
    reader.readAsDataURL(f);
  }

  async function read() {
    if (!file || loading) return;
    setLoading(true);
    try {
      setResult(await api.soilCard(file));
    } catch {
      alert(t("Failed to read the soil card. Is the backend running?"));
    } finally {
      setLoading(false);
    }
  }

  const ext = result?.extracted ?? {};
  const rows: [string, any][] = [
    [t("Type"), ext.type], [t("pH"), ext.ph], [t("Organic carbon"), ext.organic_carbon],
    [t("Nitrogen"), ext.nitrogen], [t("Phosphorus"), ext.phosphorus], [t("Potassium"), ext.potassium],
    [t("EC"), ext.ec],
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">
        {t("Upload a photo of your government Soil Health Card. Kimi vision reads the values (pH, N-P-K, organic carbon) into your farm twin so every recommendation is grounded in your soil.")}
      </p>

      <div className="card overflow-hidden !p-0">
        {!preview ? (
          <div onClick={() => inputRef.current?.click()} className="flex cursor-pointer flex-col items-center gap-3 px-6 py-14 hover:bg-bone/60">
            <div className="flex h-14 w-14 items-center justify-center rounded-lg border border-line bg-bone text-field-600">
              <UploadSimple className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-ink">{t("Upload Soil Health Card")}</p>
            <p className="font-mono text-xs text-faint">{t("photo or scan · JPG / PNG")}</p>
            <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="soil card" className="max-h-72 w-full object-contain bg-bone" />
        )}
      </div>

      {preview && !result && (
        <Button onClick={read} disabled={loading} size="lg" className="w-full">
          {loading ? <CircleNotch className="h-5 w-5 animate-spin" /> : <Flask className="h-5 w-5" />}
          {t("Read soil card")}
        </Button>
      )}

      {result && (
        <Card interactive={false}>
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-field-600" weight="bold" />
            <span className="text-sm font-medium text-ink">{t("Saved to your farm")}</span>
          </div>
          <dl className="divide-y divide-line">
            {rows.filter(([, v]) => v != null && v !== "null").map(([k, v]) => (
              <div key={k} className="flex justify-between py-2 text-sm">
                <dt className="text-muted">{k}</dt>
                <dd className="font-medium capitalize text-ink">{String(v)}</dd>
              </div>
            ))}
          </dl>
          {ext.notes && <p className="mt-3 text-xs text-muted">{ext.notes}</p>}
          {(ext.readable === false || ext._parse_error) && (
            <p className="mt-2 text-sm text-pale-redink">{t("Couldn't read this card clearly - try a sharper, well-lit photo.")}</p>
          )}
        </Card>
      )}
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
