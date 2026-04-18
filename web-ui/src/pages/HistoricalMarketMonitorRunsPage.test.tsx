import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { HistoricalMarketMonitorRunsPage } from "./HistoricalMarketMonitorRunsPage";

const mockUseMarketMonitorRuns = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../api/hooks", () => ({
  useMarketMonitorRuns: (...args: unknown[]) => mockUseMarketMonitorRuns(...args),
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

describe("HistoricalMarketMonitorRunsPage", () => {
  it("defaults to snapshot runs and opens detail when clicked", () => {
    installMatchMedia();
    mockUseMarketMonitorRuns.mockReset();
    mockNavigate.mockReset();

    mockUseMarketMonitorRuns.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      data: [
        {
          run_id: "run-snapshot",
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
          log_path: "results/market_monitor/2026-04-11/run-snapshot/market_monitor.log",
          results_dir: "results/market_monitor/2026-04-11/run-snapshot",
        },
        {
          run_id: "run-history",
          trigger_endpoint: "history",
          as_of_date: "2026-04-11",
          days: 20,
          status: "completed",
          generated_at: "2026-04-11T08:30:00Z",
          data_freshness: "delayed_15min",
          source_completeness: "medium",
          regime_label: "黄灯",
          degraded: false,
          error_message: null,
          log_path: "results/market_monitor/2026-04-11/run-history/market_monitor.log",
          results_dir: "results/market_monitor/2026-04-11/run-history",
        },
      ],
    });

    render(
      <MemoryRouter>
        <HistoricalMarketMonitorRunsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("市场监控历史")).toBeInTheDocument();
    expect(screen.getByText("黄绿灯-Swing")).toBeInTheDocument();
    expect(screen.queryByText("历史 20 天")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("2026-04-11"));
    expect(mockNavigate).toHaveBeenCalledWith("/monitor/runs/run-snapshot");
  });

  it("shows empty state when snapshot filter removes non-snapshot runs", () => {
    installMatchMedia();
    mockUseMarketMonitorRuns.mockReset();

    mockUseMarketMonitorRuns.mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      data: [
        {
          run_id: "run-history",
          trigger_endpoint: "history",
          as_of_date: "2026-04-11",
          days: 20,
          status: "completed",
          generated_at: "2026-04-11T08:30:00Z",
          data_freshness: "delayed_15min",
          source_completeness: "medium",
          regime_label: "黄灯",
          degraded: false,
          error_message: null,
          log_path: null,
          results_dir: null,
        },
      ],
    });

    render(
      <MemoryRouter>
        <HistoricalMarketMonitorRunsPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("没有匹配的运行记录")).toBeInTheDocument();
  });
});
