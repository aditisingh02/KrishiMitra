"use client";
/**
 * Runtime UI localization. Components call `t("English string")`; the provider
 * auto-collects unseen strings, batch-translates them via the backend /api/i18n
 * (LLM + server cache), and caches the result in localStorage per language so
 * subsequent loads are instant. English is a pass-through (no network).
 *
 * Strings render in English for a beat on first encounter in a new language,
 * then swap to the translation once it arrives — and are cached forever after.
 */
import { getStoredLang } from "@/lib/i18n";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Dict = Record<string, string>;
const Ctx = createContext<{ t: (s: string) => string; lang: string }>({
  t: (s) => s,
  lang: "en",
});

// bump the version when the translation prompt/cache changes so browsers refetch
const key = (lang: string) => `i18n.v2:${lang}`;

function loadDict(lang: string): Dict {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(key(lang)) || "{}");
  } catch {
    return {};
  }
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState("en");
  const [dict, setDict] = useState<Dict>({});
  // strings seen this render that aren't translated yet; flushed in an effect
  const missing = useRef<Set<string>>(new Set());
  const [tick, setTick] = useState(0); // bumped to schedule a flush after render

  useEffect(() => {
    const apply = (l: string) => {
      setLang(l);
      setDict(l === "en" ? {} : loadDict(l));
    };
    apply(getStoredLang());
    const onLang = (e: Event) => apply((e as CustomEvent).detail || getStoredLang());
    window.addEventListener("krishi-lang", onLang);
    return () => window.removeEventListener("krishi-lang", onLang);
  }, []);

  // After render, translate any strings that were missing. Runs every commit but
  // exits immediately once nothing is missing (setDict clears the backlog), so no loop.
  useEffect(() => {
    if (lang === "en") return;
    const batch = Array.from(missing.current);
    if (!batch.length) return;
    missing.current.clear();
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/i18n`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lang, strings: batch }),
        });
        const data = await res.json();
        if (cancelled) return;
        const next = { ...loadDict(lang), ...(data.translations || {}) };
        localStorage.setItem(key(lang), JSON.stringify(next));
        setDict(next);
      } catch {
        /* keep English; a later render will re-register and retry */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [lang, dict, tick]);

  const t = useCallback(
    (s: string) => {
      if (!s || lang === "en") return s;
      if (dict[s] !== undefined) return dict[s];
      if (!missing.current.has(s)) {
        missing.current.add(s);
        // defer a state bump so the flush effect runs (never setState during render)
        queueMicrotask(() => setTick((n) => n + 1));
      }
      return s;
    },
    [dict, lang]
  );

  const value = useMemo(() => ({ t, lang }), [t, lang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useT() {
  return useContext(Ctx).t;
}

export function useLang() {
  return useContext(Ctx).lang;
}
