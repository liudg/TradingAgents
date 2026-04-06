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

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}
