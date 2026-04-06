import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { BacktestCreatePage } from "./pages/BacktestCreatePage";
import { BacktestDetailPage } from "./pages/BacktestDetailPage";
import { CreateJobPage } from "./pages/CreateJobPage";
import { HistoricalBacktestsPage } from "./pages/HistoricalBacktestsPage";
import { HistoricalReportDetailPage } from "./pages/HistoricalReportDetailPage";
import { HistoricalReportsPage } from "./pages/HistoricalReportsPage";
import { JobDetailPage } from "./pages/JobDetailPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function RootApp() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppLayout>
          <Routes>
            <Route path="/" element={<CreateJobPage />} />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
            <Route path="/backtests" element={<BacktestCreatePage />} />
            <Route path="/backtests/:jobId" element={<BacktestDetailPage />} />
            <Route path="/backtests/history" element={<HistoricalBacktestsPage />} />
            <Route path="/reports" element={<HistoricalReportsPage />} />
            <Route
              path="/reports/:jobId"
              element={<HistoricalReportDetailPage />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
