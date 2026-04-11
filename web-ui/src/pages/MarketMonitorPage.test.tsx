import { render, screen } from "@testing-library/react";
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

function buildSnapshot() {
  return {
    timestamp: "2026-04-11T08:30:00Z",
    as_of_date: "2026-04-11",
    trace_id: "trace-1",
    market_data_snapshot: {
      local_market_data: {
        SPY: { close: 510.2, change_20d_pct: 4.1, above_ma200: true },
        QQQ: { close: 430.4, change_20d_pct: 5.3, above_ma200: true },
      },
      derived_metrics: {
        breadth_above_200dma_pct: 75,
        spy_distance_to_ma200_pct: 6.2,
      },
      llm_reasoning_notes: ["已补充未来三日宏观事件与财报日历。"],
    },
    missing_data: [
      {
        key: "vix_term_structure",
        label: "VIX 期限结构",
        required_for: ["long_term_card", "system_risk_card"],
        status: "filled_by_search",
        note: "通过搜索补充事件背景，不作为本地时序因子。",
      },
    ],
    assessment: {
      long_term_card: {
        label: "偏多",
        summary: "中期趋势与广度共振偏多。",
        confidence: 0.84,
        data_completeness: "medium",
        key_evidence: ["SPY 站上 MA200", "QQQ 同步走强"],
        missing_data_filled_by_search: ["VIX 期限结构背景"],
        action: "允许继续持有趋势仓。",
      },
      short_term_card: {
        label: "可做",
        summary: "短线环境允许参与，但事件前减少追价。",
        confidence: 0.76,
        data_completeness: "medium",
        key_evidence: ["行业动量扩散改善"],
        missing_data_filled_by_search: ["未来三日事件窗口"],
        action: "优先低吸而非追突破。",
      },
      system_risk_card: {
        label: "正常",
        summary: "系统性风险未明显恶化。",
        confidence: 0.8,
        data_completeness: "medium",
        key_evidence: ["VIX 未出现异常抬升"],
        missing_data_filled_by_search: [],
        action: "使用标准风险预算。",
      },
      execution_card: {
        label: "顺势参与",
        summary: "维持偏多，但控制事件日前追高。",
        confidence: 0.81,
        data_completeness: "medium",
        key_evidence: ["趋势偏多", "未来三日事件密集"],
        missing_data_filled_by_search: ["银行财报日历"],
        action: "继续参与，但压低追高频率。",
        total_exposure_range: "50%-70%",
        new_position_allowed: true,
        chase_breakout_allowed: false,
        dip_buy_allowed: true,
        overnight_allowed: true,
        leverage_allowed: false,
        single_position_cap: "10%",
        daily_risk_budget: "1.0R",
      },
      event_risk_card: {
        label: "事件密集",
        summary: "未来三日存在宏观与财报事件簇。",
        confidence: 0.78,
        data_completeness: "high",
        key_evidence: ["PPI", "大型银行财报"],
        missing_data_filled_by_search: ["已搜索事件日历"],
        action: "减少事件前追价。",
      },
      panic_card: {
        label: "未激活",
        summary: "没有恐慌反转条件。",
        confidence: 0.83,
        data_completeness: "medium",
        key_evidence: ["未见恐慌抛售"],
        missing_data_filled_by_search: [],
        action: "无需执行恐慌策略。",
      },
    },
    evidence_sources: ["bls.gov", "federalreserve.gov"],
    overall_confidence: 0.81,
  };
}

describe("MarketMonitorPage", () => {
  it("renders the new assessment cards and evidence panels", () => {
    installMatchMedia();

    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: {
        as_of_date: "2026-04-11",
        points: [
          {
            trade_date: "2026-04-10",
            overall_confidence: 0.79,
            long_term_label: "偏多",
            short_term_label: "可做",
            system_risk_label: "正常",
            execution_label: "顺势参与",
          },
        ],
      },
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
      data: buildSnapshot(),
      error: null,
      refetch: vi.fn(),
    }));

    render(<MarketMonitorPage />);

    expect(screen.getByText("整体置信度 0.81")).toBeInTheDocument();
    expect(screen.getByText("长线环境")).toBeInTheDocument();
    expect(screen.getAllByText("顺势参与").length).toBeGreaterThan(0);
    expect(screen.getByText("事件密集")).toBeInTheDocument();
    expect(screen.getByText("未来三日存在宏观与财报事件簇。")).toBeInTheDocument();
    expect(screen.getByText("本地数据证据")).toBeInTheDocument();
    expect(screen.getByText("缺失数据与补全")).toBeInTheDocument();
    expect(screen.getByText("VIX 期限结构")).toBeInTheDocument();
    expect(screen.getByText("bls.gov")).toBeInTheDocument();
    expect(screen.getByText("2026-04-10")).toBeInTheDocument();
  });
});
