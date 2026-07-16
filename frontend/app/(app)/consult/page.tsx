"use client";
import { api, ApiError, type ConsultResult } from "@/lib/api";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { TextGenerate } from "@/components/ui/text-generate";
import { motion, AnimatePresence } from "framer-motion";
import {
  Microphone,
  PaperPlaneRight,
  SpeakerHigh,
  Brain,
  Scan,
  Plant,
  CloudRain,
  TrendUp,
  Bank,
  ShieldWarning,
  CircleNotch,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n-runtime";
import { getStoredLang } from "@/lib/i18n";

// Web Speech locale for the farmer's chosen language (all supported langs use the
// India locale: hi-IN, pa-IN, ta-IN, bn-IN …). Used for both STT input and TTS.
const sttLocale = () => `${getStoredLang() || "hi"}-IN`;

const AGENT_META: Record<string, { icon: any; label: string }> = {
  crop_health: { icon: Scan, label: "Crop Health" },
  natural_farming: { icon: Plant, label: "Natural Farming" },
  weather: { icon: CloudRain, label: "Weather" },
  market: { icon: TrendUp, label: "Market" },
  finance: { icon: Bank, label: "Finance" },
  risk: { icon: ShieldWarning, label: "Risk" },
};

/** The answer in the requested language, falling back to the other one. Returns
 *  undefined when the agents produced nothing usable (`_parse_error`). */
function answerText(res: ConsultResult, lang: "en" | "local"): string | undefined {
  const { answer_en, answer_local } = res.result;
  const text = lang === "en" ? answer_en || answer_local : answer_local || answer_en;
  return text?.trim() ? text : undefined;
}

const SUGGESTIONS = [
  "My tomato leaves have white spots - should I spray neem tomorrow?",
  "Mere tamatar ke patte peele ho rahe hain, kya karu?",
  "Should I sell my tomatoes now or wait?",
  "What government schemes can I apply for?",
];

export default function ConsultPage() {
  const t = useT();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ConsultResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<"en" | "local">("local");
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = true;
    rec.lang = sttLocale();
    rec.onresult = (e: any) => setQuery(Array.from(e.results).map((r: any) => r[0].transcript).join(""));
    rec.onend = () => setListening(false);
    recognitionRef.current = rec;
  }, []);

  function toggleMic() {
    const rec = recognitionRef.current;
    if (!rec) return alert(t("Voice input needs Chrome or Edge. You can type instead."));
    if (listening) {
      rec.stop();
      setListening(false);
    } else {
      rec.lang = sttLocale(); // re-bind in case the language was changed
      setQuery("");
      rec.start();
      setListening(true);
    }
  }

  function speak(text: string, ttsLocale: string) {
    if (!text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = ttsLocale;
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  }

  async function submit(q?: string) {
    const text = (q ?? query).trim();
    if (!text || loading) return;
    setQuery(text);
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await api.consult(text);
      setResult(res);
      const spoken = res.result.answer_local || res.result.answer_en;
      if (spoken) speak(spoken, res.language?.tts || sttLocale());
    } catch (e) {
      // The server distinguishes these; surfacing its message is far more useful
      // than a blanket "is the backend running?".
      if (e instanceof ApiError) {
        if (e.status === 429) {
          setError(t("You're asking a bit too quickly. Please wait a moment and try again."));
        } else if (e.status === 400) {
          setError(e.message); // guard rejection - already farmer-friendly
        } else if (e.status === 404) {
          setError(t("Complete onboarding first so I know your farm."));
        } else {
          setError(t("Something went wrong reaching the agents. Please try again."));
        }
      } else {
        setError(t("Couldn't reach KrishiMitra. Check your connection and try again."));
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" dot className="mb-3">{t("Multi-agent consultation")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Talk to KrishiMitra")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Ask by voice or text in Hindi or English. The Planner routes your question to the right specialists and returns one clear plan - read aloud in your language.")}
        </p>
      </div>

      {/* input */}
      <div className="card p-2.5">
        <div className="flex items-end gap-2">
          <button
            onClick={toggleMic}
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md transition-colors ${
              listening ? "bg-pale-red text-pale-redink" : "bg-bone text-charcoal hover:bg-line"
            }`}
          >
            <Microphone className="h-5 w-5" weight={listening ? "fill" : "regular"} />
          </button>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={listening ? t("Listening…") : t("Ask about disease, weather, prices, schemes…")}
            className="max-h-32 flex-1 resize-none bg-transparent py-2.5 text-[15px] text-ink placeholder:text-faint focus:outline-none"
          />
          <Button onClick={() => submit()} disabled={loading || !query.trim()} className="h-11 w-11 !p-0">
            {loading ? <CircleNotch className="h-5 w-5 animate-spin" /> : <PaperPlaneRight className="h-5 w-5" weight="fill" />}
          </Button>
        </div>
      </div>

      {!result && !loading && (
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-muted transition-colors hover:border-faint/50 hover:text-charcoal"
            >
              {t(s)}
            </button>
          ))}
        </div>
      )}

      {loading && <OrchestrationLoader />}

      {error && !loading && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 rounded-md border border-line bg-pale-red p-4"
        >
          <ShieldWarning className="mt-0.5 h-4 w-4 shrink-0 text-pale-redink" />
          <p className="text-sm leading-relaxed text-pale-redink">{error}</p>
        </motion.div>
      )}

      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
            {/* The agronomic safety guardrail withheld the model's advice. Be explicit
                that this is a deliberate safety hold, not a failure to understand. */}
            {result.result._blocked && (
              <div className="flex items-start gap-3 rounded-md border border-line bg-pale-yellow p-4">
                <ShieldWarning className="mt-0.5 h-4 w-4 shrink-0 text-pale-yellowink" />
                <p className="text-sm leading-relaxed text-pale-yellowink">
                  {t("I held this answer back because I couldn't verify it against my agronomy knowledge base. I'd rather say nothing than give you a wrong dosage.")}
                </p>
              </div>
            )}

            {/* plan trace */}
            <Card interactive={false}>
              <div className="mb-3 flex items-center gap-2">
                <Brain className="h-4 w-4 text-field-600" />
                <span className="text-sm font-medium text-ink">{t("Planner")}</span>
                <span className="text-xs text-muted">{t("routed to")} {result.agents_run.length} {t("agents")}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {result.agents_run.map((a) => {
                  const meta = AGENT_META[a];
                  if (!meta) return null;
                  const Icon = meta.icon;
                  return (
                    <span key={a} className="inline-flex items-center gap-1.5 rounded-md border border-line bg-bone px-2.5 py-1 text-xs text-charcoal">
                      <Icon className="h-3.5 w-3.5" /> {t(meta.label)}
                    </span>
                  );
                })}
              </div>
              {result.plan.intent && <p className="mt-3 font-mono text-xs text-faint">intent: {result.plan.intent}</p>}
            </Card>

            {/* answer */}
            <Card interactive={false}>
              <div className="mb-4 flex items-center justify-between">
                <span className="overline">{t("KrishiMitra says")}</span>
                <div className="flex items-center gap-1.5">
                  <div className="flex rounded-md border border-line p-0.5 text-xs">
                    {(["local", "en"] as const).map((l) => (
                      <button
                        key={l}
                        onClick={() => setLang(l)}
                        className={`rounded px-2.5 py-1 transition-colors ${lang === l ? "bg-bone text-ink" : "text-faint"}`}
                      >
                        {l === "en" ? "EN" : result.language?.native ?? "Local"}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={() =>
                      speak(
                        answerText(result, lang) ?? "",
                        lang === "en" ? "en-IN" : result.language?.tts || sttLocale(),
                      )
                    }
                    className="flex h-8 w-8 items-center justify-center rounded-md bg-bone text-charcoal hover:bg-line"
                  >
                    <SpeakerHigh className="h-4 w-4" />
                  </button>
                </div>
              </div>
              {answerText(result, lang) ? (
                <TextGenerate
                  key={lang}
                  text={answerText(result, lang)!}
                  className="font-serif text-xl leading-relaxed text-ink"
                />
              ) : (
                // The agents returned nothing usable (unparseable even after the
                // backend's retry). Say so plainly instead of rendering an empty card.
                <p className="font-serif text-lg leading-relaxed text-muted">
                  {t("I couldn't put together a clear answer for that. Please try asking again, in a bit more detail.")}
                </p>
              )}
            </Card>

            {/* action plan */}
            {(result.result.action_plan?.length ?? 0) > 0 && (
              <Card interactive={false}>
                <span className="overline">{t("Today's action plan")}</span>
                <div className="mt-4 space-y-0">
                  {result.result.action_plan!.map((step, i) => (
                    <motion.div
                      key={step.step}
                      initial={{ opacity: 0, x: -6 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.07 }}
                      className="flex gap-3 border-b border-line py-3.5 last:border-0"
                    >
                      <span className="font-mono text-sm text-faint">{String(step.step).padStart(2, "0")}</span>
                      <div className="flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-medium text-ink">{t(step.action)}</p>
                          <Tag tone="neutral">{t(step.when)}</Tag>
                        </div>
                        {step.why && <p className="mt-0.5 text-sm text-muted">{t(step.why)}</p>}
                      </div>
                    </motion.div>
                  ))}
                </div>
              </Card>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function OrchestrationLoader() {
  const t = useT();
  const steps = [
    { icon: Brain, label: "Planner analysing your question" },
    { icon: Scan, label: "Specialist agents working in parallel" },
    { icon: Plant, label: "Action Planner synthesising your plan" },
  ];
  return (
    <Card interactive={false}>
      <div className="space-y-3">
        {steps.map((s, i) => {
          const Icon = s.icon;
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0.35 }}
              animate={{ opacity: [0.35, 1, 0.35] }}
              transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.4 }}
              className="flex items-center gap-3"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-bone text-charcoal">
                <Icon className="h-4 w-4" />
              </span>
              <span className="text-sm text-charcoal">{t(s.label)}</span>
              <CircleNotch className="ml-auto h-3.5 w-3.5 animate-spin text-faint" />
            </motion.div>
          );
        })}
      </div>
    </Card>
  );
}
