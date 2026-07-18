"use client";

import { api, ApiError, type Farm, type Profile } from "@/lib/api";
import { Button, Card, Tag } from "@/components/ui/primitives";
import { WhatsAppLink } from "@/components/shell/whatsapp-link";
import { motion, AnimatePresence } from "framer-motion";
import {
  CircleNotch, Plus, X, Warning, CheckCircle, CalendarPlus, Plant, Trash,
  MapPin, Star,
} from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n-runtime";
import { setStoredLang } from "@/lib/i18n";

const FARMING_TYPES = ["Natural Farming", "Organic", "Conventional", "Mixed"];
const SOIL_TYPES = ["Loamy", "Clay", "Sandy", "Silt", "Black (Regur)", "Red", "Alluvial"];
const STAGES = ["", "sown", "seedling", "vegetative", "flowering", "fruiting", "harvest"];
const LANGS = [
  ["hi", "हिंदी (Hindi)"], ["en", "English"], ["pa", "ਪੰਜਾਬੀ (Punjabi)"],
  ["mr", "मराठी (Marathi)"], ["ta", "தமிழ் (Tamil)"], ["te", "తెలుగు (Telugu)"],
  ["bn", "বাংলা (Bengali)"], ["gu", "ગુજરાતી (Gujarati)"],
] as const;

type CropRow = { name: string; stage?: string; area_acres?: number };

export default function ProfilePage() {
  const t = useT();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [farms, setFarms] = useState<Farm[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const { profile, farms } = await api.profile();
      setProfile(profile);
      setFarms(farms);
      setActiveId(profile.active_farm_id ?? null);
    } catch {
      setError(t("Couldn't load your profile."));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function switchFarm(id: string) {
    setActiveId(id); // optimistic
    try {
      await api.setActiveFarm(id);
      // The whole app is scoped to the active farm - reload so every page follows.
      window.location.reload();
    } catch {
      load();
    }
  }

  async function removeFarm(farm: Farm) {
    if (farms.length === 1) {
      alert(t("You can't delete your only farm. Add another first."));
      return;
    }
    if (!confirm(t("Delete this farm and all its crops, calendar and history?"))) return;
    try {
      await api.deleteFarm(farm.id);
      await load();
    } catch {
      setError(t("Couldn't delete that farm."));
    }
  }

  if (loading) {
    return <div className="flex justify-center py-20"><CircleNotch className="h-6 w-6 animate-spin text-faint" /></div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" dot className="mb-3">{t("Your account")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Profile & farms")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("You, and every farm you manage. The AI works on whichever farm is active - switch any time.")}
        </p>
      </div>

      {profile && <ProfileCard profile={profile} onSaved={setProfile} />}

      <WhatsAppLink />

      {/* farms */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <span className="overline">{t("Your farms")} ({farms.length})</span>
        </div>
        <div className="space-y-4">
          <AnimatePresence>
            {farms.map((farm) => (
              <FarmCard
                key={farm.id}
                farm={farm}
                active={farm.id === activeId}
                onActivate={() => switchFarm(farm.id)}
                onDelete={() => removeFarm(farm)}
                onSaved={load}
              />
            ))}
          </AnimatePresence>
          <AddFarm onAdded={load} defaultLocation={profile?.default_location ?? ""} />
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-line bg-pale-red px-3 py-2.5">
          <Warning className="mt-0.5 h-4 w-4 shrink-0 text-pale-redink" weight="bold" />
          <p className="text-sm text-pale-redink">{error}</p>
        </div>
      )}
    </div>
  );
}

// ---------- profile ----------
function ProfileCard({ profile, onSaved }: { profile: Profile; onSaved: (p: Profile) => void }) {
  const t = useT();
  const [name, setName] = useState(profile.name ?? "");
  const [phone, setPhone] = useState(profile.phone ?? "");
  const [language, setLanguage] = useState(profile.language ?? "hi");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setSaving(true); setErr(null); setSaved(false);
    try {
      const { profile: updated } = await api.updateProfile({ name: name.trim(), phone: phone.trim(), language });
      onSaved(updated);
      setStoredLang(language);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("Couldn't save."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card interactive={false}>
      <span className="overline">{t("You")}</span>
      <div className="mt-4 space-y-5">
        <Field label={t("Your name")}>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-5">
          <Field label={t("WhatsApp number")} hint={t("Leave empty to stop alerts")}>
            <input className={inputCls} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" />
          </Field>
          <Field label={t("Language")} hint={t("Answers & WhatsApp alerts")}>
            <select className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value)}>
              {LANGS.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
            </select>
          </Field>
        </div>
        {err && <p className="text-sm text-pale-redink">{err}</p>}
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={saving}>
            {saving ? <CircleNotch className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
            {t("Save profile")}
          </Button>
          {saved && <span className="flex items-center gap-1.5 text-sm text-pale-greenink"><CheckCircle className="h-4 w-4" weight="fill" />{t("Saved")}</span>}
        </div>
      </div>
    </Card>
  );
}

// ---------- one farm ----------
function FarmCard({ farm, active, onActivate, onDelete, onSaved }: {
  farm: Farm; active: boolean; onActivate: () => void; onDelete: () => void; onSaved: () => void;
}) {
  const t = useT();
  const router = useRouter();
  const [name, setName] = useState(farm.name ?? farm.location ?? "");
  const [location, setLocation] = useState(farm.location ?? "");
  const [size, setSize] = useState(String(farm.farm_size_acres ?? 1));
  const [farmingType, setFarmingType] = useState(farm.farming_type ?? "Natural Farming");
  const [soilType, setSoilType] = useState(farm.soil?.type ?? "Loamy");
  const [crops, setCrops] = useState<CropRow[]>(farm.crops ?? []);
  const [cropInput, setCropInput] = useState("");
  const [materials, setMaterials] = useState<string[]>(farm.inputs_on_hand ?? []);
  const [materialInput, setMaterialInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  function addCrop() {
    const n = cropInput.trim();
    if (n && !crops.some((c) => c.name.toLowerCase() === n.toLowerCase())) setCrops([...crops, { name: n }]);
    setCropInput("");
  }
  function addMaterial() {
    const m = materialInput.trim();
    if (m && !materials.includes(m)) setMaterials([...materials, m]);
    setMaterialInput("");
  }
  const patchCrop = (i: number, p: Partial<CropRow>) =>
    setCrops(crops.map((c, idx) => (idx === i ? { ...c, ...p } : c)));

  async function save() {
    setSaving(true); setSaved(false);
    try {
      await api.updateFarm(farm.id, {
        name: name.trim(),
        location: location.trim(),
        farm_size_acres: parseFloat(size) || 1,
        farming_type: farmingType,
        soil: { ...(farm.soil ?? {}), type: soilType },
        crops: crops.filter((c) => c.name.trim()),
        inputs_on_hand: materials,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
      <Card interactive={false} className={active ? "ring-1 ring-field-600" : undefined}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border-0 bg-transparent p-0 text-lg font-medium text-ink focus:outline-none"
            />
            <p className="mt-0.5 flex items-center gap-1 text-sm text-muted">
              <MapPin className="h-3.5 w-3.5" /> {farm.location}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {active ? (
              <Tag tone="green" dot>{t("Active")}</Tag>
            ) : (
              <button onClick={onActivate}
                className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-charcoal hover:bg-bone">
                <Star className="h-3.5 w-3.5" /> {t("Set active")}
              </button>
            )}
            <button onClick={onDelete} className="flex h-7 w-7 items-center justify-center rounded-md text-faint hover:bg-bone hover:text-pale-redink" aria-label={t("Delete farm")}>
              <Trash className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <Field label={t("Location (City, State)")}>
            <input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} />
          </Field>
          <Field label={t("Farm size (acres)")}>
            <input className={inputCls} type="number" min="0.1" step="0.1" value={size} onChange={(e) => setSize(e.target.value)} />
          </Field>
          <Field label={t("Farming type")}>
            <select className={inputCls} value={farmingType} onChange={(e) => setFarmingType(e.target.value)}>
              {FARMING_TYPES.map((f) => <option key={f} value={f}>{t(f)}</option>)}
            </select>
          </Field>
          <Field label={t("Soil type")}>
            <select className={inputCls} value={soilType} onChange={(e) => setSoilType(e.target.value)}>
              {SOIL_TYPES.map((s) => <option key={s} value={s}>{t(s)}</option>)}
            </select>
          </Field>
        </div>

        <div className="mt-4">
          <label className="mb-1.5 block text-xs font-medium text-charcoal">{t("Crops")}</label>
          <div className="flex gap-2">
            <input className={inputCls} value={cropInput} onChange={(e) => setCropInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCrop(); } }}
              placeholder={t("Add a crop and press Enter")} />
            <Button type="button" variant="outline" onClick={addCrop} className="!px-3"><Plus className="h-4 w-4" /></Button>
          </div>
          {crops.length > 0 && (
            <div className="mt-3 space-y-0">
              {crops.map((crop, i) => (
                <div key={`${crop.name}-${i}`} className="flex flex-wrap items-center gap-2 border-b border-line py-2.5 last:border-0">
                  <Plant className="h-4 w-4 shrink-0 text-field-600" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{crop.name}</span>
                  <select className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-charcoal focus:outline-none"
                    value={crop.stage ?? ""} onChange={(e) => patchCrop(i, { stage: e.target.value || undefined })}>
                    {STAGES.map((s) => <option key={s} value={s}>{s ? t(s) : t("stage…")}</option>)}
                  </select>
                  <input type="number" min="0" step="0.1" value={crop.area_acres ?? ""} placeholder={t("acres")}
                    onChange={(e) => patchCrop(i, { area_acres: e.target.value ? parseFloat(e.target.value) : undefined })}
                    className="w-16 rounded-md border border-line bg-surface px-2 py-1 text-xs text-charcoal focus:outline-none" />
                  {/* Deep-link pre-fills the calendar. Only the active farm has a
                      calendar in view, so switch to it first if needed. */}
                  <button
                    onClick={() => {
                      const go = () => router.push(`/planner?tab=calendar&crop=${encodeURIComponent(crop.name)}`);
                      active ? go() : (onActivate(), setTimeout(go, 300));
                    }}
                    className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-charcoal hover:bg-bone"
                    title={t("Set a sowing date and build the task calendar")}>
                    <CalendarPlus className="h-3.5 w-3.5" /> {t("Set date")}
                  </button>
                  <button onClick={() => setCrops(crops.filter((_, idx) => idx !== i))} className="text-faint hover:text-pale-redink" aria-label={t("Remove crop")}>
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Materials & fertilizers on hand - the agents prefer these when
            recommending treatments. */}
        <div className="mt-4">
          <label className="mb-1.5 block text-xs font-medium text-charcoal">{t("Materials & fertilizers")}</label>
          <div className="flex gap-2">
            <input className={inputCls} value={materialInput} onChange={(e) => setMaterialInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addMaterial(); } }}
              placeholder={t("What you have, e.g. Vermicompost, Neem oil")} />
            <Button type="button" variant="outline" onClick={addMaterial} className="!px-3"><Plus className="h-4 w-4" /></Button>
          </div>
          {materials.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {materials.map((m) => (
                <span key={m} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-bone px-2.5 py-1 text-xs text-charcoal">
                  {m}
                  <button onClick={() => setMaterials(materials.filter((x) => x !== m))} className="text-faint hover:text-pale-redink"><X className="h-3 w-3" /></button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button onClick={save} disabled={saving} variant="outline">
            {saving ? <CircleNotch className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
            {t("Save farm")}
          </Button>
          {saved && <span className="flex items-center gap-1.5 text-sm text-pale-greenink"><CheckCircle className="h-4 w-4" weight="fill" />{t("Saved")}</span>}
        </div>
      </Card>
    </motion.div>
  );
}

// ---------- add farm ----------
// Same fields as the farm edit card, so a new farm is as complete as an edited one.
function AddFarm({ onAdded, defaultLocation }: { onAdded: () => void; defaultLocation: string }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [location, setLocation] = useState(defaultLocation);
  const [size, setSize] = useState("1");
  const [farmingType, setFarmingType] = useState("Natural Farming");
  const [soilType, setSoilType] = useState("Loamy");
  const [crops, setCrops] = useState<string[]>([]);
  const [cropInput, setCropInput] = useState("");
  const [materials, setMaterials] = useState<string[]>([]);
  const [materialInput, setMaterialInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function reset() {
    setName(""); setLocation(defaultLocation); setSize("1");
    setFarmingType("Natural Farming"); setSoilType("Loamy");
    setCrops([]); setCropInput(""); setMaterials([]); setMaterialInput("");
    setErr(null);
  }
  function addCrop() {
    const c = cropInput.trim();
    if (c && !crops.includes(c)) setCrops([...crops, c]);
    setCropInput("");
  }
  function addMaterial() {
    const m = materialInput.trim();
    if (m && !materials.includes(m)) setMaterials([...materials, m]);
    setMaterialInput("");
  }

  async function create() {
    setErr(null);
    if (!name.trim() || !location.trim() || crops.length === 0) {
      setErr(t("Add a farm name, location, and at least one crop."));
      return;
    }
    setSaving(true);
    try {
      await api.createFarm({
        name: name.trim(),
        location: location.trim(),
        farm_size_acres: parseFloat(size) || 1,
        farming_type: farmingType,
        crops: crops.map((n) => ({ name: n })),
        soil: { type: soilType },
        inputs_on_hand: materials,
      });
      reset();
      setOpen(false);
      onAdded();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("Couldn't add the farm."));
    } finally {
      setSaving(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-line py-4 text-sm font-medium text-muted transition-colors hover:border-faint/50 hover:text-charcoal">
        <Plus className="h-4 w-4" /> {t("Add another farm")}
      </button>
    );
  }

  return (
    <Card interactive={false}>
      <span className="overline">{t("New farm")}</span>
      <div className="mt-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("Farm name")}>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("e.g. River field")} />
          </Field>
          <Field label={t("Location (City, State)")}>
            <input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} placeholder={t("e.g. Pune, Maharashtra")} />
          </Field>
          <Field label={t("Farm size (acres)")}>
            <input className={inputCls} type="number" min="0.1" step="0.1" value={size} onChange={(e) => setSize(e.target.value)} />
          </Field>
          <Field label={t("Farming type")}>
            <select className={inputCls} value={farmingType} onChange={(e) => setFarmingType(e.target.value)}>
              {FARMING_TYPES.map((f) => <option key={f} value={f}>{t(f)}</option>)}
            </select>
          </Field>
          <Field label={t("Soil type")}>
            <select className={inputCls} value={soilType} onChange={(e) => setSoilType(e.target.value)}>
              {SOIL_TYPES.map((s) => <option key={s} value={s}>{t(s)}</option>)}
            </select>
          </Field>
        </div>

        <Field label={t("Crops")}>
          <div className="flex gap-2">
            <input className={inputCls} value={cropInput} onChange={(e) => setCropInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCrop(); } }}
              placeholder={t("Add a crop and press Enter")} />
            <Button type="button" variant="outline" onClick={addCrop} className="!px-3"><Plus className="h-4 w-4" /></Button>
          </div>
          {crops.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {crops.map((c) => (
                <span key={c} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-bone px-2.5 py-1 text-xs text-charcoal">
                  {c}<button onClick={() => setCrops(crops.filter((x) => x !== c))} className="text-faint hover:text-pale-redink"><X className="h-3 w-3" /></button>
                </span>
              ))}
            </div>
          )}
        </Field>

        <Field label={t("Materials & fertilizers")} hint={t("Optional - what you already have")}>
          <div className="flex gap-2">
            <input className={inputCls} value={materialInput} onChange={(e) => setMaterialInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addMaterial(); } }}
              placeholder={t("e.g. Vermicompost, Neem oil")} />
            <Button type="button" variant="outline" onClick={addMaterial} className="!px-3"><Plus className="h-4 w-4" /></Button>
          </div>
          {materials.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {materials.map((m) => (
                <span key={m} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-bone px-2.5 py-1 text-xs text-charcoal">
                  {m}<button onClick={() => setMaterials(materials.filter((x) => x !== m))} className="text-faint hover:text-pale-redink"><X className="h-3 w-3" /></button>
                </span>
              ))}
            </div>
          )}
        </Field>

        {err && <p className="text-sm text-pale-redink">{err}</p>}
        <div className="flex gap-2">
          <Button onClick={create} disabled={saving}>
            {saving ? <CircleNotch className="h-4 w-4 animate-spin" /> : <Plant className="h-4 w-4" />}
            {t("Create farm")}
          </Button>
          <Button variant="ghost" onClick={() => { reset(); setOpen(false); }}>{t("Cancel")}</Button>
        </div>
      </div>
    </Card>
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
