import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { MarketMonitorRunDetailPage } from "./MarketMonitorRunDetailPage";

const mockUseMarketMonitorRun = vi.fn();
const mockUseMarketMonitorRunLogs = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorRun: (...args: unknown[]) => mockUseMarketMonitorRun(...args),
  useMarketMonitorRunLogs: (...args: unknown[]) => mockUseMarketMonitorRunLogs(...args),
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

function buildRunDetail() {
  return {
    run_id: "run-12345678",
    trigger_endpoint: "snapshot",
    as_of_date: "2026-04-11",
    days: null,
    status: "completed",
    generated_at: "2026-04-11T08:31:00Z",
    data_freshness: "delayed_15min",
    source_completeness: "medium",
    regime_label: "黄绿灯-Swing",
    degraded: true,
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
      timestamp: "2026-04-11T08:31:00Z",
      as_of_date: "2026-04-11",
      data_freshness: "delayed_15min",
      run_id: "run-12345678",
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
            action_modifier: { note: "未来一日可能出现宏观数据扰动，减少追高。" },
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
        panic_extreme_score: 38,
        selling_exhaustion_score: 45,
        reversal_confirmation_score: 39,
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
          action_modifier: { note: "未来一日可能出现宏观数据扰动，减少追高。" },
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
    },
    history: {
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
      run_id: "run-12345678",
    },
    data_status: {
      timestamp: "2026-04-11T08:31:00Z",
      as_of_date: "2026-04-11",
      source_coverage: {
        completeness: "medium",
        available_sources: ["ETF/指数日线", "VIX 日线", "本地缓存"],
        missing_sources: ["交易所级 breadth"],
        degraded: true,
      },
      degraded_factors: ["广度因子使用 ETF 代理池近似"],
      notes: ["已按代理池与降级规则输出结果。"],
      open_gaps: ["缺少交易所级 breadth 原始数据"],
      run_id: "run-12345678",
    },
  };
}

describe("MarketMonitorRunDetailPage", () => {
  it("renders run detail and logs", () => {
    installMatchMedia();
    mockUseMarketMonitorRun.mockReset();
    mockUseMarketMonitorRunLogs.mockReset();
    mockNavigate.mockReset();

    mockUseMarketMonitorRun.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      data: buildRunDetail(),
      refetch: vi.fn(),
    });
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
    expect(screen.getByText("Market monitor run run-12345678 started")).toBeInTheDocument();
    expect(screen.getByText("缺少交易所级 breadth 原始数据")).toBeInTheDocument();
  });

  it("goes back to history list when clicking return", () => {
    installMatchMedia();
    mockUseMarketMonitorRun.mockReset();
    mockUseMarketMonitorRunLogs.mockReset();
    mockNavigate.mockReset();

    mockUseMarketMonitorRun.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      isFetching: false,
      data: buildRunDetail(),
      refetch: vi.fn(),
    });
    mockUseMarketMonitorRunLogs.mockReturnValue({
      isFetching: false,
      data: [],
      refetch: vi.fn(),
    });

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
