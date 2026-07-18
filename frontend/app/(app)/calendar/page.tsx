"use client";

import { api, ApiError, type CropCycle, type CalendarTask, type TaskKind } from "@/lib/api";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plant,
  Drop,
  Leaf,
  SprayBottle,
  MagnifyingGlass,
  Basket,
  DotsThree,
  CircleNotch,
  Plus,
  Check,
  Trash,
  BellRinging,
} from "@phosphor-icons/react";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n-runtime";

const KIND_META: Record<TaskKind, { icon: any; tone: "green" | "blue" | "yellow" | "neutral" }> = {
  sowing: { icon: Plant, tone: "green" },
  irrigation: { icon: Drop, tone: "blue" },
  nutrition: { icon: Leaf, tone: "green" },
  spray: { icon: SprayBottle, tone: "yellow" },
  scouting: { icon: MagnifyingGlass, tone: "neutral" },
  harvest: { icon: Basket, tone: "green" },
  other: { icon: DotsThree, tone: "neutral" },
};

const fmt = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/** Whole days from today to `iso` (negative = overdue). Compared date-only, so a
 *  task due today reads as "Today" regardless of the current time. */
function daysAway(iso: string, todayIso: string): number {
  const a = new Date(iso + "T00:00:00").getTime();
  const b = new Date(todayIso + "T00:00:00").getTime();
  return Math.round((a - b) / 86_400_000);
}

// useSearchParams() needs a Suspense boundary above it, or the build fails with
// "should be wrapped in a suspense boundary".
export default function CalendarPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><CircleNotch className="h-6 w-6 animate-spin text-faint" /></div>}>
      <Calendar />
    </Suspense>
  );
}

function Calendar() {
  const t = useT();
  const params = useSearchParams();
  const [cycles, setCycles] = useState<CropCycle[] | null>(null);
  const [today, setToday] = useState<string>(new Date().toISOString().slice(0, 10));
  const [farmCrops, setFarmCrops] = useState<string[]>([]);
  const [crop, setCrop] = useState("");
  const [sownOn, setSownOn] = useState(new Date().toISOString().slice(0, 10));
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const res = await api.calendar();
      setCycles(res.cycles);
      setToday(res.today);
    } catch {
      setCycles([]);
    }
  }

  useEffect(() => {
    load();
    // Offer the farm's own crops rather than making the farmer retype a name -
    // and a typo here means mandi lookups and the KB miss.
    api
      .farm()
      .then(({ farm }) => setFarmCrops((farm.crops ?? []).map((c) => c.name).filter(Boolean)))
      .catch(() => setFarmCrops([]));
  }, []);

  // Deep link from the profile page ("Set date" on a crop) pre-fills the crop.
  useEffect(() => {
    const preset = params.get("crop");
    if (preset) setCrop(preset);
  }, [params]);

  async function addCycle() {
    if (!crop.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      await api.createCycle(crop.trim(), sownOn);
      setCrop("");
      await load();
    } catch (e) {
      if (e instanceof ApiError) {
        // 422 = generation failed or the safety guardrail withheld the calendar;
        // the server's message is already farmer-readable.
        setError(e.status === 429 ? t("Too many calendars too quickly. Please wait a moment.") : e.message);
      } else {
        setError(t("Couldn't create the calendar. Check your connection."));
      }
    } finally {
      setCreating(false);
    }
  }

  async function toggle(task: CalendarTask) {
    // Optimistic: ticking a task should feel instant; reload reconciles.
    setCycles((cs) =>
      cs?.map((c) => ({
        ...c,
        tasks: c.tasks.map((x) => (x.id === task.id ? { ...x, done: !x.done } : x)),
      })) ?? null,
    );
    try {
      await api.setTaskDone(task.id, !task.done);
    } catch {
      load(); // put it back if the server disagreed
    }
  }

  async function remove(cycle: CropCycle) {
    if (!confirm(t("Delete this crop cycle and all its reminders?"))) return;
    try {
      await api.deleteCycle(cycle.id);
      await load();
    } catch {
      setError(t("Couldn't delete that cycle."));
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" dot className="mb-3">{t("Sowing → harvest")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Crop calendar")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Tell me what you sowed and when. I'll build the full natural-farming timeline and remind you on WhatsApp before each task is due.")}
        </p>
      </div>

      {/* new cycle */}
      <Card interactive={false}>
        <span className="overline">{t("Start a crop cycle")}</span>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          {/* Free text, but suggests the crops already on the farm profile. A
              mistyped name silently misses both the mandi listing and the KB. */}
          <input
            list="farm-crops"
            value={crop}
            onChange={(e) => setCrop(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCycle()}
            placeholder={farmCrops.length ? t("Pick or type a crop") : t("Which crop? e.g. Tomato")}
            className="flex-1 rounded-md border border-line bg-surface px-4 py-2.5 text-sm text-ink placeholder:text-faint focus:border-faint/50 focus:outline-none"
          />
          <datalist id="farm-crops">
            {farmCrops.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <input
            type="date"
            value={sownOn}
            onChange={(e) => setSownOn(e.target.value)}
            className="rounded-md border border-line bg-surface px-4 py-2.5 text-sm text-ink focus:border-faint/50 focus:outline-none"
          />
          <Button onClick={addCycle} disabled={creating || !crop.trim()}>
            {creating ? <CircleNotch className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            {creating ? t("Building timeline…") : t("Add")}
          </Button>
        </div>
        {error && <p className="mt-2.5 text-sm text-pale-redink">{error}</p>}
      </Card>

      {cycles === null && (
        <div className="flex justify-center py-10">
          <CircleNotch className="h-6 w-6 animate-spin text-faint" />
        </div>
      )}

      {cycles?.length === 0 && (
        <p className="py-6 text-center text-sm text-muted">
          {t("No crop cycles yet. Add one above to get your timeline and reminders.")}
        </p>
      )}

      <AnimatePresence>
        {cycles?.map((cycle) => {
          const done = cycle.tasks.filter((x) => x.done).length;
          const pct = cycle.tasks.length ? Math.round((done / cycle.tasks.length) * 100) : 0;
          return (
            <motion.div key={cycle.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
              <Card interactive={false}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-medium text-ink">{t(cycle.crop)}</h2>
                      {cycle.status === "harvested" && <Tag tone="neutral">{t("Harvested")}</Tag>}
                    </div>
                    <p className="mt-0.5 text-sm text-muted">
                      {t("Sown")} {fmt(cycle.sown_on)}
                      {cycle.expected_harvest_on && <> · {t("harvest ~")}{fmt(cycle.expected_harvest_on)}</>}
                    </p>
                  </div>
                  <button
                    onClick={() => remove(cycle)}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-faint transition-colors hover:bg-bone hover:text-pale-redink"
                    aria-label={t("Delete cycle")}
                  >
                    <Trash className="h-4 w-4" />
                  </button>
                </div>

                {/* progress */}
                <div className="mt-3 flex items-center gap-3">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bone">
                    <div className="h-full rounded-full bg-field-600 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono text-xs text-faint">{done}/{cycle.tasks.length}</span>
                </div>

                {/* timeline */}
                <div className="mt-4 space-y-0">
                  {cycle.tasks.map((task) => {
                    const meta = KIND_META[task.kind] ?? KIND_META.other;
                    const Icon = meta.icon;
                    const away = daysAway(task.due_on, today);
                    const overdue = away < 0 && !task.done;
                    const soon = away >= 0 && away <= 2 && !task.done;
                    return (
                      <div
                        key={task.id}
                        className="flex items-start gap-3 border-b border-line py-3 last:border-0"
                      >
                        <button
                          onClick={() => toggle(task)}
                          className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
                            task.done
                              ? "border-field-600 bg-field-600 text-paper"
                              : "border-line hover:border-faint"
                          }`}
                          aria-label={task.done ? t("Mark not done") : t("Mark done")}
                        >
                          {task.done && <Check className="h-3 w-3" weight="bold" />}
                        </button>

                        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${task.done ? "text-faint" : "text-field-600"}`} />

                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className={`text-sm ${task.done ? "text-faint line-through" : "font-medium text-ink"}`}>
                              {t(task.title)}
                            </p>
                            {overdue && <Tag tone="red">{t("Overdue")}</Tag>}
                            {soon && <Tag tone="yellow">{away === 0 ? t("Today") : t("Soon")}</Tag>}
                            {task.notified_on && !task.done && (
                              <BellRinging className="h-3 w-3 text-faint" aria-label={t("Reminder sent")} />
                            )}
                          </div>
                          {task.detail && !task.done && (
                            <p className="mt-0.5 text-sm text-muted">{t(task.detail)}</p>
                          )}
                        </div>

                        <span className="shrink-0 font-mono text-xs text-faint">{fmt(task.due_on)}</span>
                      </div>
                    );
                  })}
                </div>
              </Card>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
