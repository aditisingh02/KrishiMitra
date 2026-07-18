"use client";

import { api, ApiError, type WhatsAppStatus } from "@/lib/api";
import { Card, Button, Tag } from "@/components/ui/primitives";
import { WhatsappLogo, CheckCircle, Warning, PaperPlaneTilt, CircleNotch } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n-runtime";

/**
 * WhatsApp link status + a "Send test" button.
 *
 * WhatsApp is an inbound Q&A channel: once linked, the farmer can send a crop
 * photo (diagnose) or a question (consult) from their phone. No proactive alerts
 * are pushed. This card makes the link state visible and lets them confirm it.
 *
 * Two failure modes are shown separately because only one is the farmer's to fix:
 * no phone number (they can), or the server has no Twilio credentials (they
 * can't - telling them to "check your number" would be a wild goose chase).
 */
export function WhatsAppLink() {
  const t = useT();
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.whatsappStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  async function sendTest() {
    setSending(true);
    setError(null);
    setSent(false);
    try {
      await api.whatsappTest();
      setSent(true);
    } catch (e) {
      if (e instanceof ApiError) {
        // The server distinguishes "not linked" (400), "not configured" (503),
        // "undeliverable" (502) and "too many" (429) - surface its message.
        setError(e.status === 429 ? t("Too many test messages. Please wait a while.") : e.message);
      } else {
        setError(t("Couldn't send the test message. Check your connection."));
      }
    } finally {
      setSending(false);
    }
  }

  if (!status) return null; // not loaded, or no farm yet

  const canTest = status.linked && !sending;

  return (
    <Card interactive={false}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-line bg-bone text-field-600">
            <WhatsappLogo className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink">{t("Ask on WhatsApp")}</span>
              {status.linked ? (
                <Tag tone="green" dot>{t("Linked")}</Tag>
              ) : (
                <Tag tone="yellow" dot>{t("Not linked")}</Tag>
              )}
            </div>

            <p className="mt-1 text-sm text-muted">
              {status.linked ? (
                <>
                  {t("Send crop photos & questions from")}{" "}
                  <span className="font-mono text-charcoal">{status.phone_masked}</span>
                </>
              ) : !status.has_phone ? (
                t("Add your WhatsApp number in your profile to ask questions and diagnose crops on WhatsApp.")
              ) : (
                t("WhatsApp isn't set up on the server yet. Your number is saved - it'll work once it's enabled.")
              )}
            </p>

            {/* Sandbox numbers only receive messages after opting in - without this
                the test just fails with no explanation. */}
            {status.linked && status.sandbox_join_code && (
              <p className="mt-1.5 text-xs text-faint">
                {t("First time? Send")}{" "}
                <span className="font-mono text-charcoal">join {status.sandbox_join_code}</span>{" "}
                {t("from your WhatsApp to the KrishiMitra number.")}
              </p>
            )}

            {sent && (
              <p className="mt-2 flex items-center gap-1.5 text-sm text-pale-greenink">
                <CheckCircle className="h-4 w-4" weight="fill" />
                {t("Test message sent - check your WhatsApp.")}
              </p>
            )}
            {error && (
              <p className="mt-2 flex items-start gap-1.5 text-sm text-pale-redink">
                <Warning className="mt-0.5 h-4 w-4 shrink-0" />
                {error}
              </p>
            )}
          </div>
        </div>

        {status.linked && (
          <Button onClick={sendTest} disabled={!canTest} variant="outline" size="sm" className="shrink-0">
            {sending ? <CircleNotch className="h-4 w-4 animate-spin" /> : <PaperPlaneTilt className="h-4 w-4" />}
            {t("Send test")}
          </Button>
        )}
      </div>
    </Card>
  );
}
