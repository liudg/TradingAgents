import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketMonitorPage } from "./MarketMonitorPage";

const mockUseMarketMonitorSnapshot = vi.fn();
const mockUseMarketMonitorHistory = vi.fn();
const mockUseMarketMonitorTraceLogs = vi.fn();
const mockUseMarketMonitorTraces = vi.fn();
let snapshotQueryState: unknown;
let historyQueryState: unknown;
let traceLogsQueryState: unknown;
let tracesQueryState: unknown;

vi.mock("../api/hooks", () => ({
  useMarketMonitorSnapshot: () => mockUseMarketMonitorSnapshot(),
  useMarketMonitorHistory: () => mockUseMarketMonitorHistory(),
  useMarketMonitorTraceLogs: () => mockUseMarketMonitorTraceLogs(),
  useMarketMonitorTraces: () => mockUseMarketMonitorTraces(),
}));

describe("MarketMonitorPage", () => {
  it("renders successfully after transitioning from loading to loaded state", () => {
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

    const snapshotRefetch = vi.fn();
    const historyRefetch = vi.fn();

    historyQueryState = {
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: historyRefetch,
    };
    mockUseMarketMonitorHistory.mockImplementation(() => historyQueryState);
    tracesQueryState = {
      data: [{ trace_id: "trace-1", status: "running" }],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    mockUseMarketMonitorTraces.mockImplementation(() => tracesQueryState);
    traceLogsQueryState = {
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:30Z",
          level: "Request",
          content: "Snapshot request started for 2026-04-11",
        },
      ],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    };
    mockUseMarketMonitorTraceLogs.mockImplementation(() => traceLogsQueryState);

    snapshotQueryState = {
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
      refetch: snapshotRefetch,
    };
    mockUseMarketMonitorSnapshot.mockImplementation(() => snapshotQueryState);

    const { rerender } = render(<MarketMonitorPage />);

    expect(screen.getByText("市场监控")).toBeInTheDocument();
    expect(screen.getByText("正在分析市场状态")).toBeInTheDocument();
    expect(screen.getByText("执行过程")).toBeInTheDocument();
    expect(screen.getByText("接收请求")).toBeInTheDocument();

    snapshotQueryState = {
      isLoading: false,
      isError: false,
      data: {
        timestamp: "2026-04-11T08:30:00Z",
        as_of_date: "2026-04-11",
        trace_id: "trace-1",
        rule_snapshot: {
          ready: true,
          long_term_score: {
            score: 72.1,
            zone: "bullish",
            delta_1d: 1.2,
            delta_5d: 2.8,
            slope_state: "rising",
            action: "Stay constructive",
          },
          short_term_score: {
            score: 61.5,
            zone: "neutral",
            delta_1d: 0.4,
            delta_5d: 1.1,
            slope_state: "stable",
            action: "Watch pullbacks",
          },
          system_risk_score: {
            score: 55.4,
            zone: "moderate",
            delta_1d: -0.5,
            delta_5d: 0.3,
            slope_state: "stable",
            action: "Keep size disciplined",
          },
          panic_reversal_score: null,
          base_regime_label: "green",
          base_execution_card: {
            regime_label: "green",
            conflict_mode: "normal",
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
              note: "Confirmed",
            },
            event_risk_flag: {
              index_level: { active: false, type: null, note: "" },
              stock_level: { active: false, rule: "standard", tickers: [] },
            },
            summary: "Risk-on bias intact.",
          },
          base_event_risk_flag: {
            index_level: { active: false, type: null, note: "" },
            stock_level: { active: false, rule: "standard", tickers: [] },
          },
          source_coverage: {
            status: "full",
            data_freshness: "fresh",
            degraded_factors: [],
            notes: [],
          },
          missing_inputs: [],
          degraded_factors: [],
          key_indicators: {},
        },
        model_overlay: {
          status: "applied",
          regime_override: "green",
          execution_adjustments: null,
          event_risk_override: null,
          market_narrative: "Breadth is improving.",
          risk_narrative: "Risk remains contained.",
          panic_narrative: "No panic reversal setup.",
          evidence_sources: ["snapshot"],
          model_confidence: 0.82,
          notes: [],
        },
        final_execution_card: {
          regime_label: "green",
          conflict_mode: "normal",
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
            note: "Confirmed",
          },
          event_risk_flag: {
            index_level: { active: false, type: null, note: "" },
            stock_level: { active: false, rule: "standard", tickers: [] },
          },
          summary: "Follow the dominant trend.",
        },
      },
      error: null,
      refetch: snapshotRefetch,
    };
    tracesQueryState = {
      data: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    };
    traceLogsQueryState = {
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:30Z",
          level: "Request",
          content: "Snapshot request started for 2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T08:30:00Z",
          level: "Response",
          content: "Snapshot request completed",
        },
      ],
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
    };

    rerender(<MarketMonitorPage />);

    expect(screen.getByText("规则快照 + 模型叠加")).toBeInTheDocument();
    expect(screen.getByText(/更新时间 2026-04-11 .*:30:00/)).toBeInTheDocument();
    expect(screen.getByText("返回结果")).toBeInTheDocument();

    const pageCards = document.querySelectorAll(".page-card");
    expect(pageCards[pageCards.length - 1]?.textContent).toContain("执行过程");
  });

  it("does not mark trailing steps as completed before terminal logs arrive", () => {
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
          content: "Snapshot request started for 2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T08:29:31Z",
          level: "Overlay",
          content: "Generated 3 context queries",
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
      data: {
        timestamp: "2026-04-11T08:30:00Z",
        as_of_date: "2026-04-11",
        trace_id: "trace-1",
        rule_snapshot: {
          ready: true,
          long_term_score: {
            score: 72.1,
            zone: "bullish",
            delta_1d: 1.2,
            delta_5d: 2.8,
            slope_state: "rising",
            action: "Stay constructive",
          },
          short_term_score: {
            score: 61.5,
            zone: "neutral",
            delta_1d: 0.4,
            delta_5d: 1.1,
            slope_state: "stable",
            action: "Watch pullbacks",
          },
          system_risk_score: {
            score: 55.4,
            zone: "moderate",
            delta_1d: -0.5,
            delta_5d: 0.3,
            slope_state: "stable",
            action: "Keep size disciplined",
          },
          panic_reversal_score: null,
          base_regime_label: "green",
          base_execution_card: {
            regime_label: "green",
            conflict_mode: "normal",
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
              note: "Confirmed",
            },
            event_risk_flag: {
              index_level: { active: false, type: null, note: "" },
              stock_level: { active: false, rule: "standard", tickers: [] },
            },
            summary: "Risk-on bias intact.",
          },
          base_event_risk_flag: {
            index_level: { active: false, type: null, note: "" },
            stock_level: { active: false, rule: "standard", tickers: [] },
          },
          source_coverage: {
            status: "full",
            data_freshness: "fresh",
            degraded_factors: [],
            notes: [],
          },
          missing_inputs: [],
          degraded_factors: [],
          key_indicators: {},
        },
        model_overlay: {
          status: "applied",
          regime_override: "green",
          execution_adjustments: null,
          event_risk_override: null,
          market_narrative: "Breadth is improving.",
          risk_narrative: "Risk remains contained.",
          panic_narrative: "No panic reversal setup.",
          evidence_sources: ["snapshot"],
          model_confidence: 0.82,
          notes: [],
        },
        final_execution_card: {
          regime_label: "green",
          conflict_mode: "normal",
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
            note: "Confirmed",
          },
          event_risk_flag: {
            index_level: { active: false, type: null, note: "" },
            stock_level: { active: false, rule: "standard", tickers: [] },
          },
          summary: "Follow the dominant trend.",
        },
      },
    }));

    render(<MarketMonitorPage />);

    const mergeStep = screen.getByText("合并最终决策").closest(".ant-list-item");
    const responseStep = screen.getByText("返回结果").closest(".ant-list-item");

    expect(mergeStep).not.toBeNull();
    expect(responseStep).not.toBeNull();
    expect(within(mergeStep as HTMLElement).getByText("等待中")).toBeInTheDocument();
    expect(within(responseStep as HTMLElement).getByText("等待中")).toBeInTheDocument();
  });
});
