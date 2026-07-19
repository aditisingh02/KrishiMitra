// Text-to-speech with a persisted global mute. The app reads answers aloud
// (consult + diagnose); the mute lets a farmer silence the automatic voice while
// still being able to tap "play" on demand (force).

const KEY = "km_tts_muted";
const EVENT = "km-tts-muted-changed";

export function isMuted(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(KEY) === "1";
}

export function setMuted(muted: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, muted ? "1" : "0");
  if (muted) stopSpeaking();
  window.dispatchEvent(new Event(EVENT)); // let toggles in other components sync
}

export function onMutedChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

function pickVoice(synth: SpeechSynthesis, locale: string): SpeechSynthesisVoice | null {
  const voices = synth.getVoices();
  if (!voices.length) return null;
  const base = locale.split("-")[0].toLowerCase();
  return (
    voices.find((v) => v.lang.toLowerCase() === locale.toLowerCase()) ||
    voices.find((v) => v.lang.toLowerCase().startsWith(base)) ||
    null
  );
}

/**
 * Speak `text` in `locale`. No-ops when muted unless `force` (an explicit tap on
 * a play button). Auto-read-aloud omits force, so it stays silent when muted.
 */
export function speak(text: string, locale: string, opts?: { force?: boolean }) {
  if (typeof window === "undefined") return;
  const synth = window.speechSynthesis;
  if (!synth || !text || !text.trim()) return;
  if (isMuted() && !opts?.force) return;

  synth.cancel();       // clear anything queued/stuck
  synth.resume();       // unstick a paused engine (Chrome quirk after cancel)

  const u = new SpeechSynthesisUtterance(text.trim());
  u.lang = locale;
  u.rate = 0.95;
  const v = pickVoice(synth, locale);
  if (v) u.voice = v;
  u.onerror = (e) => console.warn("[voice] speechSynthesis error:", e.error, "lang:", locale);

  // Speak synchronously so we stay inside the click's user-activation window.
  synth.speak(u);

  // If no voices were loaded yet, retry once when the engine reports them.
  if (!v && synth.getVoices().length === 0) {
    synth.addEventListener(
      "voiceschanged",
      () => {
        const late = pickVoice(synth, locale);
        if (late && !synth.speaking) {
          const u2 = new SpeechSynthesisUtterance(text.trim());
          u2.lang = locale;
          u2.rate = 0.95;
          u2.voice = late;
          synth.speak(u2);
        }
      },
      { once: true }
    );
  }
}
