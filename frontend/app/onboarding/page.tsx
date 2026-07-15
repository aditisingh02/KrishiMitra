"use client";
import { api, ApiError, type FarmInput } from "@/lib/api";
import { Button } from "@/components/ui/primitives";
import { motion } from "framer-motion";
import { Plant, CircleNotch, Plus, X, Warning } from "@phosphor-icons/react";
import { getStoredLang } from "@/lib/i18n";
import { useT } from "@/lib/i18n-runtime";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const FARMING_TYPES = ["Natural Farming", "Organic", "Conventional", "Mixed"];
const SOIL_TYPES = ["Loamy", "Clay", "Sandy", "Silt", "Black (Regur)", "Red", "Alluvial"];
const LANGS = [
  ["hi", "हिंदी (Hindi)"], ["en", "English"], ["pa", "ਪੰਜਾਬੀ (Punjabi)"],
  ["mr", "मराठी (Marathi)"], ["ta", "தமிழ் (Tamil)"], ["te", "తెలుగు (Telugu)"],
  ["bn", "বাংলা (Bengali)"], ["gu", "ગુજરાતી (Gujarati)"],
] as const;

export default function OnboardingPage() {
  const t = useT();
  const router = useRouter();
  const [farmer, setFarmer] = useState("");
  const [location, setLocation] = useState("");
  const [size, setSize] = useState("2");
  const [farmingType, setFarmingType] = useState("Natural Farming");
  const [language, setLanguage] = useState("hi");
  const [phone, setPhone] = useState("");

  useEffect(() => setLanguage(getStoredLang()), []);
  const [soilType, setSoilType] = useState("Loamy");
  const [crops, setCrops] = useState<string[]>(["Tomato"]);
  const [cropInput, setCropInput] = useState("");
  const [inputs, setInputs] = useState<string[]>(["Jeevamrut", "Neem oil"]);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addCrop() {
    const c = cropInput.trim();
    if (c && !crops.includes(c)) setCrops([...crops, c]);
    setCropInput("");
  }
  function addInput() {
    const v = inputText.trim();
    if (v && !inputs.includes(v)) setInputs([...inputs, v]);
    setInputText("");
  }

  async function submit() {
    setError(null);
    if (!farmer.trim() || !location.trim() || crops.length === 0) {
      setError(t("Please add your name, location, and at least one crop."));
      return;
    }
    setLoading(true);
    const payload: FarmInput = {
      farmer: farmer.trim(),
      location: location.trim(),
      phone: phone.trim() || undefined,
      farm_size_acres: parseFloat(size) || 1,
      farming_type: farmingType,
      language,
      crops: crops.map((name) => ({ name })),
      soil: { type: soilType },
      inputs_on_hand: inputs,
    };
    try {
      await api.createFarm(payload);
      router.push("/dashboard");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : t("Could not create your farm. Try again.");
      setError(msg);
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-auto max-w-xl"
      >
        <div className="mb-8 flex items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="KrishiMitra" className="h-8 w-8 rounded-md object-contain" />
          <span className="font-serif text-xl text-ink">KrishiMitra</span>
        </div>

        <h1 className="display text-4xl text-ink">{t("Set up your farm")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("This becomes your farm's digital twin. Every recommendation is grounded in these details and your real local weather and mandi prices.")}
        </p>

        <div className="mt-8 space-y-5">
          <Field label={t("Your name")}>
            <input className={inputCls} value={farmer} onChange={(e) => setFarmer(e.target.value)} placeholder={t("e.g. Ramesh Kumar")} />
          </Field>

          <Field label={t("Location (City, State)")} hint={t("Used for real weather & mandi data")}>
            <input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} placeholder={t("e.g. Hisar, Haryana")} />
          </Field>

          <Field label={t("WhatsApp number")} hint={t("Optional - get proactive alerts & ask questions on WhatsApp")}>
            <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="e.g. +91 98765 43210" />
          </Field>

          <div className="grid grid-cols-2 gap-5">
            <Field label={t("Farm size (acres)")}>
              <input className={inputCls} type="number" min="0.1" step="0.1" value={size} onChange={(e) => setSize(e.target.value)} />
            </Field>
            <Field label={t("Language")}>
              <select className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-5">
            <Field label={t("Farming type")}>
              <select className={inputCls} value={farmingType} onChange={(e) => setFarmingType(e.target.value)}>
                {FARMING_TYPES.map((ft) => <option key={ft} value={ft}>{t(ft)}</option>)}
              </select>
            </Field>
            <Field label={t("Soil type")}>
              <select className={inputCls} value={soilType} onChange={(e) => setSoilType(e.target.value)}>
                {SOIL_TYPES.map((st) => <option key={st} value={st}>{t(st)}</option>)}
              </select>
            </Field>
          </div>

          <Field label={t("Crops")} hint={t("Use names that match mandi listings (e.g. Tomato, Wheat, Onion)")}>
            <ChipInput
              items={crops}
              value={cropInput}
              onValue={setCropInput}
              onAdd={addCrop}
              onRemove={(c: string) => setCrops(crops.filter((x) => x !== c))}
              placeholder={t("Add a crop and press Enter")}
            />
          </Field>

          <Field label={t("Inputs on hand")} hint={t("Optional - what you already have")}>
            <ChipInput
              items={inputs}
              value={inputText}
              onValue={setInputText}
              onAdd={addInput}
              onRemove={(c: string) => setInputs(inputs.filter((x) => x !== c))}
              placeholder={t("e.g. Vermicompost")}
            />
          </Field>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-pale-red bg-pale-red px-3 py-2.5">
              <Warning className="mt-0.5 h-4 w-4 shrink-0 text-pale-redink" weight="bold" />
              <p className="text-sm text-pale-redink">{error}</p>
            </div>
          )}

          <Button onClick={submit} disabled={loading} size="lg" className="w-full">
            {loading ? <CircleNotch className="h-5 w-5 animate-spin" /> : <Plant className="h-5 w-5" />}
            {t("Create my farm")}
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-ink focus:border-faint/50 focus:outline-none";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-charcoal">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
    </div>
  );
}

function ChipInput({ items, value, onValue, onAdd, onRemove, placeholder }: any) {
  return (
    <div>
      <div className="flex gap-2">
        <input
          className={inputCls}
          value={value}
          onChange={(e) => onValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onAdd();
            }
          }}
          placeholder={placeholder}
        />
        <Button type="button" variant="outline" onClick={onAdd} className="!px-3">
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {items.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {items.map((c: string) => (
            <span key={c} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-bone px-2.5 py-1 text-xs text-charcoal">
              {c}
              <button onClick={() => onRemove(c)} className="text-faint hover:text-pale-redink">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
