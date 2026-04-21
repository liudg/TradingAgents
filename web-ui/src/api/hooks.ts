import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createAnalysisJob,
  createBacktestJob,
  createMarketMonitorRun,
  fetchAnalysisJob,
  fetchAnalysisJobLogs,
  fetchAnalysisReport,
  fetchBacktestJob,
  fetchBacktestJobLogs,
  fetchHistoricalBacktest,
  fetchHistoricalBacktests,
  fetchHistoricalReport,
  fetchHistoricalReports,
  fetchMarketMonitorArtifact,
  fetchMarketMonitorDataStatus,
  fetchMarketMonitorHistory,
  fetchMarketMonitorPromptTraces,
  fetchMarketMonitorRun,
  fetchMarketMonitorRunLogs,
  fetchMarketMonitorRuns,
  fetchMarketMonitorSnapshot,
  fetchMetadataOptions,
  recoverMarketMonitorRun,
} from "./client";
import { AnalysisJobRequest, BacktestJobRequest, JobStatus, MarketMonitorRunRequest } from "./types";

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

export function useMarketMonitorSnapshot(
  asOfDate?: string,
  forceRefresh = false,
  refreshKey = 0,
) {
  return useQuery({
    queryKey: ["market-monitor-snapshot", asOfDate ?? null, forceRefresh, refreshKey],
    queryFn: () => fetchMarketMonitorSnapshot(asOfDate, forceRefresh),
  });
}

export function useMarketMonitorHistory(
  days = 20,
  asOfDate?: string,
  forceRefresh = false,
  refreshKey = 0,
) {
  return useQuery({
    queryKey: ["market-monitor-history", days, asOfDate ?? null, forceRefresh, refreshKey],
    queryFn: () => fetchMarketMonitorHistory(days, asOfDate, forceRefresh),
  });
}

export function useMarketMonitorDataStatus(
  asOfDate?: string,
  forceRefresh = false,
  refreshKey = 0,
) {
  return useQuery({
    queryKey: ["market-monitor-data-status", asOfDate ?? null, forceRefresh, refreshKey],
    queryFn: () => fetchMarketMonitorDataStatus(asOfDate, forceRefresh),
  });
}

export function useCreateMarketMonitorRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MarketMonitorRunRequest) => createMarketMonitorRun(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["market-monitor-run", data.run_id], data);
      queryClient.invalidateQueries({ queryKey: ["market-monitor-runs"] });
    },
  });
}

export function useMarketMonitorRuns() {
  return useQuery({
    queryKey: ["market-monitor-runs"],
    queryFn: fetchMarketMonitorRuns,
  });
}

export function useMarketMonitorRun(runId: string) {
  return useQuery({
    queryKey: ["market-monitor-run", runId],
    queryFn: () => fetchMarketMonitorRun(runId),
    enabled: Boolean(runId),
  });
}

export function useMarketMonitorRunLogs(runId: string) {
  return useQuery({
    queryKey: ["market-monitor-run-logs", runId],
    queryFn: () => fetchMarketMonitorRunLogs(runId),
    enabled: Boolean(runId),
  });
}

export function useMarketMonitorPromptTraces(runId: string) {
  return useQuery({
    queryKey: ["market-monitor-prompt-traces", runId],
    queryFn: () => fetchMarketMonitorPromptTraces(runId),
    enabled: Boolean(runId),
  });
}

export function useMarketMonitorArtifact(runId: string, artifactName: string, enabled = true) {
  return useQuery({
    queryKey: ["market-monitor-artifact", runId, artifactName],
    queryFn: () => fetchMarketMonitorArtifact(runId, artifactName),
    enabled: Boolean(runId) && Boolean(artifactName) && enabled,
  });
}

export function useRecoverMarketMonitorRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => recoverMarketMonitorRun(runId),
    onSuccess: (data) => {
      queryClient.setQueryData(["market-monitor-run", data.run_id], data);
      queryClient.invalidateQueries({ queryKey: ["market-monitor-runs"] });
      queryClient.invalidateQueries({ queryKey: ["market-monitor-run", data.run_id] });
      queryClient.invalidateQueries({ queryKey: ["market-monitor-run-logs", data.run_id] });
      queryClient.invalidateQueries({ queryKey: ["market-monitor-prompt-traces", data.run_id] });
    },
  });
}
