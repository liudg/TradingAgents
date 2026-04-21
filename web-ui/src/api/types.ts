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

export interface MarketMonitorLayerMetric {
  score: number;
  delta_5d: number;
  valid?: boolean | null;
  preferred?: boolean | null;
}

export interface MarketMonitorEvidenceRef {
  source_type: string;
  source_label: string;
  snippet?: string | null;
  timestamp?: string | null;
  confidence?: "low" | "medium" | "high" | null;
  metadata?: Record<string, unknown>;
}

export interface MarketMonitorReasoningFields {
  reasoning_summary?: string | null;
  key_drivers: string[];
  risks: string[];
  evidence_refs: MarketMonitorEvidenceRef[];
  confidence?: "low" | "medium" | "high" | null;
}

export interface MarketMonitorScoreCard extends MarketMonitorReasoningFields {
  score: number;
  zone: string;
  delta_1d: number;
  delta_5d: number;
  slope_state: string;
  summary: string;
  action: string;
  recommended_exposure?: string | null;
}

export interface MarketMonitorSystemRiskCard extends MarketMonitorScoreCard {
  liquidity_stress_score: number;
  risk_appetite_score: number;
  pcr_percentile?: number | null;
  pcr_absolute?: number | null;
  pcr_panic_flag?: boolean | null;
}

export interface MarketMonitorStyleEffectiveness extends MarketMonitorReasoningFields {
  tactic_layer: {
    trend_breakout: MarketMonitorLayerMetric;
    dip_buy: MarketMonitorLayerMetric;
    oversold_bounce: MarketMonitorLayerMetric;
    top_tactic: string;
    avoid_tactic: string;
  };
  asset_layer: {
    large_cap_tech: MarketMonitorLayerMetric;
    small_cap_momentum: MarketMonitorLayerMetric;
    defensive: MarketMonitorLayerMetric;
    energy_cyclical: MarketMonitorLayerMetric;
    financials: MarketMonitorLayerMetric;
    preferred_assets: string[];
    avoid_assets: string[];
  };
}

export interface MarketMonitorActionModifier {
  new_position_allowed?: boolean | null;
  overnight_allowed?: boolean | null;
  single_position_cap_multiplier?: number | null;
  note?: string | null;
}

export interface MarketMonitorEventRiskFlag extends MarketMonitorReasoningFields {
  index_level: {
    active: boolean;
    type?: string | null;
    days_to_event?: number | null;
    action_modifier?: MarketMonitorActionModifier | null;
  };
  stock_level: {
    earnings_stocks: string[];
    rule?: string | null;
  };
}

export interface MarketMonitorExecutionCard extends MarketMonitorReasoningFields {
  regime_label: string;
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
  event_risk_flag: MarketMonitorEventRiskFlag;
  summary: string;
}

export interface MarketMonitorPanicCard extends MarketMonitorReasoningFields {
  score: number;
  zone: string;
  state: string;
  panic_extreme_score: number;
  selling_exhaustion_score: number;
  reversal_confirmation_score: number;
  action: string;
  system_risk_override?: string | null;
  stop_loss: string;
  profit_rule: string;
  timeout_warning: boolean;
  days_held: number;
  early_entry_allowed: boolean;
  max_position_hint: string;
}

export interface MarketMonitorSourceCoverage {
  completeness: "high" | "medium" | "low";
  available_sources: string[];
  missing_sources: string[];
  degraded: boolean;
}

export interface MarketMonitorFactSheet {
  as_of_date: string;
  generated_at: string;
  local_facts: Record<string, unknown>;
  derived_metrics: Record<string, unknown>;
  search_facts: Array<Record<string, unknown>>;
  open_gaps: string[];
  source_coverage?: MarketMonitorSourceCoverage | null;
  evidence_refs: MarketMonitorEvidenceRef[];
  notes: string[];
}

export interface MarketMonitorPromptTrace {
  stage: string;
  card_type?: string | null;
  model?: string | null;
  provider?: string | null;
  input_summary?: string | null;
  prompt_text?: string | null;
  raw_response?: string | null;
  parsed_ok: boolean;
  latency_ms?: number | null;
  token_usage: Record<string, number>;
  error?: string | null;
  created_at: string;
}

export interface MarketMonitorStageResult {
  stage_name: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  started_at?: string | null;
  finished_at?: string | null;
  artifact_path?: string | null;
  error?: string | null;
  metadata: Record<string, unknown>;
}

export interface MarketMonitorRunManifest {
  run_id: string;
  mode: "snapshot" | "history" | "data_status" | "debug_card";
  request: MarketMonitorRunRequest;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  results_dir: string;
  log_path: string;
  error_message?: string | null;
  recoverable: boolean;
  llm_config?: Record<string, unknown> | null;
  debug_options?: Record<string, unknown> | null;
  stage_results: MarketMonitorStageResult[];
  artifact_paths: Record<string, string>;
  prompt_trace_count: number;
}

export interface MarketMonitorSnapshotResponse {
  timestamp: string;
  as_of_date: string;
  data_freshness: string;
  long_term_score: MarketMonitorScoreCard;
  short_term_score: MarketMonitorScoreCard;
  system_risk_score: MarketMonitorSystemRiskCard;
  style_effectiveness: MarketMonitorStyleEffectiveness;
  execution_card: MarketMonitorExecutionCard;
  panic_reversal_score: MarketMonitorPanicCard;
  event_risk_flag: MarketMonitorEventRiskFlag;
  source_coverage: MarketMonitorSourceCoverage;
  degraded_factors: string[];
  notes: string[];
  fact_sheet?: MarketMonitorFactSheet | null;
  prompt_traces: MarketMonitorPromptTrace[];
  run_id?: string | null;
}

export interface MarketMonitorHistoryPoint {
  trade_date: string;
  long_term_score: number;
  short_term_score: number;
  system_risk_score: number;
  panic_score: number;
  regime_label: string;
}

export interface MarketMonitorHistoryResponse {
  as_of_date: string;
  points: MarketMonitorHistoryPoint[];
  run_id?: string | null;
}

export interface MarketMonitorDataStatusResponse {
  timestamp: string;
  as_of_date: string;
  source_coverage: MarketMonitorSourceCoverage;
  degraded_factors: string[];
  notes: string[];
  open_gaps: string[];
  fact_sheet?: MarketMonitorFactSheet | null;
  run_id?: string | null;
}

export interface MarketMonitorRunRequest {
  trigger_endpoint: "snapshot" | "history" | "data_status";
  as_of_date?: string | null;
  days?: number | null;
  force_refresh: boolean;
}

export interface HistoricalMarketMonitorRunSummary {
  run_id: string;
  trigger_endpoint: "snapshot" | "history" | "data_status";
  as_of_date: string;
  days?: number | null;
  status: JobStatus;
  generated_at: string;
  data_freshness?: string | null;
  source_completeness?: "high" | "medium" | "low" | null;
  regime_label?: string | null;
  degraded: boolean;
  recoverable?: boolean;
  error_message?: string | null;
  log_path?: string | null;
  results_dir?: string | null;
}

export interface HistoricalMarketMonitorRunDetail extends HistoricalMarketMonitorRunSummary {
  request: MarketMonitorRunRequest;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  snapshot?: MarketMonitorSnapshotResponse | null;
  history?: MarketMonitorHistoryResponse | null;
  data_status?: MarketMonitorDataStatusResponse | null;
  fact_sheet?: MarketMonitorFactSheet | null;
  manifest?: MarketMonitorRunManifest | null;
  stage_results: MarketMonitorStageResult[];
  prompt_traces: MarketMonitorPromptTrace[];
}

export type MarketMonitorArtifactPayload = Record<string, unknown>;

export interface MarketMonitorHistoryDailyArtifactItem {
  artifactName: string;
  tradeDate: string;
  artifactType: "snapshot" | "fact_sheet";
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
