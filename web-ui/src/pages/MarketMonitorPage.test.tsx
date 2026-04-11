import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketMonitorPage } from "./MarketMonitorPage";

const mockUseMarketMonitorSnapshot = vi.fn();
const mockUseMarketMonitorHistory = vi.fn();
const mockUseMarketMonitorTraceLogs = vi.fn();
const mockUseMarketMonitorTraces = vi.fn();
const mockUseMarketMonitorTraceDetail = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorSnapshot: () => mockUseMarketMonitorSnapshot(),
  useMarketMonitorHistory: () => mockUseMarketMonitorHistory(),
  useMarketMonitorTraceLogs: () => mockUseMarketMonitorTraceLogs(),
  useMarketMonitorTraces: () => mockUseMarketMonitorTraces(),
  useMarketMonitorTraceDetail: () => mockUseMarketMonitorTraceDetail(),
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
      },
      derived_metrics: {
        breadth_above_200dma_pct: 75,
      },
      llm_reasoning_notes: [],
    },
    missing_data: [],
    assessment: {
      long_term_card: {
        label: "偏多",
        summary: "中期趋势偏多。",
        confidence: 0.84,
        data_completeness: "medium",
        key_evidence: ["SPY 站上 MA200"],
        missing_data_filled_by_search: [],
        action: "允许继续持有趋势仓。",
      },
      short_term_card: {
        label: "可做",
        summary: "短线环境允许参与。",
        confidence: 0.76,
        data_completeness: "medium",
        key_evidence: ["行业动量扩散改善"],
        missing_data_filled_by_search: [],
        action: "优先低吸而非追突破。",
      },
      system_risk_card: {
        label: "正常",
        summary: "系统性风险未明显恶化。",
        confidence: 0.8,
        data_completeness: "medium",
        key_evidence: ["VIX 未异常抬升"],
        missing_data_filled_by_search: [],
        action: "使用标准风险预算。",
      },
      execution_card: {
        label: "顺势参与",
        summary: "维持偏多，但控制事件日前追高。",
        confidence: 0.81,
        data_completeness: "medium",
        key_evidence: ["趋势偏多", "未来三日事件密集"],
        missing_data_filled_by_search: [],
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
        missing_data_filled_by_search: [],
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
    evidence_sources: ["bls.gov"],
    overall_confidence: 0.81,
  };
}

function buildTraceDetail(status = "completed") {
  return {
    trace_id: "trace-1",
    as_of_date: "2026-04-11",
    status,
    force_refresh: false,
    started_at: "2026-04-11T08:29:00Z",
    finished_at: status === "completed" ? "2026-04-11T08:30:00Z" : null,
    duration_ms: status === "completed" ? 60000 : null,
    overall_confidence: status === "completed" ? 0.81 : null,
    long_term_label: status === "completed" ? "偏多" : null,
    execution_label: status === "completed" ? "顺势参与" : null,
    request: { as_of_date: "2026-04-11" },
    cache_decision: { snapshot_cache_hit: false, dataset_cache_hit: false },
    dataset_summary: { source: "live_request" },
    context_summary: { local_symbol_count: 16 },
    assessment_summary: status === "completed" ? { overall_confidence: 0.81 } : {},
    response_summary: status === "completed" ? { trace_id: "trace-1" } : {},
    error: {},
  };
}

describe("MarketMonitorPage", () => {
  it("renders assessment cards and execution trace after snapshot returns", () => {
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
          timestamp: "2026-04-11T08:29:00Z",
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
    mockUseMarketMonitorTraceDetail.mockImplementation(() => ({
      data: buildTraceDetail(),
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
    expect(screen.getByText("长期环境")).toBeInTheDocument();
    expect(screen.getByText("SPY 站上 MA200")).toBeInTheDocument();
    expect(screen.getByText("执行过程")).toBeInTheDocument();
  });

  it("shows execution trace while snapshot is still loading", () => {
    installMatchMedia();

    mockUseMarketMonitorHistory.mockImplementation(() => ({
      data: { as_of_date: "2026-04-11", points: [] },
      refetch: vi.fn(),
    }));
    mockUseMarketMonitorTraces.mockImplementation(() => ({
      data: [{ trace_id: "trace-running", status: "running" }],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceDetail.mockImplementation(() => ({
      data: { ...buildTraceDetail("running"), trace_id: "trace-running" },
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorTraceLogs.mockImplementation(() => ({
      data: [
        {
          line_no: 1,
          timestamp: "2026-04-11T08:29:00Z",
          level: "Request",
          content: "市场监控快照请求开始：2026-04-11",
        },
      ],
      isLoading: false,
      isFetching: true,
      isError: false,
      error: null,
    }));
    mockUseMarketMonitorSnapshot.mockImplementation(() => ({
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    }));

    render(<MarketMonitorPage />);

    expect(screen.getByText("执行过程")).toBeInTheDocument();
    expect(screen.getByText("正在生成市场裁决")).toBeInTheDocument();
  });
});
