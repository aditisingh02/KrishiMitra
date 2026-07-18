"use client";
import { api, ApiError, type Interaction } from "@/lib/api";
import { downscaleImage } from "@/lib/image";
import { Tag, Button, Card } from "@/components/ui/primitives";
import { motion, AnimatePresence } from "framer-motion";
import {
  UploadSimple,
  Scan,
  CircleNotch,
  SpeakerHigh,
  Plant,
  Warning,
  CheckCircle,
  X,
  ClockCounterClockwise,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n-runtime";
import { getStoredLang } from "@/lib/i18n";

const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);

export default function DiagnosePage() {
  const t = useT();
  const [preview, setPreview] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sizes, setSizes] = useState<{ from: number; to: number } | null>(null);
  const [compressing, setCompressing] = useState(false);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<Interaction[]>([]);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const previewUrl = useRef<string | null>(null);

  // Past diagnoses for the active farm (result only - no image is stored).
  useEffect(() => {
    api.diagnoseHistory().then(({ items }) => setHistory(items)).catch(() => {});
  }, []);

  function setPreviewUrl(url: string | null) {
    // Object URLs pin the blob in memory until revoked - always release the old one.
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
    previewUrl.current = url;
    setPreview(url);
  }

  // Revoke on unmount so navigating away doesn't leak the blob.
  useEffect(() => () => {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current);
  }, []);

  async function onFile(f: File) {
    if (!f.type.startsWith("image/")) return;
    setResult(null);
    setSizes(null);
    setCompressing(true);
    try {
      // Downscale at selection, not at submit: by the time the farmer hits
      // "Diagnose" the upload is already ~250KB instead of several MB. The
      // preview reuses the downscaled blob (readAsDataURL on a 4MB photo
      // visibly janks a low-end Android).
      const out = await downscaleImage(f);
      setFile(out.file);
      setPreviewUrl(out.previewUrl);
      setSizes(out.resized ? { from: out.originalBytes, to: out.bytes } : null);
    } finally {
      setCompressing(false);
    }
  }

  async function diagnose() {
    if (!file || loading) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await api.diagnose(file, note);
      setResult(res.diagnosis);
      const d = res.diagnosis;
      if (d && !d._parse_error) {
        const tr = d.natural_treatment || {};
        setHistory((h) => [
          {
            id: Date.now(),
            kind: "diagnose",
            query: note || "Photo diagnosis",
            answer: d.explanation_local ?? null,
            answer_en: tr.remedy ?? null,
            payload: {
              issue: d.issue, category: d.category, severity: d.severity,
              confidence: d.confidence, crop_guess: d.crop_guess, remedy: tr.remedy,
            },
            blocked: false,
            created_at: new Date().toISOString(),
          },
          ...h,
        ]);
      }
      if (res.diagnosis?.explanation_local) {
        const u = new SpeechSynthesisUtterance(res.diagnosis.explanation_local);
        u.lang = res.diagnosis.language?.tts || `${getStoredLang() || "hi"}-IN`;
        window.speechSynthesis.speak(u);
      }
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 429) alert(t("Too many photos too quickly. Please wait a moment and try again."));
        else if (e.status === 413) alert(t("That photo is too large. Please try another one."));
        else if (e.status === 415) alert(t("Unsupported image type. Please send a JPEG or PNG photo."));
        else if (e.status === 404) alert(t("Complete onboarding first so I know your farm."));
        else alert(t("Diagnosis failed. Please try again."));
      } else {
        alert(t("Couldn't reach KrishiMitra. Check your connection and try again."));
      }
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setPreviewUrl(null);
    setFile(null);
    setSizes(null);
    setResult(null);
    setNote("");
  }

  const sevTone: Record<string, "green" | "yellow" | "red"> = { low: "green", medium: "yellow", high: "red" };

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Tag tone="green" dot className="mb-3">{t("Kimi K2.6 vision")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Diagnose your crop")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Upload a photo of an affected leaf or plant. The vision agent identifies the disease, its severity, and a natural-farming treatment - explained simply in your language.")}
        </p>
      </div>

      {/* dropzone */}
      <div className="card overflow-hidden !p-0">
        {!preview ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-3 px-6 py-16 transition-colors ${drag ? "bg-bone" : "hover:bg-bone/60"}`}
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-lg border border-line bg-bone text-field-600">
              <UploadSimple className="h-6 w-6" />
            </div>
            {compressing ? (
              <>
                <p className="text-sm font-medium text-ink">{t("Compressing photo…")}</p>
                <p className="font-mono text-xs text-faint">{t("so it uploads fast on mobile data")}</p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-ink">{t("Drop a crop photo here")}</p>
                <p className="font-mono text-xs text-faint">{t("or click to browse · JPG / PNG")}</p>
              </>
            )}
            <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
          </div>
        ) : (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preview} alt="crop" className="max-h-80 w-full object-cover" />
            <button onClick={reset} className="absolute right-3 top-3 flex h-8 w-8 items-center justify-center rounded-md bg-surface/90 text-charcoal shadow-subtle backdrop-blur hover:bg-surface">
              <X className="h-4 w-4" />
            </button>
            {sizes && !loading && (
              // Real numbers, not a fake progress bar - this is the upload the
              // farmer no longer has to pay for.
              <span className="absolute left-3 top-3 rounded-md bg-surface/90 px-2 py-1 font-mono text-[11px] text-muted shadow-subtle backdrop-blur">
                {kb(sizes.from)} → {kb(sizes.to)}
              </span>
            )}
            {loading && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-paper/80 backdrop-blur-sm">
                <CircleNotch className="h-9 w-9 animate-spin text-field-600" />
                <p className="text-sm text-charcoal">{t("Vision agent analysing…")}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {preview && !result && (
        <div className="space-y-3">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("Optional note (e.g. spots spreading fast on lower leaves)")}
            className="w-full rounded-md border border-line bg-surface px-4 py-3 text-sm text-ink placeholder:text-faint focus:border-faint/50 focus:outline-none"
          />
          <Button onClick={diagnose} disabled={loading || compressing} size="lg" className="w-full">
            {loading || compressing ? <CircleNotch className="h-5 w-5 animate-spin" /> : <Scan className="h-5 w-5" />}
            {compressing ? t("Compressing photo…") : t("Diagnose with AI")}
          </Button>
        </div>
      )}

      {/* result */}
      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
            <Card interactive={false}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    {result.category === "healthy" ? (
                      <CheckCircle className="h-5 w-5 text-field-600" weight="bold" />
                    ) : (
                      <Warning className="h-5 w-5 text-pale-yellowink" weight="bold" />
                    )}
                    <h2 className="display text-2xl text-ink">{result.issue ? t(result.issue) : t("Analysis")}</h2>
                  </div>
                  <p className="mt-1 font-mono text-xs text-muted">
                    {result.crop_guess ? `${t(result.crop_guess)} · ` : ""}{t(result.category)}
                  </p>
                </div>
                {typeof result.confidence === "number" && (
                  <div className="text-right">
                    <div className="display text-3xl text-ink">{Math.round(result.confidence * 100)}%</div>
                    <p className="overline">{t("confidence")}</p>
                  </div>
                )}
              </div>

              {result.severity && (
                <div className="mt-3">
                  <Tag tone={sevTone[result.severity] ?? "yellow"}>{t(result.severity)} {t("severity")}</Tag>
                </div>
              )}

              {result.visible_symptoms?.length > 0 && (
                <div className="mt-5">
                  <p className="overline mb-2">{t("Visible symptoms")}</p>
                  <ul className="space-y-1.5">
                    {result.visible_symptoms.map((s: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-charcoal">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-field-600" /> {t(s)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.image_quality && <p className="mt-4 font-mono text-xs text-faint">{t("image quality")}: {t(result.image_quality)}</p>}
            </Card>

            {result.natural_treatment && (
              <Card interactive={false}>
                <div className="mb-3 flex items-center gap-2">
                  <Plant className="h-4 w-4 text-field-600" />
                  <span className="text-sm font-medium text-ink">{t("Natural treatment")}</span>
                </div>
                <p className="text-[15px] font-medium text-ink">{t(result.natural_treatment.remedy)}</p>
                {result.natural_treatment.recipe && (
                  <div className="mt-3 rounded-lg border border-line bg-bone p-3">
                    <p className="overline mb-1">{t("Recipe")}</p>
                    <p className="text-sm text-charcoal">{t(result.natural_treatment.recipe)}</p>
                  </div>
                )}
                {result.natural_treatment.frequency && (
                  <p className="mt-2 text-sm text-muted">{t("Frequency")}: {t(result.natural_treatment.frequency)}</p>
                )}
              </Card>
            )}

            {result.explanation_local && (
              <Card interactive={false}>
                <div className="mb-2 flex items-center justify-between">
                  <span className="overline">{result.language?.native ?? t("For the farmer")}</span>
                  <button
                    onClick={() => {
                      const u = new SpeechSynthesisUtterance(result.explanation_local);
                      u.lang = result.language?.tts || `${getStoredLang() || "hi"}-IN`;
                      window.speechSynthesis.speak(u);
                    }}
                    className="flex h-8 w-8 items-center justify-center rounded-md bg-bone text-charcoal hover:bg-line"
                  >
                    <SpeakerHigh className="h-4 w-4" />
                  </button>
                </div>
                <p className="font-serif text-xl leading-relaxed text-ink">{result.explanation_local}</p>
              </Card>
            )}

            <Button onClick={reset} variant="outline" className="w-full">{t("Diagnose another photo")}</Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Past diagnoses - stored per farm (result only, no image). */}
      {history.length > 0 && (
        <div className="pt-1">
          <div className="mb-2 flex items-center gap-2 px-1 text-sm text-muted">
            <ClockCounterClockwise className="h-4 w-4" />
            {t("Past diagnoses")} ({history.length})
          </div>
          <div className="space-y-2">
            {history.map((h) => (
              <Card key={h.id} interactive={false} className="!p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">
                      {h.payload?.issue ? t(h.payload.issue) : t("Analysis")}
                    </p>
                    <p className="mt-0.5 font-mono text-[11px] text-muted">
                      {h.payload?.crop_guess ? `${t(h.payload.crop_guess)} · ` : ""}
                      {h.payload?.category ? t(h.payload.category) : ""}
                      {h.payload?.severity ? ` · ${t(h.payload.severity)}` : ""}
                    </p>
                  </div>
                  <span className="shrink-0 font-mono text-[11px] text-faint">
                    {new Date(h.created_at).toLocaleDateString()}
                  </span>
                </div>
                {(h.answer || h.answer_en) && (
                  <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-muted">
                    {h.answer || h.answer_en}
                  </p>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
