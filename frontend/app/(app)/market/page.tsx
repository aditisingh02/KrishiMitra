"use client";
import { api, type Dashboard } from "@/lib/api";
import { Tag, Card } from "@/components/ui/primitives";
import { motion } from "framer-motion";
import { TrendUp, TrendDown, Minus, CurrencyInr, Warning } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";
import { useT } from "@/lib/i18n-runtime";

export default function MarketPage() {
  const t = useT();
  const [data, setData] = useState<Dashboard | null>(null);

  useEffect(() => {
    api.dashboard().then(setData).catch(() => {});
  }, []);

  const items = data?.market.items ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <div>
        <Tag tone="green" dot className="mb-3">{t("Market intelligence")}</Tag>
        <h1 className="display text-4xl text-ink">{t("Mandi Prices & Trends")}</h1>
        <p className="mt-2 text-[15px] leading-relaxed text-muted">
          {t("Nearby market rates, seven-day movement, and an AI recommendation on when to sell.")}
        </p>
      </div>

      {!data ? (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-44 animate-pulse rounded-xl bg-bone" />)}
        </div>
      ) : data.market.error ? (
        <div className="card flex items-start gap-3 border-pale-red bg-pale-red p-5">
          <Warning className="mt-0.5 h-5 w-5 shrink-0 text-pale-redink" weight="bold" />
          <div>
            <p className="text-sm font-medium text-pale-redink">{t("Mandi data unavailable")}</p>
            <p className="mt-1 text-sm text-pale-redink/80">{data.market.error}</p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {items.map((item: any, i: number) => {
            const Trend = item.trend === "rising" ? TrendUp : item.trend === "falling" ? TrendDown : Minus;
            const tone = item.trend === "rising" ? "green" : item.trend === "falling" ? "red" : "neutral";
            const stroke = item.trend === "falling" ? "#9F2F2D" : "#346538";
            return (
              <motion.div key={item.crop} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
                <Card>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-serif text-2xl capitalize text-ink">{item.crop}</h3>
                      <p className="font-mono text-xs text-muted">{item.mandi}</p>
                    </div>
                    <Tag tone={tone as any}>
                      <Trend className="h-3.5 w-3.5" weight="bold" />
                      {item.change_pct > 0 ? "+" : ""}{item.change_pct}%
                    </Tag>
                  </div>

                  <div className="mt-3 flex items-end gap-1">
                    <CurrencyInr className="mb-1 h-5 w-5 text-field-600" />
                    <span className="display text-4xl text-ink">{(item.price_per_quintal / 100).toFixed(2)}</span>
                    <span className="mb-1.5 text-xs text-muted">/{t("kg")}</span>
                  </div>

                  <div className="mt-3 h-14 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={item.history}>
                        <Tooltip
                          content={({ active, payload }: any) =>
                            active && payload?.length ? (
                              <div className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs text-ink shadow-lift">₹{payload[0].value}</div>
                            ) : null
                          }
                        />
                        <Line type="monotone" dataKey="price" stroke={stroke} strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <div className="mt-3 rounded-lg border border-line bg-bone p-3">
                    <p className="text-sm leading-relaxed text-charcoal">{item.advice}</p>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
