// API client for the KrishiMitra backend. Requests go to /api/* which Next.js
// rewrites to the FastAPI server (see next.config.mjs).

export type Crop = { name: string; stage?: string; sown?: string; area_acres?: number };

export type Farm = {
  id: string;
  farmer: string;
  language: string;
  location: string;
  phone?: string;
  lat?: number;
  lon?: number;
  farm_size_acres: number;
  farming_type: string;
  crops: Crop[];
  soil: Record<string, any>;
  recent_diseases: { disease: string; crop: string; date: string }[];
  inputs_on_hand?: string[];
};

export type Alert = { level: "ok" | "info" | "warning" | "danger"; icon: string; text: string };

export type Dashboard = {
  farm: Farm;
  metrics: {
    health_score: number;
    risk_level: string;
    risk_score: number;
    rain_probability: number;
    market_trend: string;
    recommended_actions: number;
  };
  risk: Record<string, any>;
  weather: { days: any[]; summary: string; source?: string; error?: string | null };
  market: { items: MarketItem[]; error?: string | null };
  alerts: Alert[];
  recent_activity: { kind: string; summary: string; created_at: string }[];
  generated_at?: string;
};

export type MarketItem = {
  crop: string;
  mandi: string;
  state?: string;
  arrival_date?: string;
  price_per_quintal: number;
  min_price?: number;
  max_price?: number;
  change_pct: number;
  trend: "rising" | "falling" | "stable";
  history: { date: string; price: number }[];
  advice: string;
};

export type LangInfo = { name: string; native: string; tts: string; script: string };

export type ConsultResult = {
  query: string;
  plan: { tasks: string[]; reasoning?: string; intent?: string };
  agents_run: string[];
  agent_outputs: Record<string, any>;
  result: {
    // Optional: the agents can fail to return usable JSON (`_parse_error`), or
    // the agronomic safety guardrail can block the answer (`_blocked`). Callers
    // must handle both rather than assume an answer is present.
    answer_en?: string;
    answer_local?: string;
    action_plan?: { step: number; action: string; when: string; why: string }[];
    confidence?: number;
    /** The model's reply could not be parsed as JSON, even after one retry. */
    _parse_error?: boolean;
    /** Advice was withheld by the agronomic safety guardrail. */
    _blocked?: boolean;
    _safety?: { safe: boolean; blocking: string[]; warnings: string[] };
  };
  language: LangInfo;
};

export type Notification = {
  id: number;
  level: "info" | "warning" | "danger" | "ok";
  title: string;
  body: string;
  read: number;
  created_at: string;
};

/** Pull the active Clerk session token (client-side) for the Authorization header. */
async function authHeader(): Promise<Record<string, string>> {
  const clerk = (typeof window !== "undefined" && (window as any).Clerk) || null;
  const token = clerk?.session ? await clerk.session.getToken() : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function parseError(r: Response, path: string): Promise<never> {
  let detail = `${path} → ${r.status}`;
  try {
    const j = await r.json();
    if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  throw new ApiError(r.status, detail);
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store", headers: { ...(await authHeader()) } });
  if (!r.ok) await parseError(r, path);
  return r.json();
}

async function jpost<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", ...(await authHeader()) },
    body: JSON.stringify(body),
  });
  if (!r.ok) await parseError(r, path);
  return r.json();
}

export type FarmInput = {
  farmer: string;
  location: string;
  phone?: string;
  farm_size_acres: number;
  farming_type: string;
  language: string;
  crops: { name: string; stage?: string; area_acres?: number }[];
  soil: Record<string, any>;
  inputs_on_hand: string[];
};

async function upload<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  const r = await fetch(path, { method: "POST", body: fd, headers: { ...(await authHeader()) } });
  if (!r.ok) await parseError(r, path);
  return r.json();
}

export const api = {
  farmExists: () => jget<{ exists: boolean }>("/api/farm/exists"),
  createFarm: (farm: FarmInput) => jpost<{ farm: Farm }>("/api/farm", farm),
  updateFarm: (patch: Record<string, any>) => jpost<{ farm: Farm }>("/api/farm", patch, "PATCH"),
  dashboard: (refresh = false) =>
    jget<Dashboard>(`/api/dashboard${refresh ? "?refresh=1" : ""}`),
  farm: () => jget<{ farm: Farm; recent_activity: any[] }>("/api/farm"),
  languages: () => jget<{ languages: Record<string, LangInfo> }>("/api/languages"),
  consult: (query: string) => jpost<ConsultResult>("/api/consult", { query }),
  weeklyPlan: (focus = "") => jpost<{ plan: any }>("/api/weekly-plan", { focus }),
  croppingDesign: (land: string, location: string, goals: string) =>
    jpost<{ design: any }>("/api/cropping-design", { land, location, goals }),
  diagnose: (file: File, note = "") => upload<{ diagnosis: any }>("/api/diagnose", file, { note }),
  soilCard: (file: File) => upload<{ soil: any; extracted: any }>("/api/soil-card", file),
  notifications: () => jget<{ items: Notification[]; unread: number }>("/api/notifications"),
  markRead: () => jpost<{ ok: boolean }>("/api/notifications/read", {}),
  runMonitor: () => jpost<{ alerts_created: number; unread: number }>("/api/monitor/run", {}),
};
