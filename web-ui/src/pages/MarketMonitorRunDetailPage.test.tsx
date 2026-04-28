import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type {
  HistoricalMarketMonitorRunDetail,
  MarketMonitorFactorBreakdown,
  MarketMonitorInputDataStatus,
} from "../api/types";
import { MarketMonitorRunDetailPage } from "./MarketMonitorRunDetailPage";

const mockUseMarketMonitorRun = vi.fn();
const mockUseMarketMonitorRunLogs = vi.fn();
const mockUseMarketMonitorPromptTraces = vi.fn();
const mockUseMarketMonitorArtifact = vi.fn();
const mockUseRecoverMarketMonitorRun = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorRun: (...args: unknown[]) => mockUseMarketMonitorRun(...args),
  useMarketMonitorRunLogs: (...args: unknown[]) => mockUseMarketMonitorRunLogs(...args),
  useMarketMonitorPromptTraces: (...args: unknown[]) => mockUseMarketMonitorPromptTraces(...args),
  useMarketMonitorArtifact: (...args: unknown[]) => mockUseMarketMonitorArtifact(...args),
  useRecoverMarketMonitorRun: (...args: unknown[]) => mockUseRecoverMarketMonitorRun(...args),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function installMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

const inputDataStatus: MarketMonitorInputDataStatus = {
  core_symbols_available: ["SPY", "QQQ", "IWM", "DIA", "^VIX"],
  core_symbols_missing: [],
  interval: "1d",
  includes_prepost: false,
  source: "yfinance",
  stale_symbols: [],
  partial_symbols: [],
};

const factor: MarketMonitorFactorBreakdown = {
  factor: "ETF proxy trend",
  raw_value: 1.8,
  raw_value_unit: "%",
  percentile: 0.64,
  polarity: "higher_is_better",
  score: 66,
  weight: 1,
  reason: "核心 ETF 趋势保持正向。",
  data_status: "available",
};

function baseReasoning() {
  return {
    reasoning_summary: "规则层分数为主，LLM 仅解释风险。",
    key_drivers: ["ETF proxy 广度改善"],
    risks: ["广度因子使用 ETF 代理池近似"],
    evidence: [],
    confidence: 0.82,
  };
}

function buildRunDetail(): HistoricalMarketMonitorRunDetail {
  const missingData = [
    {
      field: "event_fact_sheet",
      reason: "当前刷新周期未注入联网搜索事件事实",
      impact: "事件风险按空事实表处理",
      severity: "medium" as const,
    },
  ];
  const risks = ["广度因子使用 ETF 代理池近似"];

  return {
    run_id: "run-12345678",
    trigger_endpoint: "snapshot",
    as_of_date: "2026-04-11",
    days: null,
    status: "completed",
    generated_at: "2026-04-11T08:31:00Z",
    data_freshness: "daily_final",
    regime_label: "黄绿灯-Swing",
    degraded: true,
    recoverable: false,
    error_message: null,
    log_path: "results/market_monitor/2026-04-11/run-12345678/market_monitor.log",
    results_dir: "results/market_monitor/2026-04-11/run-12345678",
    request: {
      trigger_endpoint: "snapshot",
      as_of_date: "2026-04-11",
      days: null,
      force_refresh: true,
    },
    created_at: "2026-04-11T08:30:00Z",
    started_at: "2026-04-11T08:30:05Z",
    finished_at: "2026-04-11T08:31:00Z",
    snapshot: {
      scorecard_version: "2.3.1",
      prompt_version: "market-monitor-scorecard-2026-04-v2.3.1",
      model_name: "test-model",
      timestamp: "2026-04-11T08:31:00Z",
      as_of_date: "2026-04-11",
      data_mode: "daily",
      data_freshness: "daily_final",
      input_data_status: inputDataStatus,
      missing_data: missingData,
      risks,
      event_fact_sheet: [],
      run_id: "run-12345678",
      long_term_score: {
        ...baseReasoning(),
        deterministic_score: 67.5,
        score: 68.5,
        zone: "进攻区",
        delta_1d: 2.1,
        delta_5d: 8.2,
        slope_state: "缓慢改善",
        recommended_exposure: "60%-80%",
        factor_breakdown: [factor],
        score_adjustment: null,
      },
      short_term_score: {
        ...baseReasoning(),
        deterministic_score: 61.3,
        score: 61.3,
        zone: "可做区",
        delta_1d: 1.1,
        delta_5d: 4.6,
        slope_state: "缓慢改善",
        factor_breakdown: [factor],
        score_adjustment: null,
      },
      system_risk_score: {
        ...baseReasoning(),
        deterministic_score: 34.6,
        score: 34.6,
        zone: "正常区",
        delta_1d: -1.2,
        delta_5d: -3.5,
        slope_state: "风险缓慢回落",
        factor_breakdown: [{ ...factor, polarity: "higher_is_riskier", score: 35 }],
        score_adjustment: null,
        liquidity_stress_score: 31.2,
        risk_appetite_score: 38.0,
        event_triggers: [],
      },
      style_effectiveness: {
        ...baseReasoning(),
        tactic_layer: {
          trend_breakout: { score: 52, delta_5d: 0.8, valid: false, factor_breakdown: [factor] },
          dip_buy: { score: 66, delta_5d: 3.4, valid: true, factor_breakdown: [factor] },
          oversold_bounce: { score: 58, delta_5d: 2.1, valid: true, factor_breakdown: [factor] },
          top_tactic: "回调低吸",
          avoid_tactic: "趋势突破",
        },
        asset_layer: {
          large_cap_tech: { score: 61, delta_5d: 3.2, preferred: true, factor_breakdown: [factor] },
          small_cap_momentum: { score: 44, delta_5d: -1.2, preferred: false, factor_breakdown: [factor] },
          defensive: { score: 70, delta_5d: 2.8, preferred: true, factor_breakdown: [factor] },
          energy_cyclical: { score: 64, delta_5d: 1.8, preferred: true, factor_breakdown: [factor] },
          financials: { score: 49, delta_5d: 0.4, preferred: false, factor_breakdown: [factor] },
          preferred_assets: ["防御板块", "能源/周期"],
          avoid_assets: ["小盘高弹性"],
          factor_breakdown: [factor],
        },
      },
      execution_card: {
        ...baseReasoning(),
        regime_label: "黄绿灯-Swing",
        conflict_mode: "长线中性+短线活跃+风险低",
        total_exposure_range: "50%-70%",
        new_position_allowed: true,
        chase_breakout_allowed: true,
        dip_buy_allowed: true,
        overnight_allowed: true,
        leverage_allowed: false,
        single_position_cap: "12%",
        daily_risk_budget: "1.0R",
        tactic_preference: "回调低吸 > 趋势突破",
        preferred_assets: ["防御板块", "能源/周期"],
        avoid_assets: ["小盘高弹性"],
        signal_confirmation: {
          current_regime_observations: 1,
          risk_loosening_unlock_in_observations: 2,
          note: "当前 regime 为新近状态，继续观察 2 个交易日。",
        },
        event_risk_flag: {
          index_level: {
            active: false,
            events: [],
            source_event_ids: [],
            action_modifier: { note: "当前无指数级事件修正。" },
          },
          stock_level: {
            earnings_stocks: [],
            rule: "个股级事件只影响个股，不改变指数 regime。",
          },
        },
      },
      panic_reversal_score: {
        ...baseReasoning(),
        score: 41.2,
        zone: "观察期",
        state: "panic_watch",
        panic_extreme_score: 38,
        selling_exhaustion_score: 45,
        intraday_reversal_score: 39,
        factor_breakdown: [factor],
        action: "加入观察列表，等待确认。",
        system_risk_override: null,
        stop_loss: "ATR×1.0",
        profit_rule: "达 1R 兑现 50%，余仓移止损到成本线。",
        timeout_warning: false,
        refreshes_held: 0,
        early_entry_allowed: false,
        max_position_hint: "20%-35%",
      },
      fact_sheet: null,
      prompt_traces: [],
    },
    history: {
      as_of_date: "2026-04-11",
      points: [
        {
          trade_date: "2026-04-10",
          scorecard_version: "2.3.1",
          long_term_score: 64,
          short_term_score: 58,
          system_risk_score: 36,
          panic_reversal_score: 22,
          panic_state: "无信号",
          regime_label: "黄灯",
        },
      ],
      run_id: "run-12345678",
    },
    data_status: {
      timestamp: "2026-04-11T08:31:00Z",
      as_of_date: "2026-04-11",
      data_mode: "daily",
      data_freshness: "daily_final",
      input_data_status: inputDataStatus,
      missing_data: missingData,
      open_gaps: ["缺少交易所级 breadth 原始数据"],
      risks,
      event_fact_sheet: [],
      fact_sheet: null,
      run_id: "run-12345678",
    },
    fact_sheet: null,
    manifest: {
      run_id: "run-12345678",
      mode: "history",
      request: {
        trigger_endpoint: "snapshot",
        as_of_date: "2026-04-11",
        days: null,
        force_refresh: true,
      },
      status: "completed",
      created_at: "2026-04-11T08:30:00Z",
      started_at: "2026-04-11T08:30:05Z",
      finished_at: "2026-04-11T08:31:00Z",
      results_dir: "results/market_monitor/2026-04-11/run-12345678",
      log_path: "results/market_monitor/2026-04-11/run-12345678/market_monitor.log",
      error_message: null,
      recoverable: false,
      llm_config: null,
      stage_results: [],
      artifact_paths: {
        "history_snapshot_2026-04-10": "results/market_monitor/2026-04-11/run-12345678/artifacts/history_snapshot_2026-04-10.json",
        "history_fact_sheet_2026-04-10": "results/market_monitor/2026-04-11/run-12345678/artifacts/history_fact_sheet_2026-04-10.json",
      },
      prompt_trace_count: 0,
    },
    stage_results: [],
    prompt_traces: [],
  };
}

function mockCommonRunQueries(run: HistoricalMarketMonitorRunDetail) {
  mockUseMarketMonitorRun.mockReturnValue({
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    data: run,
    refetch: vi.fn(),
  });
  mockUseMarketMonitorPromptTraces.mockReturnValue({ isFetching: false, data: [], refetch: vi.fn() });
  mockUseMarketMonitorArtifact.mockReturnValue({ isFetching: false, data: null, refetch: vi.fn() });
  mockUseRecoverMarketMonitorRun.mockReturnValue({ isPending: false, mutate: vi.fn() });
}

function resetMocks() {
  installMatchMedia();
  mockUseMarketMonitorRun.mockReset();
  mockUseMarketMonitorRunLogs.mockReset();
  mockUseMarketMonitorPromptTraces.mockReset();
  mockUseMarketMonitorArtifact.mockReset();
  mockUseRecoverMarketMonitorRun.mockReset();
  mockNavigate.mockReset();
}

describe("MarketMonitorRunDetailPage", () => {
  it("renders run detail and logs", () => {
    resetMocks();
    mockCommonRunQueries(buildRunDetail());
    mockUseMarketMonitorRunLogs.mockReturnValue({
      isFetching: false,
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:30:05Z",
          level: "System",
          content: "Market monitor run run-12345678 started",
        },
      ],
      refetch: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={["/monitor/runs/run-12345678"]}>
        <Routes>
          <Route path="/monitor/runs/:runId" element={<MarketMonitorRunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("市场监控运行详情")).toBeInTheDocument();
    expect(screen.getByText("执行动作卡")).toBeInTheDocument();
    expect(screen.getByText("执行日志")).toBeInTheDocument();
    expect(screen.getByText("History 日级产物")).toBeInTheDocument();
    expect(screen.getByText("history_snapshot_2026-04-10")).toBeInTheDocument();
    expect(screen.getByText("Market monitor run run-12345678 started")).toBeInTheDocument();
    expect(screen.getByText("market-monitor-scorecard-2026-04-v2.3.1")).toBeInTheDocument();
    expect(screen.getByText("test-model")).toBeInTheDocument();
    expect(screen.getByText("缺少交易所级 breadth 原始数据")).toBeInTheDocument();
  });

  it("renders detail when history and data status are missing", () => {
    resetMocks();
    const run = buildRunDetail();
    run.history = null;
    run.data_status = null;
    mockCommonRunQueries(run);
    mockUseMarketMonitorRunLogs.mockReturnValue({ isFetching: false, data: [], refetch: vi.fn() });

    render(
      <MemoryRouter initialEntries={["/monitor/runs/run-12345678"]}>
        <Routes>
          <Route path="/monitor/runs/:runId" element={<MarketMonitorRunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("市场监控运行详情")).toBeInTheDocument();
    expect(screen.getByText("执行动作卡")).toBeInTheDocument();
    expect(screen.getByText("暂无日志")).toBeInTheDocument();
  });

  it("renders data status block for data-status-only runs", () => {
    resetMocks();
    const run = buildRunDetail();
    run.trigger_endpoint = "data_status";
    run.snapshot = null;
    run.history = null;
    mockCommonRunQueries(run);
    mockUseMarketMonitorRunLogs.mockReturnValue({ isFetching: false, data: [], refetch: vi.fn() });

    render(
      <MemoryRouter initialEntries={["/monitor/runs/run-12345678"]}>
        <Routes>
          <Route path="/monitor/runs/:runId" element={<MarketMonitorRunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("数据状态与缺失说明")).toBeInTheDocument();
    expect(screen.getByText("缺少交易所级 breadth 原始数据")).toBeInTheDocument();
    expect(screen.queryByText("执行动作卡")).not.toBeInTheDocument();
  });


  it("shows recover button and triggers recovery", () => {
    resetMocks();
    const run = buildRunDetail();
    run.recoverable = true;
    const mutate = vi.fn();
    mockCommonRunQueries(run);
    mockUseRecoverMarketMonitorRun.mockReturnValue({ isPending: false, mutate });
    mockUseMarketMonitorRunLogs.mockReturnValue({ isFetching: false, data: [], refetch: vi.fn() });

    render(
      <MemoryRouter initialEntries={["/monitor/runs/run-12345678"]}>
        <Routes>
          <Route path="/monitor/runs/:runId" element={<MarketMonitorRunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("恢复运行"));
    expect(mutate).toHaveBeenCalledWith("run-12345678");
  });

  it("goes back to history list when clicking return", () => {
    resetMocks();
    mockCommonRunQueries(buildRunDetail());
    mockUseMarketMonitorRunLogs.mockReturnValue({ isFetching: false, data: [], refetch: vi.fn() });

    render(
      <MemoryRouter initialEntries={["/monitor/runs/run-12345678"]}>
        <Routes>
          <Route path="/monitor/runs/:runId" element={<MarketMonitorRunDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("返回历史"));
    expect(mockNavigate).toHaveBeenCalledWith("/monitor/history");
  });
});
