import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildTraceSteps,
  MarketMonitorExecutionTrace,
} from "./MarketMonitorExecutionTrace";

const runningTraceDetail = {
  trace_id: "trace-1",
  as_of_date: "2026-04-11",
  status: "running",
  force_refresh: false,
  started_at: "2026-04-11T01:16:34",
  finished_at: null,
  duration_ms: null,
  overall_confidence: null,
  long_term_label: null,
  execution_label: null,
  request: { as_of_date: "2026-04-11" },
  cache_decision: { snapshot_cache_hit: false, dataset_cache_hit: false },
  dataset_summary: { source: "live_request" },
  context_summary: {},
  assessment_summary: {},
  response_summary: {},
  error: {},
};

describe("MarketMonitorExecutionTrace", () => {
  beforeEach(() => {
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
  });

  it("renders grouped execution steps from trace logs", () => {
    render(
      <MarketMonitorExecutionTrace
        logs={[
          {
            line_no: 1,
            timestamp: "2026-04-11T01:16:34",
            level: "Request",
            content: "市场监控快照请求开始：2026-04-11",
          },
          {
            line_no: 2,
            timestamp: "2026-04-11T01:16:34",
            level: "Cache",
            content: "快照缓存决策：snapshot_cache_miss",
          },
          {
            line_no: 3,
            timestamp: "2026-04-11T01:16:34",
            level: "Dataset",
            content: "复用内存中的数据集缓存",
          },
          {
            line_no: 4,
            timestamp: "2026-04-11T01:16:34",
            level: "Context",
            content: "已组装上下文：16 个本地符号，4 个缺失项",
          },
        ]}
        traceDetail={runningTraceDetail}
        isLoading={false}
        isFetching={false}
        isCompleted={false}
      />,
    );

    expect(screen.getByText("执行过程")).toBeInTheDocument();
    expect(screen.getByText("接收请求")).toBeInTheDocument();
    expect(screen.getByText("检查缓存")).toBeInTheDocument();
    expect(screen.getByText("准备市场数据")).toBeInTheDocument();
    expect(screen.getByText("组装裁决上下文")).toBeInTheDocument();
    expect(screen.getByText("生成 LLM 裁决")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
    expect(screen.getByText("已组装上下文：16 个本地符号，4 个缺失项")).toBeInTheDocument();
  });

  it("marks the failing step when an error log appears", () => {
    render(
      <MarketMonitorExecutionTrace
        logs={[
          {
            line_no: 1,
            timestamp: "2026-04-11T01:16:34",
            level: "Request",
            content: "市场监控快照请求开始：2026-04-11",
          },
          {
            line_no: 2,
            timestamp: "2026-04-11T01:17:24",
            level: "Assessment",
            content: "LLM 裁决失败",
          },
          {
            line_no: 3,
            timestamp: "2026-04-11T01:17:24",
            level: "Error",
            content: "RuntimeError: 上游服务不可用",
          },
        ]}
        traceDetail={{
          ...runningTraceDetail,
          status: "failed",
          context_summary: { local_symbol_count: 16 },
          error: { stage: "snapshot", message: "RuntimeError: 涓婃父鏈嶅姟涓嶅彲鐢?" },
        }}
        isLoading={false}
        isFetching={false}
        isCompleted={false}
      />,
    );

    expect(screen.getByText("生成 LLM 裁决")).toBeInTheDocument();
    expect(screen.getByText("执行失败")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError: 上游服务不可用")).toBeInTheDocument();
  });

  it("shows a loading hint before trace logs arrive", () => {
    render(
      <MarketMonitorExecutionTrace
        logs={[]}
        traceDetail={null}
        isLoading={true}
        isFetching={true}
        isCompleted={false}
      />,
    );

    expect(screen.getByText("正在分析市场状态，步骤会实时展示在这里。")).toBeInTheDocument();
  });

  it("keeps trailing steps waiting until terminal logs arrive", () => {
    const steps = buildTraceSteps(
      [
        {
          line_no: 1,
          timestamp: "2026-04-11T01:16:34",
          level: "Request",
          content: "市场监控快照请求开始：2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T01:16:34",
          level: "Cache",
          content: "快照缓存决策：snapshot_cache_miss",
        },
        {
          line_no: 3,
          timestamp: "2026-04-11T01:16:34",
          level: "Dataset",
          content: "已从市场数据源构建数据集",
        },
        {
          line_no: 4,
          timestamp: "2026-04-11T01:16:34",
          level: "Context",
          content: "已组装上下文：16 个本地符号，4 个缺失项",
        },
        {
          line_no: 5,
          timestamp: "2026-04-11T01:16:34",
          level: "Assessment",
          content: "LLM 裁决完成：长线=偏多，执行=顺势参与",
        },
      ],
      {
        ...runningTraceDetail,
        status: "completed",
        context_summary: { local_symbol_count: 16 },
        assessment_summary: { overall_confidence: 0.8 },
      },
      true,
    );

    expect(steps.find((item) => item.key === "assessment")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "response")?.status).toBe("waiting");
  });

  it("derives running status from trace detail even before terminal logs arrive", () => {
    const steps = buildTraceSteps(
      [
        {
          line_no: 1,
          timestamp: "2026-04-11T01:16:34",
          level: "Request",
          content: "甯傚満鐩戞帶蹇収璇锋眰寮€濮嬶細2026-04-11",
        },
      ],
      {
        ...runningTraceDetail,
        context_summary: { local_symbol_count: 16 },
      },
      false,
    );

    expect(steps.find((item) => item.key === "request")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "cache")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "dataset")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "context")?.status).toBe("running");
  });

  it("marks non-executed middle steps as skipped on cache-hit completion", () => {
    const steps = buildTraceSteps(
      [
        {
          line_no: 1,
          timestamp: "2026-04-11T01:16:34",
          level: "Request",
          content: "甯傚満鐩戞帶蹇収璇锋眰寮€濮嬶細2026-04-11",
        },
        {
          line_no: 2,
          timestamp: "2026-04-11T01:16:35",
          level: "Response",
          content: "杩斿洖缂撳瓨蹇収",
        },
      ],
      {
        ...runningTraceDetail,
        status: "completed",
        cache_decision: { snapshot_cache_hit: true, dataset_cache_hit: false },
        assessment_summary: { overall_confidence: 0.82 },
        response_summary: { served_from_snapshot_cache: true },
      },
      true,
    );

    expect(steps.find((item) => item.key === "cache")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "dataset")?.status).toBe("skipped");
    expect(steps.find((item) => item.key === "context")?.status).toBe("skipped");
    expect(steps.find((item) => item.key === "assessment")?.status).toBe("completed");
    expect(steps.find((item) => item.key === "response")?.status).toBe("completed");
  });
});
