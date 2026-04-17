import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

function buildSnapshot() {
  return {
    timestamp: "2026-04-11T08:30:00Z",
    as_of_date: "2026-04-11",
    data_freshness: "delayed_15min",
    long_term_score: {
      score: 68.5,
      zone: "进攻区",
      delta_1d: 2.1,
      delta_5d: 8.2,
      slope_state: "缓慢改善",
      summary: "长线环境偏多。",
      action: "建议维持趋势仓。",
      recommended_exposure: "60%-80%",
    },
    short_term_score: {
      score: 61.3,
      zone: "可做区",
      delta_1d: 1.1,
      delta_5d: 4.6,
      slope_state: "缓慢改善",
      summary: "短线环境允许参与。",
      action: "优先低吸。",
    },
    system_risk_score: {
      score: 34.6,
      zone: "正常区",
      delta_1d: -1.2,
      delta_5d: -3.5,
      slope_state: "缓慢恶化",
      summary: "系统性风险可控。",
      action: "维持常规风控。",
      liquidity_stress_score: 31.2,
      risk_appetite_score: 38.0,
      pcr_percentile: null,
      pcr_absolute: null,
      pcr_panic_flag: null,
    },
    style_effectiveness: {
      tactic_layer: {
        trend_breakout: { score: 52, delta_5d: 0.8, valid: false },
        dip_buy: { score: 66, delta_5d: 3.4, valid: true },
        oversold_bounce: { score: 58, delta_5d: 2.1, valid: true },
        top_tactic: "回调低吸",
        avoid_tactic: "趋势突破",
      },
      asset_layer: {
        large_cap_tech: { score: 61, delta_5d: 3.2, preferred: true },
        small_cap_momentum: { score: 44, delta_5d: -1.2, preferred: false },
        defensive: { score: 70, delta_5d: 2.8, preferred: true },
        energy_cyclical: { score: 64, delta_5d: 1.8, preferred: true },
        financials: { score: 49, delta_5d: 0.4, preferred: false },
        preferred_assets: ["防御板块", "能源/周期"],
        avoid_assets: ["小盘高弹性"],
      },
    },
    execution_card: {
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
        current_regime_days: 1,
        downgrade_unlock_in_days: 2,
        note: "当前 regime 为新近状态，继续观察 2 个交易日。",
      },
      event_risk_flag: {
        index_level: {
          active: true,
          type: "宏观窗口",
          days_to_event: 1,
          action_modifier: {
            note: "未来一日可能出现宏观数据扰动，减少追高。",
          },
        },
        stock_level: {
          earnings_stocks: ["NVDA", "META"],
          rule: "财报股单票上限减半，禁追高，不影响指数 regime。",
        },
      },
      summary: "当前处于黄绿灯-Swing，总仓建议 50%-70%，优先 回调低吸。",
    },
    panic_reversal_score: {
      score: 41.2,
      zone: "观察期",
      state: "panic_watch",
      panic_extreme_score: 38.0,
      selling_exhaustion_score: 45.0,
      reversal_confirmation_score: 39.0,
      action: "加入观察列表，等待确认。",
      system_risk_override: null,
      stop_loss: "ATR×1.0",
      profit_rule: "达 1R 兑现 50%，余仓移止损到成本线。",
      timeout_warning: false,
      days_held: 0,
      early_entry_allowed: false,
      max_position_hint: "20%-35%",
    },
    event_risk_flag: {
      index_level: {
        active: true,
        type: "宏观窗口",
        days_to_event: 1,
        action_modifier: {
          note: "未来一日可能出现宏观数据扰动，减少追高。",
        },
      },
      stock_level: {
        earnings_stocks: ["NVDA", "META"],
        rule: "财报股单票上限减半，禁追高，不影响指数 regime。",
      },
    },
    source_coverage: {
      completeness: "medium",
      available_sources: ["ETF/指数日线", "VIX 日线", "本地缓存"],
      missing_sources: ["交易所级 breadth"],
      degraded: true,
    },
    degraded_factors: ["广度因子使用 ETF 代理池近似"],
    notes: ["已按代理池与降级规则输出结果。"],
  };
}

describe("MarketMonitorPage", () => {
  it("renders snapshot cards with new formal API", () => {
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
            long_term_score: 64,
            short_term_score: 58,
            system_risk_score: 36,
            panic_score: 22,
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
        source_coverage: buildSnapshot().source_coverage,
        degraded_factors: buildSnapshot().degraded_factors,
        notes: buildSnapshot().notes,
        open_gaps: ["缺少交易所级 breadth 原始数据"],
      },
      refetch: vi.fn(),
    }));

    render(<MarketMonitorPage />);

    expect(screen.getAllByText("黄绿灯-Swing").length).toBeGreaterThan(0);
    expect(screen.getByText("执行动作卡")).toBeInTheDocument();
    expect(screen.getByText("风格有效性卡")).toBeInTheDocument();
    expect(screen.getByText("历史趋势回看")).toBeInTheDocument();
    expect(screen.getAllByText("广度因子使用 ETF 代理池近似").length).toBeGreaterThan(0);
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

    render(<MarketMonitorPage />);

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
        source_coverage: buildSnapshot().source_coverage,
        degraded_factors: buildSnapshot().degraded_factors,
        notes: buildSnapshot().notes,
        open_gaps: [],
      },
      refetch: vi.fn(),
    }));

    render(<MarketMonitorPage />);

    fireEvent.click(screen.getByText("刷新"));

    await waitFor(() => {
      expect(mockUseMarketMonitorSnapshot).toHaveBeenLastCalledWith(undefined, true);
      expect(mockUseMarketMonitorHistory).toHaveBeenLastCalledWith(20, undefined, true);
      expect(mockUseMarketMonitorDataStatus).toHaveBeenLastCalledWith(undefined, true);
    });
  });
});
