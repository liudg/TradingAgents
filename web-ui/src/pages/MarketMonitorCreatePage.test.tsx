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
        debug_options: null,
        llm_config: null,
      });
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/monitor/runs/run-debug-1");
    });
  });

  it("requires replay run id when reusing fact sheet in debug mode", async () => {
    installMatchMedia();
    const mutateAsync = vi.fn().mockResolvedValue({ run_id: "run-debug-2" });
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

    fireEvent.mouseDown(screen.getByLabelText("运行类型"));
    fireEvent.click(await screen.findByText("单卡调试"));
    fireEvent.mouseDown(screen.getByLabelText("调试卡片"));
    fireEvent.click((await screen.findAllByText("long_term"))[0]);
    fireEvent.click(screen.getByText("复用 fact sheet"));
    fireEvent.click(screen.getByText("创建运行"));

    await waitFor(() => {
      expect(screen.getByText("复用 fact sheet 时必须填写来源 Run ID")).toBeInTheDocument();
    });
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("submits debug payload with replay run id when reusing fact sheet", async () => {
    installMatchMedia();
    const mutateAsync = vi.fn().mockResolvedValue({ run_id: "run-debug-3" });
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

    fireEvent.mouseDown(screen.getByLabelText("运行类型"));
    fireEvent.click(await screen.findByText("单卡调试"));
    fireEvent.mouseDown(screen.getByLabelText("调试卡片"));
    fireEvent.click((await screen.findAllByText("execution"))[0]);
    fireEvent.click(screen.getByText("复用 fact sheet"));
    fireEvent.change(screen.getByPlaceholderText("必填，填写历史运行 ID"), { target: { value: "run-source-1" } });
    fireEvent.click(screen.getByText("创建运行"));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        trigger_endpoint: "debug_card",
        as_of_date: null,
        days: null,
        force_refresh: false,
        mode: "debug_card",
        debug_options: {
          debug_card: "execution",
          reuse_fact_sheet: true,
          replay_from_run_id: "run-source-1",
        },
        llm_config: null,
      });
    });
  });
});
