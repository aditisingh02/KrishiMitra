"use client";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/**
 * Flat editorial card. (Kept the SpotlightCard name for call sites, but the
 * mouse-follow glow is gone - minimalist hairline border + ultra-subtle hover.)
 */
export function SpotlightCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
  color?: string;
}) {
  return (
    <div className={cn("card card-interactive", className)}>
      {children}
    </div>
  );
}
