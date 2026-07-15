"use client";
import { cn } from "@/lib/utils";
import { LANGS } from "@/lib/i18n";
import { Translate, CaretDown } from "@phosphor-icons/react";

/** Dumb language dropdown (native select, styled). */
export function LanguageSelect({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (code: string) => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative inline-flex items-center gap-1.5 rounded-md border border-line bg-surface pl-2.5 pr-1.5 text-charcoal hover:border-faint/50",
        className
      )}
    >
      <Translate className="h-4 w-4 text-field-600" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Language"
        className="appearance-none bg-transparent py-1.5 pr-4 text-sm focus:outline-none cursor-pointer"
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.native}
          </option>
        ))}
      </select>
      <CaretDown className="pointer-events-none absolute right-1.5 h-3 w-3 text-faint" />
    </div>
  );
}
