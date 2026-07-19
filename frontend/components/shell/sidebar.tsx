"use client";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import {
  SquaresFour,
  Microphone,
  Scan,
  CalendarCheck,
  TrendUp,
  UserCircle,
  Plant,
} from "@phosphor-icons/react";
import { UserButton } from "@clerk/nextjs";
import { NotificationBell } from "@/components/shell/notifications";
import { AppLanguageSelect } from "@/components/shell/app-language-select";
import { VoiceToggle } from "@/components/shell/voice-toggle";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Farm, type Profile } from "@/lib/api";
import { useT } from "@/lib/i18n-runtime";

// Ordered by what a farmer reaches for day to day; Dashboard sits last because
// it's the overview you land on rather than something you navigate to.
// (It stays the post-sign-in destination - see sign-in/page.tsx and onboarding.)
const NAV = [
  { href: "/consult", label: "Consult", icon: Microphone },
  { href: "/diagnose", label: "Diagnose", icon: Scan },
  { href: "/planner", label: "Planner", icon: CalendarCheck },
  { href: "/market", label: "Market", icon: TrendUp },
  { href: "/profile", label: "Profile", icon: UserCircle },
  { href: "/dashboard", label: "Dashboard", icon: SquaresFour },
];

export function Sidebar() {
  const t = useT();
  const path = usePathname();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [farms, setFarms] = useState<Farm[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    api.profile().then((d) => {
      setProfile(d.profile);
      setFarms(d.farms);
      setActiveId(d.profile.active_farm_id ?? null);
    }).catch(() => {});
  }, []);

  const activeFarm = farms.find((f) => f.id === activeId) ?? null;

  async function switchFarm(id: string) {
    if (id === activeId) return;
    try {
      await api.setActiveFarm(id);
      // The app is scoped to the active farm - reload so every page follows.
      window.location.reload();
    } catch {
      /* leave the selection as-is on failure */
    }
  }

  return (
    <aside className="sticky top-0 z-40 hidden h-screen w-[240px] shrink-0 flex-col border-r border-line bg-paper px-4 py-7 lg:flex">
      <Link href="/" className="mb-10 flex items-center gap-2.5 px-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="KrishiMitra" className="h-8 w-8 rounded-md object-contain" />
        <div className="leading-tight">
          <p className="font-serif text-lg text-ink">KrishiMitra</p>
          <p className="overline">{t("Agronomy OS")}</p>
        </div>
      </Link>

      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map((item) => {
          const active = path === item.href;
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} className="relative">
              {active && (
                <motion.span
                  layoutId="nav-active"
                  className="absolute inset-0 rounded-md bg-bone"
                  transition={{ type: "spring", stiffness: 400, damping: 34 }}
                />
              )}
              <span
                className={cn(
                  "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active ? "text-ink" : "text-muted hover:text-charcoal"
                )}
              >
                <Icon className="h-[18px] w-[18px]" weight={active ? "bold" : "regular"} />
                {t(item.label)}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3">
        <AppLanguageSelect className="w-full justify-between" />
        <VoiceToggle className="w-full justify-center" />

        {/* Active farm + switcher. The farm name is the heading; the whole card
            is a picker when the farmer has more than one farm. */}
        <div className="rounded-lg border border-line bg-surface p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-ink">
              {activeFarm?.name ?? activeFarm?.location ?? t("Your farm")}
            </p>
            <Plant className="h-4 w-4 text-field-600" weight="fill" />
          </div>
          <p className="mt-0.5 text-xs text-muted">
            {activeFarm
              ? `${activeFarm.location} · ${activeFarm.farm_size_acres} ${t("acres")}`
              : t("Loading…")}
          </p>
          {farms.length > 1 && (
            <select
              value={activeId ?? ""}
              onChange={(e) => switchFarm(e.target.value)}
              className="mt-2.5 w-full rounded-md border border-line bg-bone px-2 py-1.5 text-xs text-charcoal focus:outline-none"
              aria-label={t("Switch farm")}
            >
              {farms.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name ?? f.location}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* The farmer, not "Account". */}
        <div className="flex items-center gap-2 px-1">
          <UserButton afterSignOutUrl="/" />
          <Link href="/profile" className="flex-1 truncate text-xs font-medium text-charcoal hover:text-ink">
            {profile?.name ?? t("Account")}
          </Link>
          <NotificationBell />
        </div>
      </div>
    </aside>
  );
}

/** Mobile bottom nav. */
export function MobileNav() {
  const path = usePathname();
  return (
    <nav className="fixed bottom-3 left-1/2 z-50 flex max-w-[calc(100vw-1.5rem)] -translate-x-1/2 items-center gap-0.5 rounded-xl border border-line bg-surface/90 px-1 py-1 shadow-lift backdrop-blur lg:hidden">
      {NAV.map((item) => {
        const active = path === item.href;
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
              active ? "bg-bone text-ink" : "text-faint"
            )}
          >
            <Icon className="h-[18px] w-[18px]" weight={active ? "bold" : "regular"} />
          </Link>
        );
      })}
      {/* voice mute + account (tap avatar → Manage account / Sign out) */}
      <span className="mx-0.5 h-6 w-px shrink-0 bg-line" />
      <VoiceToggle iconOnly />
      <div className="flex h-9 w-9 items-center justify-center">
        <UserButton afterSignOutUrl="/" />
      </div>
    </nav>
  );
}
