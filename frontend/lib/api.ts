// API client for the KrishiMitra backend. Requests go to /api/* which Next.js
// rewrites to the FastAPI server (see next.config.mjs).

export type Crop = { name: string; stage?: string; sown?: string; area_acres?: number };

export type Farm = {
  id: string;
  profile_id?: string;
  name?: string;
  farmer?: string; // denormalized from the profile
  language?: string; // denormalized from the profile
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

/** The farmer. Owns many farms; the AI runs on `active_farm_id`. */
export type Profile = {
  id: string;
  name: string;
  phone?: string | null;
  language?: string | null;
  default_location?: string | null;
  active_farm_id?: string | null;
};

export type Alert = { level: "ok" | "info" | "warning" | "danger"; icon: string; text: string };

/** A stored consult/diagnose turn (chat history). */
export type Interaction = {
  id: number;
  kind: "consult" | "diagnose";
  query: string;
  answer: string | null;
  answer_en: string | null;
  payload: Record<string, any>;
  blocked: boolean;
  created_at: string;
};

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
  recent_questions: Interaction[];
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
  /** Stored interaction id - used by "Add to planner". */
  interaction_id?: number | null;
};

export type TaskKind = "sowing" | "irrigation" | "nutrition" | "spray" | "scouting" | "harvest" | "other";

export type CalendarTask = {
  id: number;
  /** NULL for cycle-less tasks (added from a consult answer). */
  cycle_id: number | null;
  title: string;
  detail: string | null;
  kind: TaskKind;
  /** ISO date (YYYY-MM-DD); NULL when timing couldn't be dated. */
  due_on: string | null;
  done: boolean;
  notified_on: string | null;
  source?: string | null; // "calendar" | "consult"
};

export type CropCycle = {
  id: number;
  crop: string;
  sown_on: string;
  expected_harvest_on: string | null;
  status: "active" | "harvested" | "abandoned";
  tasks: CalendarTask[];
};

export type WhatsAppStatus = {
  /** Both sides ready: the farm has a number AND the server has Twilio creds. */
  linked: boolean;
  /** The farmer can fix this one (add a number). */
  has_phone: boolean;
  /** Only an operator can fix this one (server config). */
  provider_configured: boolean;
  phone_masked: string | null;
  /** Twilio sandbox opt-in code, when the server is running on the sandbox. */
  sandbox_join_code: string | null;
  /** Bare digits of the KrishiMitra WhatsApp number, or null if unconfigured. */
  number: string | null;
  /** One-tap wa.me link (prefills "join <code>" on the sandbox), or null. */
  join_link: string | null;
};

/** Public WhatsApp opt-in info for unauthenticated pages (landing). */
export type WhatsAppInfo = {
  configured: boolean;
  number: string | null;
  sandbox_join_code: string | null;
  join_link: string | null;
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

/** Onboarding step 1: the farmer. `location` seeds the first farm. */
export type ProfileInput = {
  name: string;
  location: string;
  phone?: string;
  language: string;
};

/** Partial profile update. `phone: ""` explicitly unlinks WhatsApp. */
export type ProfilePatch = {
  name?: string;
  phone?: string;
  language?: string;
  default_location?: string;
};

/** A farm (onboarding step 2 / "add farm"). Identity comes from the profile. */
export type FarmInput = {
  name: string;
  location: string;
  state?: string;
  farm_size_acres: number;
  farming_type: string;
  crops: { name: string; stage?: string; area_acres?: number }[];
  soil: Record<string, any>;
  inputs_on_hand: string[];
};

/** Partial farm update - farm-level fields only (no identity). */
export type FarmPatch = Partial<Omit<FarmInput, "state">>;

async function upload<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  const r = await fetch(path, { method: "POST", body: fd, headers: { ...(await authHeader()) } });
  if (!r.ok) await parseError(r, path);
  return r.json();
}

export const api = {
  // profile (the farmer)
  profileExists: () =>
    jget<{ profile: boolean; farms: number; active_farm_id: string | null }>("/api/profile/exists"),
  profile: () => jget<{ profile: Profile; farms: Farm[] }>("/api/profile"),
  createProfile: (p: ProfileInput) => jpost<{ profile: Profile }>("/api/profile", p),
  updateProfile: (patch: ProfilePatch) => jpost<{ profile: Profile }>("/api/profile", patch, "PATCH"),
  setActiveFarm: (farm_id: string) =>
    jpost<{ active_farm_id: string }>("/api/profile/active-farm", { farm_id }),

  // farms (a profile owns many)
  farms: () => jget<{ farms: Farm[]; active_farm_id: string | null }>("/api/farms"),
  createFarm: (farm: FarmInput) => jpost<{ farm: Farm }>("/api/farms", farm),
  updateFarm: (farmId: string, patch: FarmPatch) =>
    jpost<{ farm: Farm }>(`/api/farms/${farmId}`, patch, "PATCH"),
  deleteFarm: (farmId: string) => jpost<{ ok: boolean }>(`/api/farms/${farmId}`, {}, "DELETE"),

  dashboard: (refresh = false) =>
    jget<Dashboard>(`/api/dashboard${refresh ? "?refresh=1" : ""}`),
  /** The currently-active farm. */
  farm: () => jget<{ farm: Farm; recent_activity: any[] }>("/api/farm"),
  languages: () => jget<{ languages: Record<string, LangInfo> }>("/api/languages"),
  consult: (query: string) => jpost<ConsultResult>("/api/consult", { query }),
  consultHistory: (limit = 20) => jget<{ items: Interaction[] }>(`/api/consult/history?limit=${limit}`),
  diagnoseHistory: (limit = 20) => jget<{ items: Interaction[] }>(`/api/diagnose/history?limit=${limit}`),
  weeklyPlan: (focus = "") => jpost<{ plan: any }>("/api/weekly-plan", { focus }),
  croppingDesign: (land: string, location: string, goals: string) =>
    jpost<{ design: any }>("/api/cropping-design", { land, location, goals }),
  diagnose: (file: File, note = "") => upload<{ diagnosis: any }>("/api/diagnose", file, { note }),
  /** Extract soil values from a card photo (no farm write) - used while adding a farm. */
  readSoilCard: (file: File) =>
    upload<{ soil: Record<string, any>; extracted: any }>("/api/soil-card/read", file),
  calendar: () =>
    jget<{ cycles: CropCycle[]; general_tasks: CalendarTask[]; today: string }>("/api/calendar"),
  createCycle: (crop: string, sown_on: string) =>
    jpost<{ cycle: CropCycle }>("/api/calendar/cycles", { crop, sown_on }),
  deleteTask: (id: number) => jpost<{ ok: boolean }>(`/api/calendar/tasks/${id}`, {}, "DELETE"),
  addPlan: (interaction_id: number) =>
    jpost<{ tasks: CalendarTask[] }>("/api/planner/plan", { interaction_id }),
  setTaskDone: (id: number, done: boolean) =>
    jpost<{ ok: boolean }>(`/api/calendar/tasks/${id}`, { done }, "PATCH"),
  deleteCycle: (id: number) => jpost<{ ok: boolean }>(`/api/calendar/cycles/${id}`, {}, "DELETE"),
  markHarvested: (id: number) => jpost<{ ok: boolean }>(`/api/calendar/cycles/${id}/harvested`, {}),
  whatsappStatus: () => jget<WhatsAppStatus>("/api/whatsapp/status"),
  whatsappInfo: () => jget<WhatsAppInfo>("/api/whatsapp/info"),
  whatsappTest: () => jpost<{ sent: boolean; to: string }>("/api/whatsapp/test", {}),
  notifications: () => jget<{ items: Notification[]; unread: number }>("/api/notifications"),
  markRead: () => jpost<{ ok: boolean }>("/api/notifications/read", {}),
  runMonitor: () => jpost<{ alerts_created: number; unread: number }>("/api/monitor/run", {}),
};
