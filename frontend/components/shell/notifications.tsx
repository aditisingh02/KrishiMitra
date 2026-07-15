"use client";
import { api, type Notification } from "@/lib/api";
import { Bell, X } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n-runtime";

const dot: Record<string, string> = {
  danger: "bg-pale-redink",
  warning: "bg-pale-yellowink",
  info: "bg-pale-blueink",
  ok: "bg-field-600",
};

export function NotificationBell() {
  const t = useT();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      const d = await api.notifications();
      setItems(d.items);
      setUnread(d.unread);
    } catch {
      /* not onboarded yet / no auth */
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) {
      await api.markRead().catch(() => {});
      setUnread(0);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={toggle}
        className="relative flex h-9 w-9 items-center justify-center rounded-md border border-line bg-surface text-charcoal hover:bg-bone"
        aria-label="Notifications"
      >
        <Bell className="h-[18px] w-[18px]" weight={unread ? "fill" : "regular"} />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-pale-redink px-1 text-[10px] font-medium text-white">
            {unread}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="absolute bottom-12 left-0 z-50 flex max-h-[min(70vh,28rem)] w-80 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-lift"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-line px-4 py-2.5">
              <span className="text-sm font-medium text-ink">{t("Alerts")}</span>
              <button onClick={() => setOpen(false)} className="text-faint hover:text-charcoal">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {items.length === 0 ? (
                <p className="px-4 py-8 text-center text-sm text-muted">{t("No alerts yet. The monitor checks your farm automatically.")}</p>
              ) : (
                items.map((n) => (
                  <div key={n.id} className="flex gap-2.5 border-b border-line px-4 py-3 last:border-0">
                    <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot[n.level] ?? "bg-faint"}`} />
                    <div>
                      <p className="text-sm leading-snug text-charcoal">{t(n.body)}</p>
                      <p className="overline mt-1">{new Date(n.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
