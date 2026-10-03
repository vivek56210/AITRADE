export type RunState = "idle" | "loading" | "ready" | "running" | "paused" | "stopped" | "finished" | "error";

export interface Status {
  state: RunState;
  symbol: string;
  data_source: string;
  replay_speed: number;
  sessions_total: number;
  sessions_done: number;
  warmup_sessions: number;
  current_date: string | null;
  bar_index: number;
  bars_in_session: number;
  last_bar_ts: string | null;
  bars_processed: number;
  bars_per_second: number;
  uptime_s: number;
  worker_alive: boolean;
  heartbeat_age_s: number;
  pending_restart: boolean;
  last_error: string | null;
  signals_total: number;
  jobs_running: number;
  disabled_setups: string[];
}

export interface Target {
  price: number;
  label: string;
  size_pct: number;
}

export interface OptionLeg {
  side: "BUY" | "SELL";
  right: "CE" | "PE";
  strike: number;
  expiry: string;
  delta: number | null;
  premium: number | null;
}

export interface OptionPlan {
  structure: string;
  legs: OptionLeg[];
  expiry: string;
  net_premium: number | null;
  max_loss_per_lot: number | null;
  max_profit_per_lot: number | null;
  notes: string[];
}

export interface JournalEntry {
  status: "open" | "taken" | "ignored";
  note: string;
  updated?: string;
}

export interface Signal {
  key: string;
  setup_id: string;
  name: string;
  group: string;
  symbol: string;
  ts: string;
  direction: "long" | "short" | "neutral";
  entry: number;
  stop: number | null;
  stop_rule: string;
  targets: Target[];
  option_plan: OptionPlan;
  lots: number;
  risk_per_lot: number | null;
  risk_total: number | null;
  sizing_basis: string;
  exit_by: string | null;
  horizon: string;
  size_multiplier: number;
  est_costs: number | null;
  confirmations: Record<string, boolean | null>;
  notes: string[];
  validation_status: string;
  journal: JournalEntry;
}

export interface Levels {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  poc: number;
  vah: number;
  val: number;
  ib_high: number;
  ib_low: number;
  hvns: number[];
  lvns: number[];
  single_prints: [number, number][];
  poor_high: boolean;
  poor_low: boolean;
  day_type: string;
  shape: string;
  open_type: string | null;
}

export interface Today {
  open: number | null;
  high: number | null;
  low: number | null;
  last: number | null;
  ib_high: number | null;
  ib_low: number | null;
  ib_class: string | null;
  dpoc: number | null;
  vah: number | null;
  val: number | null;
  open_type: string | null;
  open_location: string | null;
  day_type: string | null;
  is_expiry: boolean;
}

export interface Plan {
  scenarios: string[];
  warnings: string[];
  avg_ib: number;
  nearest_expiry: string;
  is_expiry: boolean;
}

export interface Balance {
  sessions: string[];
  poc: number;
  vah: number;
  val: number;
  high: number;
  low: number;
  quiet: boolean;
}

export type BarRow = [string, number, number, number, number, number];

export interface SessionView {
  date: string;
  live: boolean;
  symbol: string;
  bars: BarRow[];
  today: Today;
  prior: Levels | null;
  prior_profile: [number, number][];
  profile: [number, number][];
  balance: Balance | null;
  plan: Plan;
  signals: Signal[];
  skips: { time: string | null; setup: string; reason: string }[];
}

export interface SessionSummary {
  date: string;
  live: boolean;
  day_type: string | null;
  open_type: string | null;
  ib_class: string | null;
  signals: number;
  skips: number;
}

export interface LogEvent {
  id: number;
  wall: string;
  market: string | null;
  level: "info" | "signal" | "skip" | "warn" | "error";
  kind: string;
  message: string;
  data: Record<string, unknown>;
}

export interface SetupStat {
  setup: string;
  trades: number;
  win_rate: number | null;
  avg_r: number | null;
  total_r: number;
  premium_trades: number;
  containment_rate: number | null;
}

export interface SetupInfo {
  id: string;
  group: string;
  group_name: string;
  name: string;
  context: string;
  trigger: string;
  strategy: string;
  stop: string;
  targets: string;
  enabled: boolean;
  fired: number;
  skipped: number;
  top_skip_reasons: { reason: string; count: number }[];
  today: "disabled" | "fired" | "skipped" | "watching" | "idle";
  today_reason: string | null;
  backtest: SetupStat | null;
}

export interface SetupsResponse {
  groups: Record<string, string>;
  setups: SetupInfo[];
  global_skips: { reason: string; count: number }[];
}

export interface JobSummary {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  done: number;
  total: number;
  progress: number;
  created: string;
  started: string | null;
  finished: string | null;
  duration_s: number | null;
  error: string | null;
}

export interface BacktestResult {
  symbol: string;
  data_source: string;
  first: string | null;
  last: string | null;
  sessions: number;
  signals: number;
  total_r: number;
  win_rate: number | null;
  avg_r: number | null;
  profit_factor: number | null;
  max_drawdown_r: number;
  premium_trades: number;
  premium_contained: number;
  monthly_r: Record<string, number>;
  stats: SetupStat[];
  equity: { n: number; date: string; cum_r: number }[];
  trades: {
    date: string;
    time: string;
    setup: string;
    direction: string;
    structure: string;
    entry: number;
    stop: number | null;
    r: number | null;
    contained: boolean | null;
    exit: string;
  }[];
  note: string;
}

export interface JobDetail extends JobSummary {
  result: BacktestResult | null;
}

export interface Dashboard {
  status: Status;
  session: (Pick<SessionView, "date" | "live" | "today" | "prior" | "plan"> & { signals: number; skips: number }) | null;
  signals_by_setup: Record<string, number>;
  signals_by_group: Record<string, number>;
  journal: Record<string, number>;
  recent_signals: Signal[];
  recent_events: LogEvent[];
  backtest: (JobSummary & { total_r: number; win_rate: number | null; signals: number; sessions: number; equity: BacktestResult["equity"] }) | null;
}

export type FieldKind = "number" | "integer" | "boolean" | "time" | "text" | "pair" | "list" | "select" | "optional-number";

export interface SchemaField {
  name: string;
  kind: FieldKind;
  value: unknown;
  default: unknown;
  help: string;
  live: boolean;
  options?: string[];
}

export interface SchemaSection {
  key: string;
  title: string;
  fields: SchemaField[];
}

export interface SettingsResponse {
  settings: Record<string, unknown>;
  schema: SchemaSection[];
  pending_restart: boolean;
  settings_path: string | null;
}

export interface SystemInfo {
  pid: number;
  python: string;
  platform: string;
  peak_rss_mb: number | null;
  cpu_s: number;
  threads: { name: string; alive: boolean; daemon: boolean }[];
  settings_path: string | null;
  journal_path: string | null;
  events_buffered: number;
  started: string;
}

export interface LiveJournalRow {
  key: string;
  date: string;
  symbol: string;
  setup: string;
  time: string;
  direction: "long" | "short" | "neutral";
  entry: number;
  stop: number | null;
  structure: string;
  lots: number;
  r: number | null;
  contained: boolean | null;
  exit: string | null;
}

export interface LiveSetupStats {
  key: string;
  signals: number;
  scored: number;
  wins: number;
  total_r: number;
  condors: number;
  contained: number;
}

export interface LiveHeartbeat {
  status: "running" | "finished";
  day: string;
  time: string;
  symbols: Record<string, { bars: number; last_bar: string | null; stale: boolean; feed_errors: number }>;
}

export interface LiveOverview {
  live_dir: string;
  heartbeat: LiveHeartbeat | null;
  runner_alive: boolean;
  days: string[];
  symbols: string[];
  summary: {
    signals: number;
    scored: number;
    wins: number;
    total_r: number;
    by_setup: LiveSetupStats[];
    by_day: { date: string; r: number }[];
  };
  journal: LiveJournalRow[];
}
