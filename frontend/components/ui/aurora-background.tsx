"use client";
import { cn } from "@/lib/utils";
import React from "react";

/**
 * Calm light ambient backdrop (replaces the old neon aurora). A single very
 * faint warm radial glow + a subtle dot grid. Quiet, editorial depth.
 */
export function AuroraBackground({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={cn("relative", className)}>
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-[520px] paper-glow" />
        <div className="absolute inset-0 dot-grid opacity-[0.5] [mask-image:radial-gradient(ellipse_at_top,black,transparent_60%)]" />
      </div>
      <div className="relative">{children}</div>
    </div>
  );
}
