"use client";
import { api, type Dashboard } from "@/lib/api";
import { Tag, Card, Button } from "@/components/ui/primitives";
import { AppLanguageSelect } from "@/components/shell/app-language-select";
import { Gauge } from "@/components/ui/gauge";
import { WeatherScene } from "@/components/ui/weather-scene";
import { useT } from "@/lib/i18n-runtime";
import { WhatsAppLink } from "@/components/shell/whatsapp-link";
import { motion } from "framer-motion";
import {
  CloudRain,
  TrendUp,
  ShieldWarning,
  CheckCircle,
  Info,
  Drop,
  Wind,
  Sun,
  Pulse,
  Warning,
  ArrowsClockwise,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

const alertIcon: Record<string, any> = {
  rain: CloudRain,
  shield: ShieldWarning,
  trending: TrendUp,
  check: CheckCircle,
};
// literal classes (Tailwind can't see runtime-built names)
const alertBox: Record<string, string> = {
  danger: "bg-pale-red text-pale-redink",
  warning: "bg-pale-yellow text-pale-yellowink",
  info: "bg-pale-blue text-pale-blueink",
  ok: "bg-pale-green text-pale-greenink",
};

export default function DashboardPage() {
  const t = useT();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load(refresh = false) {
    return api.dashboard(refresh).then(setData).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!data) return <DashboardSkeleton />;

  const { metrics, weather, market, alerts, risk, recent_activity, farm } = data;
  const today = weather.days?.[0];

  return (
    <div className="space-y-10">
      {/* header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <Tag tone="green" dot>{t("Autonomous monitoring")}</Tag>
            <span className="font-mono text-xs text-faint">{t("updated")} {timeAgo(data.generated_at, t)}</span>
          </div>
          <h1 className="display text-4xl text-ink">{t("Namaste")}, {farm.farmer.split(" ")[0]}.</h1>
          <p className="mt-1.5 text-[15px] text-muted">
            {farm.location} · {farm.farm_size_acres} {t("acres")} · {t(farm.farming_type)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AppLanguageSelect />
          <RunCheckButton onDone={() => load(true)} />
        </div>
      </motion.div>

      {/* hero metrics */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Card className="flex flex-col items-center justify-center gap-3 text-center lg:col-span-4" interactive={false}>
          <p className="overline">{t("Farm health score")}</p>
          <Gauge value={metrics.health_score} label={t("of 100")} />
          <p className="text-sm text-muted">
            {metrics.health_score >= 70
              ? t("Thriving - keep it up")
              : metrics.health_score >= 50
              ? t("Needs attention this week")
              : t("Action required")}
          </p>
        </Card>

        <div className="grid grid-cols-2 gap-5 lg:col-span-8">
          <StatCard icon={ShieldWarning} label={t("Disease risk")} value={t(risk?.level ?? metrics.risk_level)} sub={`${metrics.risk_score} / 100 ${t("index")}`} warn={metrics.risk_score >= 60} />
          <StatCard icon={CloudRain} label={t("Rain probability")} value={`${metrics.rain_probability}%`} sub={today?.condition ? t(today.condition) : "-"} warn={metrics.rain_probability >= 70} />
          <StatCard icon={TrendUp} label={t("Market trend")} value={metrics.market_trend} sub={`${market.items.length} ${t("crops tracked")}`} />
          <StatCard icon={Pulse} label={t("Actions today")} value={String(metrics.recommended_actions)} sub={t("recommended now")} warn={metrics.recommended_actions > 0} />
        </div>
      </div>

      {/* alerts */}
      <section>
        <Head label={t("Proactive alerts")} note={t("What the agronomist noticed without being asked")} />
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {alerts.map((a, i) => {
            const Icon = alertIcon[a.icon] ?? Info;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                className="card flex items-start gap-3 p-4"
              >
                <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${alertBox[a.level]}`}>
                  <Icon className="h-4 w-4" weight="bold" />
                </span>
                <p className="text-sm leading-relaxed text-charcoal">{a.text}</p>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* WhatsApp is the delivery channel for the alerts above - if it's not
          linked, those alerts silently never reach the farmer off-app. */}
      <WhatsAppLink />

      {/* weather + risk */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Card className="flex flex-col lg:col-span-7" interactive={false}>
          <Head label={t("5-day forecast")} note={weather.summary} inline />
          <div className="mt-4 h-44 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={weather.days} margin={{ top: 10, right: 4, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="rainGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1F6C9F" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#1F6C9F" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tickFormatter={(d) => new Date(d).toLocaleDateString("en", { weekday: "short" })}
                  tick={{ fill: "#9B9A97", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<WeatherTip />} cursor={{ stroke: "#EAEAEA" }} />
                <Area type="monotone" dataKey="rain_prob" stroke="#1F6C9F" strokeWidth={1.5} fill="url(#rainGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4 text-center">
            <MiniStat icon={Sun} label={t("High")} value={`${today?.temp_max_c ?? "-"}°`} />
            <MiniStat icon={Drop} label={t("Humidity")} value={`${today?.humidity ?? "-"}%`} />
            <MiniStat icon={Wind} label={t("Wind")} value={`${today?.wind_kmph ?? "-"} km/h`} />
          </div>
          <WeatherScene
            className="mt-4 min-h-[150px]"
            condition={today?.condition}
            tempMaxC={today?.temp_max_c}
            rainProb={today?.rain_prob ?? metrics.rain_probability}
          />
        </Card>

        <Card className="lg:col-span-5" interactive={false}>
          <Head label={t("Risk assessment")} note={t("Next 3–5 days")} inline />
          <div className="mt-4 flex items-center gap-5">
            <Gauge value={metrics.risk_score} size={104} stroke={7} label={t("risk")} />
            <div className="flex-1">
              <p className="text-sm font-medium capitalize text-ink">{risk?.primary_risk ?? t("Stable")}</p>
              <p className="mt-1 text-sm leading-relaxed text-muted">{risk?.reason}</p>
            </div>
          </div>
          {risk?.mitigation && (
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-line bg-bone p-3">
              <Warning className="mt-0.5 h-4 w-4 shrink-0 text-field-600" weight="bold" />
              <p className="text-sm leading-relaxed text-charcoal">{risk.mitigation}</p>
            </div>
          )}
        </Card>
      </div>

      {/* market + activity */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <Card className="lg:col-span-7" interactive={false}>
          <Head label={t("Mandi prices")} note={market.items[0]?.mandi ?? t("Local mandi")} inline />
          <div className="mt-4 divide-y divide-line">
            {market.items.map((item: any) => (
              <div key={item.crop} className="flex items-center justify-between py-3 first:pt-0">
                <div>
                  <p className="text-sm font-medium capitalize text-ink">{item.crop}</p>
                  <p className="font-mono text-xs text-muted">₹{(item.price_per_quintal / 100).toFixed(2)}/kg</p>
                </div>
                <div className="text-right">
                  <Tag tone={item.trend === "rising" ? "green" : item.trend === "falling" ? "red" : "neutral"}>
                    {item.change_pct > 0 ? "+" : ""}{item.change_pct}%
                  </Tag>
                  <p className="mt-1 max-w-[200px] text-[11px] leading-snug text-faint">{item.advice}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="lg:col-span-5" interactive={false}>
          <Head label={t("Farm activity")} note={t("Recent memory")} inline />
          <ol className="relative mt-4 space-y-4 border-l border-line pl-4">
            {recent_activity.slice(0, 5).map((ev, i) => (
              <li key={i} className="relative">
                <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-field-600 ring-4 ring-paper" />
                <p className="text-sm text-charcoal">{t(ev.summary)}</p>
                <p className="overline mt-0.5">{t(ev.kind)} · {new Date(ev.created_at).toLocaleDateString()}</p>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}

/* ----------------------------- sub components ---------------------------- */
function timeAgo(iso: string | undefined, t: (s: string) => string) {
  if (!iso) return t("just now");
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return t("just now");
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins} ${t("min ago")}`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs} ${t("hr ago")}` : `${Math.round(hrs / 24)} ${t("days ago")}`;
}

function RunCheckButton({ onDone }: { onDone?: () => void }) {
  const t = useT();
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  async function run() {
    setRunning(true);
    setMsg(null);
    try {
      const r = await api.runMonitor();
      setMsg(r.alerts_created > 0 ? `${r.alerts_created} ${t("new alert(s)")}` : t("All clear"));
      onDone?.();
    } catch {
      setMsg(t("Check failed"));
    } finally {
      setRunning(false);
    }
  }
  return (
    <div className="flex items-center gap-2">
      {msg && <span className="text-xs text-muted">{msg}</span>}
      <Button variant="outline" size="sm" onClick={run} disabled={running}>
        <ArrowsClockwise className={`h-4 w-4 ${running ? "animate-spin" : ""}`} />
        {t("Run check now")}
      </Button>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, warn }: any) {
  return (
    <div className="card card-interactive p-5">
      <div className="mb-4 flex items-center justify-between">
        <span className="overline">{label}</span>
        <Icon className={`h-4 w-4 ${warn ? "text-pale-yellowink" : "text-field-600"}`} weight="regular" />
      </div>
      <p className="display text-2xl capitalize text-ink">{value}</p>
      <p className="mt-1 text-xs text-muted">{sub}</p>
    </div>
  );
}

function Head({ label, note, inline }: any) {
  return (
    <div className={inline ? "" : "mb-4"}>
      <h2 className="text-base font-medium text-ink">{label}</h2>
      {note && <p className="mt-0.5 text-sm text-muted">{note}</p>}
    </div>
  );
}

function MiniStat({ icon: Icon, label, value }: any) {
  return (
    <div>
      <Icon className="mx-auto h-4 w-4 text-faint" />
      <p className="mt-1.5 text-sm font-medium text-ink">{value}</p>
      <p className="overline">{label}</p>
    </div>
  );
}

function WeatherTip({ active, payload }: any) {
  const t = useT();
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lift">
      <p className="font-medium text-ink">{new Date(d.date).toLocaleDateString("en", { weekday: "long" })}</p>
      <p className="text-pale-blueink">{t("Rain")} {d.rain_prob}%</p>
      <p className="text-muted">{d.temp_min_c}°–{d.temp_max_c}° · {d.condition}</p>
    </div>
  );
}

function ErrorState({ error }: { error: string }) {
  const t = useT();
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <Warning className="h-9 w-9 text-pale-yellowink" weight="bold" />
      <h2 className="mt-4 display text-2xl text-ink">{t("Couldn't reach the farm")}</h2>
      <p className="mt-2 max-w-md text-sm text-muted">
        {t("Make sure the backend is running on port 8000.")}
        <br />
        <code className="font-mono text-xs text-charcoal">{error}</code>
      </p>
    </div>
  );
}

function DashboardSkeleton() {
  const t = useT();
  return (
    <div className="space-y-8">
      <div className="h-16 w-64 animate-pulse rounded-lg bg-bone" />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <div className="h-64 animate-pulse rounded-xl bg-bone lg:col-span-4" />
        <div className="grid grid-cols-2 gap-5 lg:col-span-8">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl bg-bone" />
          ))}
        </div>
      </div>
      <p className="flex items-center gap-2 font-mono text-xs text-muted">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-field-600" />
        {t("running risk, weather and market agents…")}
      </p>
    </div>
  );
}
