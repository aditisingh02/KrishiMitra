"use client";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import {
  SquaresFour,
  Microphone,
  Scan,
  CalendarBlank,
  CalendarCheck,
  TrendUp,
} from "@phosphor-icons/react";
import { UserButton } from "@clerk/nextjs";
import { NotificationBell } from "@/components/shell/notifications";
import { AppLanguageSelect } from "@/components/shell/app-language-select";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Farm } from "@/lib/api";
import { useT } from "@/lib/i18n-runtime";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: SquaresFour },
  { href: "/consult", label: "Consult", icon: Microphone },
  { href: "/diagnose", label: "Diagnose", icon: Scan },
  { href: "/calendar", label: "Calendar", icon: CalendarCheck },
  { href: "/planner", label: "Planner", icon: CalendarBlank },
  { href: "/market", label: "Market", icon: TrendUp },
];

export function Sidebar() {
  const t = useT();
  const path = usePathname();
  const [farm, setFarm] = useState<Farm | null>(null);

  useEffect(() => {
    api.farm().then((d) => setFarm(d.farm)).catch(() => {});
  }, []);

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
        <div className="rounded-lg border border-line bg-surface p-4">
          <p className="overline mb-1.5">{t("Active twin")}</p>
          <p className="text-sm font-medium text-ink">{farm?.farmer ?? t("Your farm")}</p>
          <p className="mt-0.5 text-xs text-muted">
            {farm
              ? `${farm.location} · ${farm.farm_size_acres} ${t("acres")} · ${t(farm.farming_type)}`
              : t("Loading…")}
          </p>
        </div>
        <div className="flex items-center gap-2 px-1">
          <UserButton afterSignOutUrl="/" />
          <span className="flex-1 text-xs text-muted">{t("Account")}</span>
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
    <nav className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-1 rounded-xl border border-line bg-surface/90 px-1.5 py-1.5 shadow-lift backdrop-blur lg:hidden">
      {NAV.map((item) => {
        const active = path === item.href;
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex h-10 w-10 items-center justify-center rounded-lg transition-colors",
              active ? "bg-bone text-ink" : "text-faint"
            )}
          >
            <Icon className="h-5 w-5" weight={active ? "bold" : "regular"} />
          </Link>
        );
      })}
      {/* account + logout (tap avatar → Manage account / Sign out) */}
      <span className="mx-0.5 h-6 w-px bg-line" />
      <div className="flex h-10 w-10 items-center justify-center">
        <UserButton afterSignOutUrl="/" />
      </div>
    </nav>
  );
}
