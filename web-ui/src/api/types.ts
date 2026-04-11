export type JobStatus = "pending" | "running" | "completed" | "failed";

export type AnalystType = "market" | "social" | "news" | "fundamentals";

export interface AnalysisJobRequest {
  ticker: string;
  trade_date: string;
  selected_analysts: AnalystType[];
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url?: string | null;
  google_thinking_level?: string | null;
  openai_reasoning_effort?: string | null;
  codex_reasoning_effort?: string | null;
  anthropic_effort?: string | null;
  output_language: string;
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
}

export interface AnalysisJobCreateResponse {
  job_id: string;
  status: JobStatus;
}

export interface DebateState {
  bull_history?: string | null;
  bear_history?: string | null;
  aggressive_history?: string | null;
  conservative_history?: string | null;
  neutral_history?: string | null;
  history?: string | null;
  current_response?: string | null;
  judge_decision?: string | null;
}

export interface AnalysisFinalState {
  company_of_interest?: string | null;
  trade_date?: string | null;
  market_report?: string | null;
  sentiment_report?: string | null;
  news_report?: string | null;
  fundamentals_report?: string | null;
  investment_plan?: string | null;
  trader_investment_plan?: string | null;
  final_trade_decision?: string | null;
  investment_debate_state?: DebateState | null;
  risk_debate_state?: DebateState | null;
}

export interface AnalysisJobResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  request: AnalysisJobRequest;
  final_state: AnalysisFinalState | null;
  decision: string | null;
  error_message: string | null;
  report_path: string | null;
  log_path?: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AnalysisJobLogEntry {
  line_no: number;
  timestamp: string | null;
  level: string;
  content: string;
}

export interface ModelOptionItem {
  label: string;
  value: string;
}

export interface MetadataOptionsResponse {
  analysts: AnalystType[];
  llm_providers: string[];
  models: Record<string, { quick?: ModelOptionItem[]; deep?: ModelOptionItem[] }>;
  default_config: AnalysisJobRequest & Record<string, unknown>;
}

export interface HistoricalReportItem {
  report_key: string;
  title: string;
  content?: string | null;
}

export interface HistoricalReportAgentGroup {
  agent_key: string;
  agent_name: string;
  reports: HistoricalReportItem[];
}

export interface HistoricalReportSummary {
  job_id: string;
  ticker: string;
  trade_date: string;
  generated_at: string;
  selected_analysts: AnalystType[];
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url?: string | null;
  google_thinking_level?: string | null;
  openai_reasoning_effort?: string | null;
  codex_reasoning_effort?: string | null;
  anthropic_effort?: string | null;
  output_language: string;
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
  report_path?: string | null;
}

export interface HistoricalReportDetail extends HistoricalReportSummary {
  agent_reports: HistoricalReportAgentGroup[];
}

export interface BacktestJobRequest {
  ticker: string;
  start_date: string;
  end_date: string;
  selected_analysts: AnalystType[];
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url?: string | null;
  google_thinking_level?: string | null;
  openai_reasoning_effort?: string | null;
  codex_reasoning_effort?: string | null;
  anthropic_effort?: string | null;
  output_language: string;
  max_debate_rounds: number;
  max_risk_discuss_rounds: number;
  holding_period: number;
  reflection_enabled: boolean;
  writeback_enabled: boolean;
}

export interface BacktestJobCreateResponse {
  job_id: string;
  status: JobStatus;
}

export interface BacktestSampleEvaluation {
  trade_date: string;
  signal: string;
  raw_decision: string;
  full_state_path?: string | null;
  report_path?: string | null;
  entry_date?: string | null;
  exit_date?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  holding_period: number;
  return_pct?: number | null;
  benchmark_return_pct?: number | null;
  excess_return_pct?: number | null;
  max_drawdown_pct?: number | null;
  outcome_label: string;
  evaluation_status: string;
  notes?: string | null;
  reflection_text?: string | null;
  reflection_payload?: Record<string, unknown> | null;
  memory_written: boolean;
}

export interface BacktestSummary {
  ticker: string;
  sample_count: number;
  evaluated_count: number;
  buy_count: number;
  hold_count: number;
  sell_count: number;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  benchmark_avg_return_pct?: number | null;
  excess_return_pct?: number | null;
  cumulative_return_pct?: number | null;
  max_drawdown_pct?: number | null;
  reflection_count: number;
  memory_write_count: number;
}

export interface BacktestMemoryEntry {
  memory_type: string;
  trade_date: string;
  signal: string;
  return_pct?: number | null;
  outcome_label: string;
  memory_query: string;
  recommendation: string;
}

export interface BacktestJobResponse {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  request: BacktestJobRequest;
  summary?: BacktestSummary | null;
  samples: BacktestSampleEvaluation[];
  memory_entries: BacktestMemoryEntry[];
  error_message?: string | null;
  log_path?: string | null;
  results_dir?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface HistoricalBacktestSummary {
  job_id: string;
  ticker: string;
  start_date: string;
  end_date: string;
  generated_at: string;
  holding_period: number;
  selected_analysts: AnalystType[];
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  output_language: string;
  sample_count: number;
  evaluated_count: number;
  win_rate?: number | null;
  avg_return_pct?: number | null;
  excess_return_pct?: number | null;
  reflection_count: number;
  memory_write_count: number;
}

export interface HistoricalBacktestDetail extends HistoricalBacktestSummary {
  summary?: BacktestSummary | null;
  samples: BacktestSampleEvaluation[];
  memory_entries: BacktestMemoryEntry[];
}

export interface MarketScoreCard {
  score: number;
  zone: string;
  delta_1d: number;
  delta_5d: number;
  slope_state: string;
  action: string;
}

export interface MarketStyleSignal {
  score: number;
  preferred?: boolean | null;
  valid?: boolean | null;
  delta_5d: number;
}

export interface MarketStyleEffectiveness {
  tactic_layer: {
    trend_breakout: MarketStyleSignal;
    dip_buy: MarketStyleSignal;
    oversold_bounce: MarketStyleSignal;
    top_tactic: string;
    avoid_tactic: string;
  };
  asset_layer: {
    large_cap_tech: MarketStyleSignal;
    small_cap_momentum: MarketStyleSignal;
    defensive: MarketStyleSignal;
    energy_cyclical: MarketStyleSignal;
    financials: MarketStyleSignal;
    preferred_assets: string[];
    avoid_assets: string[];
  };
}

export interface MarketEventRiskFlag {
  index_level: {
    active: boolean;
    type?: string | null;
    days_to_event?: number | null;
    action_modifier?: {
      new_position_allowed?: boolean | null;
      overnight_allowed?: boolean | null;
      single_position_cap_multiplier?: number | null;
      note?: string | null;
    } | null;
  };
  stock_level: {
    earnings_stocks: string[];
    rule?: string | null;
  };
}

export type MarketRegimeLabel =
  | "green"
  | "yellow"
  | "yellow_green_swing"
  | "orange"
  | "red";

export interface MarketExecutionCard {
  regime_label: MarketRegimeLabel;
  conflict_mode: string;
  total_exposure_range: string;
  new_position_allowed: boolean;
  chase_breakout_allowed: boolean;
  dip_buy_allowed: boolean;
  overnight_allowed: boolean;
  leverage_allowed: boolean;
  single_position_cap: string;
  daily_risk_budget: string;
  tactic_preference: string;
  preferred_assets: string[];
  avoid_assets: string[];
  signal_confirmation: {
    current_regime_days: number;
    downgrade_unlock_in_days: number;
    note: string;
  };
  event_risk_flag: MarketEventRiskFlag;
  summary: string;
}

export interface MarketPanicReversalCard {
  score: number;
  zone: string;
  state: "none" | "watch" | "confirmed";
  panic_extreme_score: number;
  selling_exhaustion_score: number;
  intraday_reversal_score: number;
  followthrough_confirmation_score: number;
  action: string;
  system_risk_override?: string | null;
  stop_loss: string;
  profit_rule: string;
  timeout_warning: boolean;
  days_held: number;
  early_entry_allowed: boolean;
}

export interface MarketSourceCoverage {
  status: "full" | "partial" | "degraded";
  data_freshness: string;
  degraded_factors: string[];
  notes: string[];
}

export interface MarketMonitorRuleSnapshot {
  ready: boolean;
  long_term_score?: MarketScoreCard | null;
  short_term_score?: MarketScoreCard | null;
  system_risk_score?: MarketScoreCard | null;
  style_effectiveness?: MarketStyleEffectiveness | null;
  panic_reversal_score?: MarketPanicReversalCard | null;
  base_regime_label?: MarketRegimeLabel | null;
  base_execution_card?: MarketExecutionCard | null;
  base_event_risk_flag: MarketEventRiskFlag;
  source_coverage: MarketSourceCoverage;
  missing_inputs: string[];
  degraded_factors: string[];
  key_indicators: Record<string, unknown>;
}

export interface MarketMonitorModelOverlay {
  status: "skipped" | "applied" | "error";
  regime_override?: MarketRegimeLabel | null;
  execution_adjustments?: {
    regime_label?: MarketRegimeLabel | null;
    conflict_mode?: string | null;
    new_position_allowed?: boolean | null;
    chase_breakout_allowed?: boolean | null;
    dip_buy_allowed?: boolean | null;
    overnight_allowed?: boolean | null;
    daily_risk_budget?: string | null;
    summary?: string | null;
  } | null;
  event_risk_override?: MarketEventRiskFlag | null;
  market_narrative: string;
  risk_narrative: string;
  panic_narrative: string;
  evidence_sources: string[];
  model_confidence?: number | null;
  notes: string[];
}

export interface MarketMonitorSnapshotResponse {
  timestamp: string;
  as_of_date: string;
  trace_id?: string | null;
  rule_snapshot: MarketMonitorRuleSnapshot;
  model_overlay: MarketMonitorModelOverlay;
  final_execution_card?: MarketExecutionCard | null;
}

export interface MarketMonitorTraceLogEntry {
  line_no: number;
  timestamp: string | null;
  level: string;
  content: string;
}

export interface MarketMonitorTraceSummary {
  trace_id: string;
  as_of_date: string;
  status: string;
  force_refresh: boolean;
  started_at: string;
  finished_at?: string | null;
  duration_ms?: number | null;
  rule_ready?: boolean | null;
  base_regime_label?: MarketRegimeLabel | null;
  final_regime_label?: MarketRegimeLabel | null;
  overlay_status?: "skipped" | "applied" | "error" | null;
}

export interface MarketMonitorHistoryPoint {
  trade_date: string;
  regime_label: MarketRegimeLabel;
  long_term_score: number;
  short_term_score: number;
  system_risk_score: number;
  panic_reversal_score: number;
}

export interface MarketMonitorHistoryResponse {
  as_of_date: string;
  points: MarketMonitorHistoryPoint[];
}

export interface MarketMonitorDataStatusResponse {
  as_of_date: string;
  source_coverage: MarketSourceCoverage;
  available_sources: string[];
  pending_sources: string[];
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}
