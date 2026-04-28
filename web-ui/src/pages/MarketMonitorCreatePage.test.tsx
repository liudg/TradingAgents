import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App as AntApp } from "antd";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { MarketMonitorCreatePage } from "./MarketMonitorCreatePage";

const mockUseCreateMarketMonitorRun = vi.fn();
const mockNavigate = vi.fn();

vi.mock("../api/hooks", () => ({
  useCreateMarketMonitorRun: (...args: unknown[]) => mockUseCreateMarketMonitorRun(...args),
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

describe("MarketMonitorCreatePage", () => {
  it("renders create form", () => {
    installMatchMedia();
    mockUseCreateMarketMonitorRun.mockReturnValue({ isPending: false, mutateAsync: vi.fn() });
    render(
      <AntApp>
        <MemoryRouter initialEntries={["/monitor/create"]}>
          <Routes>
            <Route path="/monitor/create" element={<MarketMonitorCreatePage />} />
          </Routes>
        </MemoryRouter>
      </AntApp>,
    );
    expect(screen.getByText("新建市场监控运行")).toBeInTheDocument();
    expect(screen.getByText("创建运行")).toBeInTheDocument();
  });

  it("submits snapshot payload and navigates to detail", async () => {
    installMatchMedia();
    const mutateAsync = vi.fn().mockResolvedValue({ run_id: "run-debug-1" });
    mockUseCreateMarketMonitorRun.mockReturnValue({ isPending: false, mutateAsync });
    render(
      <AntApp>
        <MemoryRouter initialEntries={["/monitor/create"]}>
          <Routes>
            <Route path="/monitor/create" element={<MarketMonitorCreatePage />} />
          </Routes>
        </MemoryRouter>
      </AntApp>,
    );
    fireEvent.click(screen.getByText("创建运行"));
    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        trigger_endpoint: "snapshot",
        as_of_date: null,
        days: null,
        force_refresh: false,
        mode: "snapshot",
        llm_config: null,
      });
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/monitor/runs/run-debug-1");
    });
  });
});
