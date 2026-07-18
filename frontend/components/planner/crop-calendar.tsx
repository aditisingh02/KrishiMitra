"use client";

import { api, ApiError, type CropCycle, type CalendarTask, type TaskKind } from "@/lib/api";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plant, Drop, Leaf, SprayBottle, MagnifyingGlass, Basket, DotsThree,
  CircleNotch, Plus, Check, Trash, BellRinging, ChatCircleText,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n-runtime";

const KIND_META: Record<TaskKind, { icon: any }> = {
  sowing: { icon: Plant }, irrigation: { icon: Drop }, nutrition: { icon: Leaf },
  spray: { icon: SprayBottle }, scouting: { icon: MagnifyingGlass },
  harvest: { icon: Basket }, other: { icon: DotsThree },
};

const todayIso = () => new Date().toISOString().slice(0, 10);
const fmt = (iso: string | null) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "";
const norm = (s: string) => s.trim().toLowerCase();

/** Whole days from today to `iso` (negative = overdue). */
function daysAway(iso: string, today: string): number {
  return Math.round((new Date(iso + "T00:00:00").getTime() - new Date(today + "T00:00:00").getTime()) / 86_400_000);
}

/**
 * The crop calendar - the Planner's primary view. Auto-loads, shows EVERY crop on
 * the farm with its sowing→harvest timeline and dated tasks; crops with no cycle
 * get an inline "build calendar". Plus a "From your questions" section for plans
 * added from consult answers.
 */
export function CropCalendar() {
  const t = useT();
  const params = useSearchParams();
  const [cycles, setCycles] = useState<CropCycle[] | null>(null);
  const [general, setGeneral] = useState<CalendarTask[]>([]);
  const [today, setToday] = useState<string>(todayIso());
  const [farmCrops, setFarmCrops] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const res = await api.calendar();
      setCycles(res.cycles);
      setGeneral(res.general_tasks ?? []);
      setToday(res.today);
    } catch {
      setCycles([]);
    }
  }

  useEffect(() => {
    load();
    api.farm()
      .then(({ farm }) => setFarmCrops((farm.crops ?? []).map((c) => c.name).filter(Boolean)))
      .catch(() => setFarmCrops([]));
  }, []);

  const presetCrop = params.get("crop");

  async function toggle(task: CalendarTask) {
    const flip = (x: CalendarTask) => (x.id === task.id ? { ...x, done: !x.done } : x);
    setCycles((cs) => cs?.map((c) => ({ ...c, tasks: c.tasks.map(flip) })) ?? null);
    setGeneral((g) => g.map(flip));
    try {
      await api.setTaskDone(task.id, !task.done);
    } catch {
      load();
    }
  }

  async function removeCycle(cycle: CropCycle) {
    if (!confirm(t("Delete this crop cycle and all its tasks?"))) return;
    try { await api.deleteCycle(cycle.id); await load(); }
    catch { setError(t("Couldn't delete that cycle.")); }
  }

  async function removeTask(id: number) {
    setGeneral((g) => g.filter((x) => x.id !== id)); // optimistic
    try { await api.deleteTask(id); }
    catch { load(); }
  }

  if (cycles === null) {
    return <div className="flex justify-center py-16"><CircleNotch className="h-6 w-6 animate-spin text-faint" /></div>;
  }

  // Every crop = the farm's crops + any orphan cycle whose crop isn't in the profile.
  const cropOrder: string[] = [];
  const seen = new Set<string>();
  for (const c of farmCrops) { const k = norm(c); if (!seen.has(k)) { seen.add(k); cropOrder.push(c); } }
  for (const cy of cycles) { const k = norm(cy.crop); if (!seen.has(k)) { seen.add(k); cropOrder.push(cy.crop); } }
  const cyclesFor = (crop: string) => cycles.filter((c) => norm(c.crop) === norm(crop));

  return (
    <div className="space-y-5">
      {error && <p className="text-sm text-pale-redink">{error}</p>}

      {cropOrder.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">
          {t("Add crops to your farm profile, then build a sowing calendar for each here.")}
        </p>
      )}

      {/* one section per crop */}
      {cropOrder.map((crop) => (
        <div key={crop}>
          <div className="mb-2 flex items-center gap-2 px-1">
            <Plant className="h-4 w-4 text-field-600" weight="fill" />
            <h2 className="text-lg font-medium text-ink">{t(crop)}</h2>
          </div>
          {cyclesFor(crop).length > 0 ? (
            <div className="space-y-3">
              {cyclesFor(crop).map((cycle) => (
                <CycleCard key={cycle.id} cycle={cycle} today={today} onToggle={toggle} onDelete={removeCycle} />
              ))}
            </div>
          ) : (
            <BuildCalendar crop={crop} defaultOpen={!!presetCrop && norm(presetCrop) === norm(crop)} onBuilt={load} />
          )}
        </div>
      ))}

      {/* a crop not in the profile */}
      <BuildCalendar crop="" onBuilt={load} otherLabel />

      {/* plans added from consult answers */}
      {general.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-2 px-1 text-sm font-medium text-charcoal">
            <ChatCircleText className="h-4 w-4 text-field-600" /> {t("From your questions")}
          </div>
          <Card interactive={false}>
            <div className="space-y-0">
              {/* dated first, then undated */}
              {[...general].sort((a, b) => (a.due_on ? 0 : 1) - (b.due_on ? 0 : 1)).map((task) => (
                <TaskRow key={task.id} task={task} today={today} onToggle={toggle} onDelete={() => removeTask(task.id)} />
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function CycleCard({ cycle, today, onToggle, onDelete }: {
  cycle: CropCycle; today: string; onToggle: (t: CalendarTask) => void; onDelete: (c: CropCycle) => void;
}) {
  const t = useT();
  const done = cycle.tasks.filter((x) => x.done).length;
  const pct = cycle.tasks.length ? Math.round((done / cycle.tasks.length) * 100) : 0;
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <Card interactive={false} className={cycle.status === "harvested" ? "opacity-70" : undefined}>
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm text-muted">
            {t("Sown")} {fmt(cycle.sown_on)}
            {cycle.expected_harvest_on && <> · {t("harvest ~")}{fmt(cycle.expected_harvest_on)}</>}
            {cycle.status === "harvested" && <> · <Tag tone="neutral">{t("Harvested")}</Tag></>}
          </p>
          <button onClick={() => onDelete(cycle)} className="flex h-7 w-7 items-center justify-center rounded-md text-faint hover:bg-bone hover:text-pale-redink" aria-label={t("Delete cycle")}>
            <Trash className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bone">
            <div className="h-full rounded-full bg-field-600 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <span className="font-mono text-xs text-faint">{done}/{cycle.tasks.length}</span>
        </div>
        <div className="mt-3 space-y-0">
          {cycle.tasks.map((task) => (
            <TaskRow key={task.id} task={task} today={today} onToggle={onToggle} />
          ))}
        </div>
      </Card>
    </motion.div>
  );
}

function TaskRow({ task, today, onToggle, onDelete }: {
  task: CalendarTask; today: string; onToggle: (t: CalendarTask) => void; onDelete?: () => void;
}) {
  const t = useT();
  const Icon = (KIND_META[task.kind] ?? KIND_META.other).icon;
  const away = task.due_on ? daysAway(task.due_on, today) : null;
  const overdue = away !== null && away < 0 && !task.done;
  const soon = away !== null && away >= 0 && away <= 2 && !task.done;
  return (
    <div className="flex items-start gap-3 border-b border-line py-3 last:border-0">
      <button
        onClick={() => onToggle(task)}
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
          task.done ? "border-field-600 bg-field-600 text-paper" : "border-line hover:border-faint"
        }`}
        aria-label={task.done ? t("Mark not done") : t("Mark done")}
      >
        {task.done && <Check className="h-3 w-3" weight="bold" />}
      </button>
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${task.done ? "text-faint" : "text-field-600"}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className={`text-sm ${task.done ? "text-faint line-through" : "font-medium text-ink"}`}>{t(task.title)}</p>
          {overdue && <Tag tone="red">{t("Overdue")}</Tag>}
          {soon && <Tag tone="yellow">{away === 0 ? t("Today") : t("Soon")}</Tag>}
          {!task.due_on && <Tag tone="neutral">{t("No fixed date")}</Tag>}
          {task.notified_on && !task.done && <BellRinging className="h-3 w-3 text-faint" aria-label={t("Reminder sent")} />}
        </div>
        {task.detail && !task.done && <p className="mt-0.5 text-sm text-muted">{t(task.detail)}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="font-mono text-xs text-faint">{fmt(task.due_on)}</span>
        {onDelete && (
          <button onClick={onDelete} className="text-faint hover:text-pale-redink" aria-label={t("Remove")}>
            <Trash className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

function BuildCalendar({ crop, defaultOpen, onBuilt, otherLabel }: {
  crop: string; defaultOpen?: boolean; onBuilt: () => void; otherLabel?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = useState(!!defaultOpen);
  const [name, setName] = useState(crop);
  const [sownOn, setSownOn] = useState(todayIso());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function build() {
    const cropName = (otherLabel ? name : crop).trim();
    if (!cropName || busy) return;
    setBusy(true); setErr(null);
    try {
      await api.createCycle(cropName, sownOn);
      setName(""); setOpen(false);
      onBuilt();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("Couldn't build the calendar."));
    } finally {
      setBusy(false);
    }
  }

  if (otherLabel && !open) {
    return (
      <button onClick={() => setOpen(true)} className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-line py-3 text-sm text-muted hover:border-faint/50 hover:text-charcoal">
        <Plus className="h-4 w-4" /> {t("Add a calendar for another crop")}
      </button>
    );
  }
  if (!otherLabel && !open) {
    return (
      <button onClick={() => setOpen(true)} className="flex w-full items-center gap-2 rounded-md border border-dashed border-line px-4 py-3 text-sm text-muted hover:border-faint/50 hover:text-charcoal">
        <Plus className="h-4 w-4" /> {t("Set a sowing date to build this crop's calendar")}
      </button>
    );
  }

  return (
    <Card interactive={false}>
      <div className="flex flex-col gap-2 sm:flex-row">
        {otherLabel && (
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("Which crop?")}
            className="flex-1 rounded-md border border-line bg-surface px-4 py-2.5 text-sm text-ink placeholder:text-faint focus:border-faint/50 focus:outline-none" />
        )}
        <input type="date" value={sownOn} onChange={(e) => setSownOn(e.target.value)}
          className="rounded-md border border-line bg-surface px-4 py-2.5 text-sm text-ink focus:border-faint/50 focus:outline-none" />
        <Button onClick={build} disabled={busy || (otherLabel && !name.trim())}>
          {busy ? <CircleNotch className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          {busy ? t("Building timeline…") : t("Build calendar")}
        </Button>
        {!otherLabel && <Button variant="ghost" onClick={() => setOpen(false)}>{t("Cancel")}</Button>}
      </div>
      {err && <p className="mt-2 text-sm text-pale-redink">{err}</p>}
    </Card>
  );
}
