"use client";

import { api, type WhatsAppInfo } from "@/lib/api";
import { Button } from "@/components/ui/primitives";
import { WhatsappLogo } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

/**
 * Public "Chat on WhatsApp" button for unauthenticated pages (the landing page).
 *
 * Fetches the sandbox number + join code from /api/whatsapp/info and opens WhatsApp
 * with the "join <code>" opt-in message prefilled, so a farmer can start using the
 * assistant on WhatsApp without signing up. Renders nothing if the server hasn't
 * configured WhatsApp (join_link is null), so it degrades gracefully.
 */
export function WhatsAppCTA({
  size = "lg",
  label = "Chat on WhatsApp",
}: {
  size?: "sm" | "md" | "lg";
  label?: string;
}) {
  const [info, setInfo] = useState<WhatsAppInfo | null>(null);

  useEffect(() => {
    api.whatsappInfo().then(setInfo).catch(() => setInfo(null));
  }, []);

  if (!info?.join_link) return null;

  return (
    <a href={info.join_link} target="_blank" rel="noopener noreferrer">
      <Button size={size} variant="outline">
        <WhatsappLogo className="h-5 w-5" weight="fill" />
        {label}
      </Button>
    </a>
  );
}
