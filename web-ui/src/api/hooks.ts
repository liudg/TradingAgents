import { useMutation, useQuery } from "@tanstack/react-query";

import {
  createAnalysisJob,
  createBacktestJob,
  fetchAnalysisJob,
  fetchAnalysisJobLogs,
  fetchAnalysisReport,
  fetchBacktestJob,
  fetchBacktestJobLogs,
  fetchHistoricalBacktest,
  fetchHistoricalBacktests,
  fetchHistoricalReport,
  fetchHistoricalReports,
  fetchMarketMonitorDataStatus,
  fetchMarketMonitorHistory,
  fetchMarketMonitorSnapshot,
  fetchMarketMonitorTraceDetail,
  fetchMarketMonitorTraceLogs,
  fetchMarketMonitorTraces,
  fetchMetadataOptions,
} from "./client";
import { AnalysisJobRequest, BacktestJobRequest, JobStatus } from "./types";

const activeStatuses: JobStatus[] = ["pending", "running"];

export function useMetadataOptions() {
  return useQuery({
    queryKey: ["metadata-options"],
    queryFn: fetchMetadataOptions,
  });
}

export function useCreateAnalysisJob() {
  return useMutation({
    mutationFn: (payload: AnalysisJobRequest) => createAnalysisJob(payload),
  });
}

export function useAnalysisJob(jobId: string) {
  return useQuery({
    queryKey: ["analysis-job", jobId],
    queryFn: () => fetchAnalysisJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && activeStatuses.includes(status) ? 2000 : false;
    },
    enabled: Boolean(jobId),
  });
}

export function useAnalysisReport(jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["analysis-report", jobId],
    queryFn: () => fetchAnalysisReport(jobId),
    enabled,
  });
}

export function useAnalysisJobLogs(jobId: string, status?: JobStatus) {
  return useQuery({
    queryKey: ["analysis-job-logs", jobId],
    queryFn: () => fetchAnalysisJobLogs(jobId),
    refetchInterval:
      status && activeStatuses.includes(status) ? 2000 : false,
    enabled: Boolean(jobId),
  });
}

export function useHistoricalReports() {
  return useQuery({
    queryKey: ["historical-reports"],
    queryFn: fetchHistoricalReports,
  });
}

export function useHistoricalReport(jobId: string) {
  return useQuery({
    queryKey: ["historical-report", jobId],
    queryFn: () => fetchHistoricalReport(jobId),
    enabled: Boolean(jobId),
  });
}

export function useCreateBacktestJob() {
  return useMutation({
    mutationFn: (payload: BacktestJobRequest) => createBacktestJob(payload),
  });
}

export function useBacktestJob(jobId: string) {
  return useQuery({
    queryKey: ["backtest-job", jobId],
    queryFn: () => fetchBacktestJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && activeStatuses.includes(status) ? 2000 : false;
    },
    enabled: Boolean(jobId),
  });
}

export function useBacktestJobLogs(jobId: string, status?: JobStatus) {
  return useQuery({
    queryKey: ["backtest-job-logs", jobId],
    queryFn: () => fetchBacktestJobLogs(jobId),
    refetchInterval:
      status && activeStatuses.includes(status) ? 2000 : false,
    enabled: Boolean(jobId),
  });
}

export function useHistoricalBacktests() {
  return useQuery({
    queryKey: ["historical-backtests"],
    queryFn: fetchHistoricalBacktests,
  });
}

export function useHistoricalBacktest(jobId: string) {
  return useQuery({
    queryKey: ["historical-backtest", jobId],
    queryFn: () => fetchHistoricalBacktest(jobId),
    enabled: Boolean(jobId),
  });
}

export function useMarketMonitorSnapshot() {
  return useQuery({
    queryKey: ["market-monitor-snapshot"],
    queryFn: fetchMarketMonitorSnapshot,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.trace_id ? false : 2000;
    },
  });
}

export function useMarketMonitorHistory(enabled = true) {
  return useQuery({
    queryKey: ["market-monitor-history"],
    queryFn: fetchMarketMonitorHistory,
    enabled,
  });
}

export function useMarketMonitorDataStatus() {
  return useQuery({
    queryKey: ["market-monitor-data-status"],
    queryFn: fetchMarketMonitorDataStatus,
  });
}

export function useMarketMonitorTraceLogs(
  traceId?: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["market-monitor-trace-logs", traceId],
    queryFn: () => fetchMarketMonitorTraceLogs(traceId || ""),
    refetchInterval: (query) => {
      const logs = Array.isArray(query.state.data) ? query.state.data : [];
      const hasTerminalLog = logs.some(
        (item) => item.level === "Response" || item.level === "Error",
      );
      return enabled && traceId && !hasTerminalLog ? 2000 : false;
    },
    enabled: enabled && Boolean(traceId),
  });
}

export function useMarketMonitorTraceDetail(
  traceId?: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["market-monitor-trace-detail", traceId],
    queryFn: () => fetchMarketMonitorTraceDetail(traceId || ""),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return enabled && traceId && status === "running" ? 2000 : false;
    },
    enabled: enabled && Boolean(traceId),
  });
}

export function useMarketMonitorTraces(
  status?: string,
  enabled = true,
  limit = 20,
) {
  return useQuery({
    queryKey: ["market-monitor-traces", status, limit],
    queryFn: () => fetchMarketMonitorTraces(status, limit),
    refetchInterval: enabled ? 2000 : false,
    enabled,
  });
}
