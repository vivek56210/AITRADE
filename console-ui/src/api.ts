import type {
  Dashboard,
  JobDetail,
  JobSummary,
  JournalEntry,
  LiveOverview,
  LogEvent,
  SessionSummary,
  SessionView,
  SettingsResponse,
  SetupsResponse,
  Signal,
  Status,
  SystemInfo,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

const qs = (params: Record<string, string | number | undefined | null>) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

export const api = {
  status: () => request<Status>("/api/status"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  session: (date?: string) => request<SessionView | null>(`/api/session${qs({ date })}`),
  sessions: () => request<SessionSummary[]>("/api/sessions"),
  setups: () => request<SetupsResponse>("/api/setups"),
  toggleSetup: (id: string, enabled: boolean) => post<SetupsResponse>(`/api/setups/${id}`, { enabled }),
  signals: (date?: string) => request<Signal[]>(`/api/signals${qs({ date })}`),
  journal: (key: string, status: JournalEntry["status"], note: string) =>
    post<JournalEntry>("/api/signals/journal", { key, status, note }),
  events: (since: number, level?: string) => request<LogEvent[]>(`/api/events${qs({ since, level, limit: 500 })}`),
  control: (action: "start" | "pause" | "resume" | "stop" | "reset") => post<Status>(`/api/control/${action}`),
  step: (count: number) => post<Status>("/api/control/step", { count }),
  speed: (bars_per_second: number) => post<Status>("/api/control/speed", { bars_per_second }),
  jobs: () => request<JobSummary[]>("/api/jobs"),
  job: (id: string) => request<JobDetail>(`/api/jobs/${id}`),
  runBacktest: () => post<JobSummary>("/api/jobs/backtest"),
  cancelJob: (id: string) => post<JobSummary>(`/api/jobs/${id}/cancel`),
  settings: () => request<SettingsResponse>("/api/settings"),
  saveSettings: (data: Record<string, unknown>) =>
    request<SettingsResponse>("/api/settings", { method: "PUT", body: JSON.stringify(data) }),
  restoreDefaults: () => post<SettingsResponse>("/api/settings/defaults"),
  system: () => request<SystemInfo>("/api/system"),
  live: () => request<LiveOverview>("/api/live"),
  liveSnapshot: (symbol: string, date?: string) =>
    request<SessionView | null>(`/api/live/snapshot${qs({ symbol, date })}`),
};
