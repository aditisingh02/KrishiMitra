"use client";

import { isMuted, setMuted, onMutedChange } from "@/lib/voice";
import { SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n-runtime";

/** Global mute for the read-aloud voice. Persisted; syncs across instances.
 * `iconOnly` renders a compact square button (used in the mobile bottom nav). */
export function VoiceToggle({ className, iconOnly = false }: { className?: string; iconOnly?: boolean }) {
  const t = useT();
  const [muted, setM] = useState(false);

  useEffect(() => {
    setM(isMuted());
    return onMutedChange(() => setM(isMuted()));
  }, []);

  function toggle() {
    setMuted(!muted); // fires the sync event; effect updates local state
  }

  const Icon = muted ? SpeakerSlash : SpeakerHigh;

  if (iconOnly) {
    return (
      <button
        onClick={toggle}
        title={muted ? t("Voice off - tap to unmute") : t("Voice on - tap to mute")}
        aria-label={muted ? t("Unmute voice") : t("Mute voice")}
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-lg transition-colors",
          muted ? "text-faint" : "text-charcoal",
          className,
        )}
      >
        <Icon className="h-5 w-5" weight={muted ? "regular" : "bold"} />
      </button>
    );
  }

  return (
    <button
      onClick={toggle}
      title={muted ? t("Voice off - tap to unmute") : t("Voice on - tap to mute")}
      aria-label={muted ? t("Unmute voice") : t("Mute voice")}
      className={cn(
        "flex items-center gap-2 rounded-md border border-line px-3 py-2 text-sm transition-colors",
        muted ? "text-faint hover:text-charcoal" : "text-charcoal hover:bg-bone",
        className,
      )}
    >
      <Icon className="h-4 w-4" />
      <span className="truncate">{muted ? t("Voice off") : t("Voice on")}</span>
    </button>
  );
}
