"use client";
import { api, type Dashboard } from "@/lib/api";
import { Tag, Card } from "@/components/ui/primitives";
import { motion } from "framer-motion";
import { TrendUp, TrendDown, Minus, CurrencyInr, Warning } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";
import { useT } from "@/lib/i18n-runtime";

/**
 * Cross-market price distribution for today. Each reporting mandi is a dot placed
 * on a low→high price axis, so clustering and outliers are visible at a glance.
 * The farmer's local mandi is enlarged + ringed; the best-priced mandi is marked.
 * A line chart would imply a sequence these discrete markets don't have.
 */
function SpreadStrip({ item, t }: { item: any; t: (s: string) => string }) {
  const lo: number = item.min_price ?? 0;
  const hi: number = item.max_price ?? lo;
  const span = Math.max(1, hi - lo);
  // Inset to 6–94% so dots at the extremes aren't clipped by the container edge.
  const pos = (p: number) => 6 + ((p - lo) / span) * 88;
  const markets: { market: string; price: number }[] = item.history ?? [];
  const [hover, setHover] = useState<{ market: string; price: number; left: number } | null>(null);

  return (
    <div className="relative h-full w-full">
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-line" />

      {hover && (
        <div
          className="pointer-events-none absolute bottom-[58%] z-30 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs text-ink shadow-lift"
          style={{ left: `${Math.min(88, Math.max(12, hover.left))}%` }}
        >
          ₹{(hover.price / 100).toFixed(2)}/{t("kg")} · {hover.market}
        </div>
      )}

      {markets.map((m, idx) => {
        const isLocal = m.market === item.mandi;
        const isBest = m.market === item.best_market;
        const cls = isLocal
          ? "z-20 h-3 w-3 bg-field-600 ring-2 ring-surface"
          : isBest
            ? "z-10 h-2.5 w-2.5 bg-field-700"
            : "h-2 w-2 bg-field-600/35";
        return (
          // A generous transparent hit area around each dot so even the small ones
          // are easy to hover; the visible dot scales up on hover.
          <span
            key={`${m.market}-${idx}`}
            onMouseEnter={() => setHover({ market: m.market, price: m.price, left: pos(m.price) })}
            onMouseLeave={() => setHover(null)}
            className="group absolute top-1/2 flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center"
            style={{ left: `${pos(m.price)}%` }}
          >
            <span className={`rounded-full transition-transform group-hover:scale-150 ${cls}`} />
          </span>
        );
      })}

      <span className="absolute bottom-0 left-0 font-mono text-[10px] text-faint">
        ₹{(lo / 100).toFixed(0)}
      </span>
      <span className="absolute bottom-0 right-0 font-mono text-[10px] text-faint">
        ₹{(hi / 100).toFixed(0)}
      </span>
    </div>
  );
}

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
          {t("Live mandi rates, the day-by-day price trend as it builds up, and where to sell for the best return.")}
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
            // Prefer the accumulated day-over-day trend once we have >=2 days stored;
            // until then fall back to today's cross-market spread.
            const hasTrend = Array.isArray(item.trend_history) && item.trend_history.length >= 2;
            const changePct = hasTrend ? item.trend_change_pct : item.change_pct;
            const dir = changePct > 1.5 ? "rising" : changePct < -1.5 ? "falling" : "stable";
            const Trend = dir === "rising" ? TrendUp : dir === "falling" ? TrendDown : Minus;
            const tone = dir === "rising" ? "green" : dir === "falling" ? "red" : "neutral";
            const stroke = dir === "falling" ? "#9F2F2D" : "#346538";
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
                      {changePct > 0 ? "+" : ""}{changePct}%
                    </Tag>
                  </div>

                  <div className="mt-3 flex items-end gap-1">
                    <CurrencyInr className="mb-1 h-5 w-5 text-field-600" />
                    <span className="display text-4xl text-ink">{(item.price_per_quintal / 100).toFixed(2)}</span>
                    <span className="mb-1.5 text-xs text-muted">/{t("kg")}</span>
                  </div>

                  {(hasTrend || item.markets_count > 1) && (
                    <p className="mt-1 font-mono text-xs text-muted">
                      {hasTrend
                        ? `${item.trend_days}-${t("day trend")} · ${t("today")} ₹${(item.min_price / 100).toFixed(2)}–₹${(item.max_price / 100).toFixed(2)}/${t("kg")}`
                        : `${t("Range")} ₹${(item.min_price / 100).toFixed(2)}–₹${(item.max_price / 100).toFixed(2)}/${t("kg")} · ${item.markets_count} ${t("mandis")}`}
                    </p>
                  )}

                  <div className="mt-3 h-14 w-full">
                    {hasTrend ? (
                      // Real day-over-day history: a line is the right tool for a time series.
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={item.trend_history} margin={{ top: 6, bottom: 6, left: 2, right: 2 }}>
                          <Tooltip
                            content={({ active, payload }: any) =>
                              active && payload?.length ? (
                                <div className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs text-ink shadow-lift">
                                  ₹{(payload[0].value / 100).toFixed(2)}/{t("kg")}
                                  {payload[0].payload?.date ? ` · ${payload[0].payload.date}` : ""}
                                </div>
                              ) : null
                            }
                          />
                          <Line
                            type="monotone"
                            dataKey="price"
                            stroke={stroke}
                            strokeWidth={1.5}
                            dot={{ r: 2, fill: stroke, strokeWidth: 0 }}
                            activeDot={{ r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      // Today's cross-market snapshot: discrete, unordered mandis, so show
                      // the price distribution as a dot strip - not a line (no sequence).
                      <SpreadStrip item={item} t={t} />
                    )}
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
