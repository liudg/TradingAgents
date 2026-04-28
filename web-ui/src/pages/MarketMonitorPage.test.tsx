import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type {
  MarketMonitorFactorBreakdown,
  MarketMonitorInputDataStatus,
  MarketMonitorSnapshotResponse,
} from "../api/types";
import { MarketMonitorPage } from "./MarketMonitorPage";

const mockUseMarketMonitorSnapshot = vi.fn();
const mockUseMarketMonitorHistory = vi.fn();
const mockUseMarketMonitorDataStatus = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorSnapshot: (...args: unknown[]) => mockUseMarketMonitorSnapshot(...args),
  useMarketMonitorHistory: (...args: unknown[]) => mockUseMarketMonitorHistory(...args),
  useMarketMonitorDataStatus: (...args: unknown[]) => mockUseMarketMonitorDataStatus(...args),
}));

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

function reasoning() {
  return {
    reasoning_summary: "规则层分数为主，LLM 仅解释风险。",
    key_drivers: ["ETF proxy 广度改善"],
    risks: ["广度因子使用 ETF 代理池近似"],
    evidence: [],
    confidence: 0.82,
  };
}

function buildSnapshot(): MarketMonitorSnapshotResponse {
  return {
    scorecard_version: "2.3.1",
    prompt_version: "market-monitor-scorecard-2026-04-v2.3.1",
    model_name: "test-model",
    timestamp: "2026-04-11T08:30:00Z",
    as_of_date: "2026-04-11",
    data_mode: "daily",
    data_freshness: "daily_final",
    input_data_status: inputDataStatus,
    missing_data: [
      {
        field: "event_fact_sheet",
        reason: "当前刷新周期未注入联网搜索事件事实",
        impact: "事件风险按空事实表处理",
        severity: "medium",
      },
    ],
    risks: ["广度因子使用 ETF 代理池近似"],
    event_fact_sheet: [],
    run_id: "run-12345678",
    long_term_score: {
      ...reasoning(),
      deterministic_score: 67.5,
      score: 68.5,
      zone: "进攻区",
      delta_1d: 2.1,
      delta_5d: 8.2,
      slope_state: "缓慢改善",
      recommended_exposure: "60%-80%",
      factor_breakdown: [factor],
      score_adjustment: {
        value: 1,
        direction: "up",
        reason: "统一事件事实表未显示额外压力。",
        source_event_ids: [],
        confidence: 0.7,
        expires_at: null,
      },
    },
    short_term_score: {
      ...reasoning(),
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
      ...reasoning(),
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
      ...reasoning(),
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
      ...reasoning(),
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
      ...reasoning(),
      score: 41.2,
      zone: "观察期",
      state: "panic_watch",
      panic_extreme_score: 38.0,
      selling_exhaustion_score: 45.0,
      intraday_reversal_score: 39.0,
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
  };
}

describe("MarketMonitorPage", () => {
  it("renders snapshot cards with V2.3.1 formal API", () => {
    installMatchMedia();
    mockUseMarketMonitorSnapshot.mockReset();
    mockUseMarketMonitorHistory.mockReset();
    mockUseMarketMonitorDataStatus.mockReset();

    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      data: buildSnapshot(),
      error: null,
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: {
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
      },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorDataStatus.mockImplementation(() => ({
      data: {
        timestamp: "2026-04-11T08:30:00Z",
        as_of_date: "2026-04-11",
        data_mode: "daily",
        data_freshness: "daily_final",
        input_data_status: inputDataStatus,
        missing_data: buildSnapshot().missing_data,
        open_gaps: ["缺少交易所级 breadth 原始数据"],
        risks: buildSnapshot().risks,
        event_fact_sheet: [],
      },
      refetch: vi.fn(),
    }));

    render(
      <MemoryRouter>
        <MarketMonitorPage />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("黄绿灯-Swing").length).toBeGreaterThan(0);
    expect(screen.getByText("执行动作卡")).toBeInTheDocument();
    expect(screen.getByText("市场手法与风格有效性卡")).toBeInTheDocument();
    expect(screen.getByText("统一事件事实表")).toBeInTheDocument();
    expect(screen.getByText("历史趋势回看")).toBeInTheDocument();
    expect(screen.getByText("新建运行")).toBeInTheDocument();
    expect(screen.getByText("查看本次运行详情")).toBeInTheDocument();
    expect(screen.getByText("查看历史记录")).toBeInTheDocument();
    expect(screen.getByText("Prompt market-monitor-scorecard-2026-04-v2.3.1")).toBeInTheDocument();
    expect(screen.getByText("Model test-model")).toBeInTheDocument();
    expect(screen.getAllByText("广度因子使用 ETF 代理池近似").length).toBeGreaterThan(0);
    expect(screen.getByText(/event_fact_sheet：当前刷新周期未注入联网搜索事件事实/)).toBeInTheDocument();
  });

  it("shows loading state before snapshot returns", () => {
    installMatchMedia();
    mockUseMarketMonitorSnapshot.mockReset();
    mockUseMarketMonitorHistory.mockReset();
    mockUseMarketMonitorDataStatus.mockReset();

    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorDataStatus.mockImplementation(() => ({
      data: undefined,
      refetch: vi.fn(),
    }));

    render(
      <MemoryRouter>
        <MarketMonitorPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("正在加载市场监控快照")).toBeInTheDocument();
  });

  it("refreshes with force refresh enabled after clicking refresh", async () => {
    installMatchMedia();
    mockUseMarketMonitorSnapshot.mockReset();
    mockUseMarketMonitorHistory.mockReset();
    mockUseMarketMonitorDataStatus.mockReset();

    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      data: buildSnapshot(),
      error: null,
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorDataStatus.mockImplementation(() => ({
      data: {
        timestamp: "2026-04-11T08:30:00Z",
        as_of_date: "2026-04-11",
        data_mode: "daily",
        data_freshness: "daily_final",
        input_data_status: inputDataStatus,
        missing_data: buildSnapshot().missing_data,
        open_gaps: [],
        risks: buildSnapshot().risks,
        event_fact_sheet: [],
      },
      refetch: vi.fn(),
    }));

    render(
      <MemoryRouter>
        <MarketMonitorPage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("刷新"));

    await waitFor(() => {
      expect(mockUseMarketMonitorSnapshot).toHaveBeenLastCalledWith(undefined, true, 1);
      expect(mockUseMarketMonitorHistory).toHaveBeenLastCalledWith(20, undefined, true, 1);
      expect(mockUseMarketMonitorDataStatus).toHaveBeenLastCalledWith(undefined, true, 1);
    });
  });

  it("issues a new forced refresh on every refresh click", async () => {
    installMatchMedia();
    mockUseMarketMonitorSnapshot.mockReset();
    mockUseMarketMonitorHistory.mockReset();
    mockUseMarketMonitorDataStatus.mockReset();

    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      data: buildSnapshot(),
      error: null,
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorDataStatus.mockImplementation(() => ({
      data: {
        timestamp: "2026-04-11T08:30:00Z",
        as_of_date: "2026-04-11",
        data_mode: "daily",
        data_freshness: "daily_final",
        input_data_status: inputDataStatus,
        missing_data: buildSnapshot().missing_data,
        open_gaps: [],
        risks: buildSnapshot().risks,
        event_fact_sheet: [],
      },
      refetch: vi.fn(),
    }));

    render(
      <MemoryRouter>
        <MarketMonitorPage />
      </MemoryRouter>,
    );
    const refreshButton = screen.getByText("刷新");

    fireEvent.click(refreshButton);
    await waitFor(() => {
      expect(mockUseMarketMonitorSnapshot).toHaveBeenLastCalledWith(undefined, true, 1);
    });

    fireEvent.click(refreshButton);
    await waitFor(() => {
      expect(mockUseMarketMonitorSnapshot).toHaveBeenLastCalledWith(undefined, true, 2);
      expect(mockUseMarketMonitorHistory).toHaveBeenLastCalledWith(20, undefined, true, 2);
      expect(mockUseMarketMonitorDataStatus).toHaveBeenLastCalledWith(undefined, true, 2);
    });
  });
});
