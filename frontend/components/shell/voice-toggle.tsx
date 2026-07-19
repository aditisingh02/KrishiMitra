"use client";

import { isMuted, setMuted, onMutedChange } from "@/lib/voice";
import { SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n-runtime";

/** Global mute for the read-aloud voice. Persisted; syncs across instances. */
export function VoiceToggle({ className }: { className?: string }) {
  const t = useT();
  const [muted, setM] = useState(false);

  useEffect(() => {
    setM(isMuted());
    return onMutedChange(() => setM(isMuted()));
  }, []);

  function toggle() {
    setMuted(!muted); // fires the sync event; effect updates local state
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
      {muted ? <SpeakerSlash className="h-4 w-4" /> : <SpeakerHigh className="h-4 w-4" />}
      <span className="truncate">{muted ? t("Voice off") : t("Voice on")}</span>
    </button>
  );
}
