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

export interface MarketMonitorEvidenceRef {
  source_type: string;
  source_label: string;
  snippet?: string | null;
  timestamp?: string | null;
  confidence?: number | null;
  metadata?: Record<string, unknown>;
}

export interface MarketMonitorMissingDataItem {
  field: string;
  reason: string;
  impact?: string | null;
  severity: "low" | "medium" | "high" | "critical";
}

export interface MarketMonitorInputDataStatus {
  core_symbols_available: string[];
  core_symbols_missing: string[];
  interval: string;
  includes_prepost: boolean;
  source: string;
  stale_symbols: string[];
  partial_symbols: string[];
}

export interface MarketMonitorFactorBreakdown {
  factor: string;
  raw_value?: number | string | boolean | null;
  raw_value_unit?: string | null;
  percentile?: number | null;
  polarity: "higher_is_better" | "higher_is_riskier" | "middle_is_better" | "lower_is_better";
  score: number;
  weight: number;
  reason: string;
  data_status: "available" | "missing" | "proxy_used" | "search_only";
}

export interface MarketMonitorScoreAdjustment {
  value: number;
  direction: string;
  reason: string;
  source_event_ids: string[];
  confidence: number;
  expires_at?: string | null;
}

export interface MarketMonitorEventFact {
  event_id: string;
  event: string;
  scope: "index_level" | "stock_level" | "sector_level" | "cross_asset" | "unknown";
  time_window: string;
  severity: "low" | "medium" | "high" | "critical";
  source_type: string;
  source_name: string;
  source_url?: string | null;
  source_summary: string;
  observed_at: string;
  confidence: number;
  expires_at: string;
}

export interface MarketMonitorEventTrigger {
  trigger_type: string;
  event: string;
  severity: "low" | "medium" | "high" | "critical";
  score_impact: string;
  confidence: number;
  expires_at?: string | null;
  source_event_ids: string[];
}

export interface MarketMonitorReasoningFields {
  reasoning_summary?: string | null;
  key_drivers: string[];
  risks: string[];
  evidence: MarketMonitorEvidenceRef[];
  confidence: number;
}

export interface MarketMonitorScoreCard extends MarketMonitorReasoningFields {
  deterministic_score: number;
  score: number;
  zone: string;
  delta_1d: number;
  delta_5d: number;
  slope_state: string;
  recommended_exposure?: string | null;
  factor_breakdown: MarketMonitorFactorBreakdown[];
  score_adjustment?: MarketMonitorScoreAdjustment | null;
}

export interface MarketMonitorSystemRiskCard extends MarketMonitorScoreCard {
  liquidity_stress_score: number;
  risk_appetite_score: number;
  event_triggers: MarketMonitorEventTrigger[];
}

export interface MarketMonitorLayerMetric {
  score: number;
  delta_5d: number;
  valid?: boolean | null;
  preferred?: boolean | null;
  factor_breakdown: MarketMonitorFactorBreakdown[];
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
    factor_breakdown: MarketMonitorFactorBreakdown[];
  };
}

export interface MarketMonitorActionModifier {
  new_position_allowed?: boolean | null;
  overnight_allowed?: boolean | null;
  single_position_cap_multiplier?: number | null;
  note?: string | null;
}

export interface MarketMonitorEventRiskFlag {
  index_level: {
    active: boolean;
    events: string[];
    source_event_ids: string[];
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
    current_regime_observations: number;
    risk_loosening_unlock_in_observations: number;
    note: string;
  };
  event_risk_flag: MarketMonitorEventRiskFlag;
}

export interface MarketMonitorPanicCard extends MarketMonitorReasoningFields {
  score: number;
  zone: string;
  state: string;
  panic_extreme_score: number;
  selling_exhaustion_score: number;
  intraday_reversal_score: number;
  factor_breakdown: MarketMonitorFactorBreakdown[];
  action: string;
  system_risk_override?: string | null;
  stop_loss: string;
  profit_rule: string;
  timeout_warning: boolean;
  refreshes_held: number;
  early_entry_allowed: boolean;
  max_position_hint: string;
}

export interface MarketMonitorFactSheet {
  as_of_date: string;
  generated_at: string;
  local_facts: Record<string, unknown>;
  derived_metrics: Record<string, unknown>;
  event_fact_sheet: MarketMonitorEventFact[];
  open_gaps: string[];
  evidence: MarketMonitorEvidenceRef[];
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

export interface MarketMonitorRunLlmConfig {
  provider?: string | null;
  model?: string | null;
  reasoning_effort?: string | null;
}

export interface MarketMonitorRunManifest {
  run_id: string;
  mode: "snapshot" | "history" | "data_status";
  request: MarketMonitorRunRequest;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  results_dir: string;
  log_path: string;
  error_message?: string | null;
  recoverable: boolean;
  llm_config?: MarketMonitorRunLlmConfig | null;
  stage_results: MarketMonitorStageResult[];
  artifact_paths: Record<string, string>;
  prompt_trace_count: number;
}

export interface MarketMonitorSnapshotResponse {
  scorecard_version: string;
  prompt_version: string;
  model_name?: string | null;
  timestamp: string;
  as_of_date: string;
  data_mode: "daily" | "intraday_delayed" | "intraday_realtime";
  data_freshness: string;
  input_data_status: MarketMonitorInputDataStatus;
  missing_data: MarketMonitorMissingDataItem[];
  risks: string[];
  event_fact_sheet: MarketMonitorEventFact[];
  long_term_score: MarketMonitorScoreCard;
  short_term_score: MarketMonitorScoreCard;
  system_risk_score: MarketMonitorSystemRiskCard;
  style_effectiveness: MarketMonitorStyleEffectiveness;
  execution_card: MarketMonitorExecutionCard;
  panic_reversal_score: MarketMonitorPanicCard;
  fact_sheet?: MarketMonitorFactSheet | null;
  prompt_traces: MarketMonitorPromptTrace[];
  run_id?: string | null;
}

export interface MarketMonitorHistoryPoint {
  trade_date: string;
  scorecard_version: string;
  long_term_score: number;
  short_term_score: number;
  system_risk_score: number;
  panic_reversal_score: number;
  panic_state: string;
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
  data_mode: "daily" | "intraday_delayed" | "intraday_realtime";
  data_freshness: string;
  input_data_status: MarketMonitorInputDataStatus;
  missing_data: MarketMonitorMissingDataItem[];
  open_gaps: string[];
  risks: string[];
  event_fact_sheet: MarketMonitorEventFact[];
  fact_sheet?: MarketMonitorFactSheet | null;
  run_id?: string | null;
}

export interface MarketMonitorRunRequest {
  trigger_endpoint: "snapshot" | "history" | "data_status";
  as_of_date?: string | null;
  days?: number | null;
  force_refresh: boolean;
  mode?: "snapshot" | "history" | "data_status" | null;
  llm_config?: MarketMonitorRunLlmConfig | null;
}

export interface HistoricalMarketMonitorRunSummary {
  run_id: string;
  trigger_endpoint: "snapshot" | "history" | "data_status";
  as_of_date: string;
  days?: number | null;
  status: JobStatus;
  generated_at: string;
  data_freshness?: string | null;
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
