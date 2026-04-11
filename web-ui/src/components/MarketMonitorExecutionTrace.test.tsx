import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildTraceSteps,
  MarketMonitorExecutionTrace,
} from "./MarketMonitorExecutionTrace";

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
            level: "Rule",
            content: "规则快照 ready=True，基础状态=green",
          },
        ]}
        isLoading={false}
        isFetching={false}
        isCompleted={false}
      />,
    );

    expect(screen.getByText("执行过程")).toBeInTheDocument();
    expect(screen.getByText("接收请求")).toBeInTheDocument();
    expect(screen.getByText("检查缓存")).toBeInTheDocument();
    expect(screen.getByText("准备市场数据")).toBeInTheDocument();
    expect(screen.getByText("生成规则快照")).toBeInTheDocument();
    expect(screen.getByText("生成模型叠加")).toBeInTheDocument();
    expect(screen.getByText("进行中")).toBeInTheDocument();
    expect(screen.getByText("规则快照 ready=True，基础状态=green")).toBeInTheDocument();
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
            level: "Overlay",
            content: "模型叠加状态=error",
          },
          {
            line_no: 3,
            timestamp: "2026-04-11T01:17:24",
            level: "Error",
            content: "RuntimeError: 上游服务不可用",
          },
        ]}
        isLoading={false}
        isFetching={false}
        isCompleted={false}
      />,
    );

    expect(screen.getByText("生成模型叠加")).toBeInTheDocument();
    expect(screen.getByText("执行失败")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError: 上游服务不可用")).toBeInTheDocument();
  });

  it("shows a loading hint before trace logs arrive", () => {
    render(
      <MarketMonitorExecutionTrace
        logs={[]}
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
          level: "Rule",
          content: "规则快照 ready=True，基础状态=green",
        },
        {
          line_no: 5,
          timestamp: "2026-04-11T01:16:34",
          level: "Overlay",
          content: "已生成 3 条上下文查询",
        },
      ],
      true,
    );

    expect(steps.find((item) => item.key === "merge")?.status).toBe("waiting");
    expect(steps.find((item) => item.key === "response")?.status).toBe("waiting");
  });
});
