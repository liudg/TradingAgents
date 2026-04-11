import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MarketMonitorPage } from "./MarketMonitorPage";

const mockUseMarketMonitorSnapshot = vi.fn();
const mockUseMarketMonitorHistory = vi.fn();
const mockUseMarketMonitorTraceLogs = vi.fn();
const mockUseMarketMonitorTraces = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorSnapshot: () => mockUseMarketMonitorSnapshot(),
  useMarketMonitorHistory: () => mockUseMarketMonitorHistory(),
  useMarketMonitorTraceLogs: () => mockUseMarketMonitorTraceLogs(),
  useMarketMonitorTraces: () => mockUseMarketMonitorTraces(),
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

function buildLoadedSnapshot(overrides?: Record<string, unknown>) {
  return {
    timestamp: "2026-04-11T08:30:00Z",
    as_of_date: "2026-04-11",
    trace_id: "trace-1",
    rule_snapshot: {
      ready: true,
      long_term_score: {
        score: 72.1,
        zone: "进攻区",
        delta_1d: 1.2,
        delta_5d: 2.8,
        slope_state: "缓慢改善",
        action: "中期趋势稳健，可逐步提高风险暴露。",
      },
      short_term_score: {
        score: 61.5,
        zone: "可做区",
        delta_1d: 0.4,
        delta_5d: 1.1,
        slope_state: "钝化震荡",
        action: "短线条件允许操作，适合低吸和确认后突破。",
      },
      system_risk_score: {
        score: 55.4,
        zone: "压力区",
        delta_1d: -0.5,
        delta_5d: 0.3,
        slope_state: "钝化震荡",
        action: "系统风险抬升，应收紧风险预算并减少追价。",
      },
      panic_reversal_score: null,
      base_regime_label: "green",
      base_execution_card: {
        regime_label: "green",
        conflict_mode: "trend_and_tape_aligned",
        total_exposure_range: "40-60%",
        new_position_allowed: true,
        chase_breakout_allowed: true,
        dip_buy_allowed: true,
        overnight_allowed: true,
        leverage_allowed: false,
        single_position_cap: "10%",
        daily_risk_budget: "1R",
        tactic_preference: "trend",
        preferred_assets: ["QQQ"],
        avoid_assets: ["UVXY"],
        signal_confirmation: {
          current_regime_days: 3,
          downgrade_unlock_in_days: 0,
          note: "状态已确认",
        },
        event_risk_flag: {
          index_level: { active: false, type: null, note: "" },
          stock_level: { active: false, rule: "标准规则", tickers: [] },
        },
        summary: "当前适合顺着主趋势参与。",
      },
      base_event_risk_flag: {
        index_level: { active: false, type: null, note: "" },
        stock_level: { active: false, rule: "标准规则", tickers: [] },
      },
      source_coverage: {
        status: "full",
        data_freshness: "fresh",
        degraded_factors: ["intraday_panic_confirmation_missing"],
        notes: ["实时 Yahoo Finance 日线数据已完成更新。"],
      },
      missing_inputs: [],
      degraded_factors: ["intraday_panic_confirmation_missing"],
      key_indicators: {},
    },
    model_overlay: {
      status: "applied",
      regime_override: "green",
      execution_adjustments: null,
      event_risk_override: null,
      market_narrative: "市场广度正在改善。",
      risk_narrative: "整体风险仍处于可控范围。",
      panic_narrative: "当前没有恐慌反转信号。",
      evidence_sources: ["snapshot"],
      model_confidence: 0.82,
      notes: [],
    },
    final_execution_card: {
      regime_label: "green",
      conflict_mode: "trend_and_tape_aligned",
      total_exposure_range: "50-70%",
      new_position_allowed: true,
      chase_breakout_allowed: true,
      dip_buy_allowed: true,
      overnight_allowed: true,
      leverage_allowed: false,
      single_position_cap: "10%",
      daily_risk_budget: "1R",
      tactic_preference: "trend",
      preferred_assets: ["QQQ"],
      avoid_assets: ["UVXY"],
      signal_confirmation: {
        current_regime_days: 3,
        downgrade_unlock_in_days: 0,
        note: "状态已确认",
      },
      event_risk_flag: {
        index_level: { active: false, type: null, note: "" },
        stock_level: { active: false, rule: "标准规则", tickers: [] },
      },
      summary: "继续沿主趋势执行。",
    },
    ...overrides,
  };
}

describe("MarketMonitorPage", () => {
  it("renders successfully after transitioning from loading to loaded state", () => {
    installMatchMedia();

    const snapshotRefetch = vi.fn();
    const historyRefetch = vi.fn();

    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: {
        as_of_date: "2026-04-11",
        points: [
          {
            trade_date: "2026-04-10",
            regime_label: "green",
            long_term_score: 72.1,
            short_term_score: 61.5,
            system_risk_score: 55.4,
            panic_reversal_score: 25.0,
          },
        ],
      },
      refetch: historyRefetch,
    }));
    mockUseMarketMonitorTraces.mockImplementation(() => ({
      data: [{ trace_id: "trace-1", status: "running" }],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceLogs.mockImplementation(() => ({
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:30Z",
          level: "Request",
          content: "市场监控快照请求开始：2026-04-11",
        },
      ],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));

    mockUseMarketMonitorSnapshot.mockImplementationOnce(() => ({
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
      refetch: snapshotRefetch,
    }));

    const { rerender } = render(<MarketMonitorPage />);

    expect(screen.getByText("市场监控")).toBeInTheDocument();
    expect(screen.getByText("正在分析市场状态")).toBeInTheDocument();
    expect(screen.getByText("执行过程")).toBeInTheDocument();
    expect(screen.getByText("接收请求")).toBeInTheDocument();

    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      data: buildLoadedSnapshot(),
      error: null,
      refetch: snapshotRefetch,
    }));
    mockUseMarketMonitorTraces.mockImplementation(() => ({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceLogs.mockImplementation(() => ({
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:30Z",
          level: "Request",
          content: "市场监控快照请求开始：2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T08:30:00Z",
          level: "Response",
          content: "市场监控快照请求完成",
        },
      ],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    }));

    rerender(<MarketMonitorPage />);

    expect(screen.getByText("规则快照 + 模型叠加")).toBeInTheDocument();
    expect(screen.getByText(/更新时间 2026-04-11 .*:30:00/)).toBeInTheDocument();
    expect(screen.getByText("返回结果")).toBeInTheDocument();
    expect(screen.getByText("实时 Yahoo Finance 日线")).toBeInTheDocument();
    expect(screen.getByText("市场监控 API 服务")).toBeInTheDocument();
    expect(screen.getByText("待接入的盘中恐慌确认")).toBeInTheDocument();
    expect(screen.getByText("长期 72.1")).toBeInTheDocument();
    expect(screen.getByText("短期 61.5")).toBeInTheDocument();

    const pageCards = document.querySelectorAll(".page-card");
    expect(pageCards[pageCards.length - 1]?.textContent).toContain("执行过程");
  });

  it("does not mark trailing steps as completed before terminal logs arrive", () => {
    installMatchMedia();

    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorTraces.mockImplementation(() => ({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceLogs.mockImplementation(() => ({
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:30Z",
          level: "Request",
          content: "市场监控快照请求开始：2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T08:29:31Z",
          level: "Overlay",
          content: "已生成 3 条上下文查询",
        },
      ],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      data: buildLoadedSnapshot(),
    }));

    render(<MarketMonitorPage />);

    const mergeStep = screen.getByText("合并最终决策").closest(".ant-list-item");
    const responseStep = screen.getByText("返回结果").closest(".ant-list-item");

    expect(mergeStep).not.toBeNull();
    expect(responseStep).not.toBeNull();
    expect(within(mergeStep as HTMLElement).getByText("等待中")).toBeInTheDocument();
    expect(within(responseStep as HTMLElement).getByText("等待中")).toBeInTheDocument();
  });

  it("shows help triggers for the documented market monitor cards", async () => {
    installMatchMedia();

    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorTraces.mockImplementation(() => ({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceLogs.mockImplementation(() => ({
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      data: buildLoadedSnapshot({
        rule_snapshot: {
          ...buildLoadedSnapshot().rule_snapshot,
          panic_reversal_score: {
            score: 64,
            zone: "一级试错",
            state: "confirmed",
            early_entry_allowed: true,
            stop_loss: "ATRx1.0",
            profit_rule: "1R 兑现 50%",
            action: "允许轻仓试探",
          },
        },
      }),
    }));

    render(<MarketMonitorPage />);

    const panicTrigger = screen.getByTestId("card-help-trigger-panic_module");
    expect(screen.getByTestId("card-help-trigger-long_term_score")).toBeInTheDocument();
    expect(screen.getByTestId("card-help-trigger-short_term_score")).toBeInTheDocument();
    expect(screen.getByTestId("card-help-trigger-system_risk_score")).toBeInTheDocument();
    expect(screen.getByTestId("card-help-trigger-model_overlay")).toBeInTheDocument();
    expect(screen.getByTestId("card-help-trigger-rule_snapshot")).toBeInTheDocument();
    expect(screen.queryByTestId("card-help-trigger-final_execution")).not.toBeInTheDocument();

    const user = userEvent.setup();
    await user.hover(panicTrigger);

    expect(await screen.findByTestId("card-help-content-panic_module")).toBeInTheDocument();
    expect(screen.getByText("作用")).toBeInTheDocument();
    expect(screen.getByText("评分或结论计算规则")).toBeInTheDocument();
  });
});
