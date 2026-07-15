"use client";
import { api } from "@/lib/api";
import { setStoredLang } from "@/lib/i18n";
import { LanguageSelect } from "@/components/ui/language-select";
import { CircleNotch } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

/**
 * Self-contained language switch for the app. Reads the farm's current language,
 * and on change updates the farm (so the agents + voice respond in it) and
 * reloads so every page picks up the new language.
 */
export function AppLanguageSelect({ className }: { className?: string }) {
  const [lang, setLang] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.farm().then((d) => setLang(d.farm.language || "hi")).catch(() => setLang("hi"));
  }, []);

  async function change(code: string) {
    setSaving(true);
    setStoredLang(code);
    try {
      await api.updateFarm({ language: code });
      window.location.reload();
    } catch {
      setLang(code);
      setSaving(false);
    }
  }

  if (lang === null) return null;
  return (
    <div className="inline-flex items-center gap-1.5">
      <LanguageSelect value={lang} onChange={change} className={className} />
      {saving && <CircleNotch className="h-4 w-4 animate-spin text-faint" />}
    </div>
  );
}
