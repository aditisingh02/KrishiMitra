"use client";

import { api, ApiError } from "@/lib/api";
import { Flask, UploadSimple, CircleNotch, CheckCircle, X } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { downscaleImage } from "@/lib/image";
import { useT } from "@/lib/i18n-runtime";

/** Soil-detail fields (everything except the `type`, which has its own dropdown). */
function details(soil: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = {};
  for (const [k, v] of Object.entries(soil || {})) {
    if (k !== "type" && v != null && v !== "null") out[k] = v;
  }
  return out;
}

/**
 * Soil Health Card reader for the add-farm and edit-farm flows.
 *
 * Vision-reads a card (server-side, no farm write) and reports the values via
 * `onExtracted`; the parent merges them into the farm's `soil` on save - so pH,
 * N-P-K and organic carbon inform every future recommendation. Seed `initial`
 * with the farm's existing soil to show/keep current details when editing.
 */
export function SoilCardUpload({
  initial = {},
  onExtracted,
}: {
  initial?: Record<string, any>;
  onExtracted: (soil: Record<string, any>) => void;
}) {
  const t = useT();
  const [values, setValues] = useState<Record<string, any>>(details(initial));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const shown = details(values);
  const hasValues = Object.keys(shown).length > 0;

  async function onFile(f: File) {
    if (!f.type.startsWith("image/")) return;
    setLoading(true);
    setError(null);
    try {
      const small = (await downscaleImage(f)).file;
      const { soil, extracted } = await api.readSoilCard(small);
      if (!soil || Object.keys(soil).length === 0) {
        setError(
          extracted?._parse_error || extracted?.readable === false
            ? t("Couldn't read this card clearly - try a sharper, well-lit photo.")
            : t("No soil values found on that card."),
        );
        return;
      }
      // New card values win. Report detail fields only (pH/N-P-K…); the Soil-type
      // dropdown stays the authoritative source for `type`.
      const merged = details({ ...values, ...soil });
      setValues(merged);
      onExtracted(merged);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 429
          ? t("Too many uploads. Please wait a moment.")
          : t("Couldn't read the card. Please try again."),
      );
    } finally {
      setLoading(false);
    }
  }

  function clear() {
    setValues({});
    onExtracted({});
  }

  const rows: [string, any][] = ([
    [t("pH"), shown.ph], [t("Organic carbon"), shown.organic_carbon],
    [t("Nitrogen"), shown.nitrogen], [t("Phosphorus"), shown.phosphorus],
    [t("Potassium"), shown.potassium], [t("EC"), shown.ec],
  ] as [string, any][]).filter(([, v]) => v != null && v !== "null");

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-charcoal">
        {t("Soil Health Card")} <span className="font-normal text-faint">({t("optional")})</span>
      </label>

      {hasValues ? (
        <div className="rounded-md border border-line bg-bone/50 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-sm text-pale-greenink">
              <CheckCircle className="h-4 w-4" weight="fill" /> {t("Soil details")}
            </span>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => inputRef.current?.click()} disabled={loading}
                className="flex items-center gap-1 text-xs text-muted hover:text-charcoal disabled:opacity-60">
                {loading ? <CircleNotch className="h-3.5 w-3.5 animate-spin" /> : <UploadSimple className="h-3.5 w-3.5" />}
                {loading ? t("Reading…") : t("Re-upload")}
              </button>
              <button type="button" onClick={clear} className="text-faint hover:text-pale-redink" aria-label={t("Clear")}>
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          {rows.length > 0 ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
              {rows.map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <dt className="text-muted">{k}</dt>
                  <dd className="font-medium capitalize text-ink">{String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-muted">{shown.notes ? String(shown.notes) : t("Saved to your farm.")}</p>
          )}
          {shown.notes && rows.length > 0 && <p className="mt-2 text-xs text-muted">{String(shown.notes)}</p>}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-line py-3 text-sm text-muted transition-colors hover:border-faint/50 hover:text-charcoal disabled:opacity-60"
        >
          {loading ? <CircleNotch className="h-4 w-4 animate-spin" /> : <UploadSimple className="h-4 w-4" />}
          {loading ? t("Reading card…") : t("Upload Soil Health Card")}
        </button>
      )}

      <input ref={inputRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
      {error && <p className="mt-1.5 text-xs text-pale-redink">{error}</p>}
      {!hasValues && (
        <p className="mt-1 text-xs text-faint">
          <Flask className="mr-1 inline h-3 w-3" />
          {t("We read pH, N-P-K and organic carbon into your farm so advice is grounded in your soil.")}
        </p>
      )}
    </div>
  );
}
