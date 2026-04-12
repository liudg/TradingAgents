import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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
  fetchMarketMonitorPromptDetail,
  fetchMarketMonitorRun,
  fetchMarketMonitorRunEvidence,
  fetchMarketMonitorRunLogs,
  fetchMarketMonitorRunPrompts,
  fetchMarketMonitorRunStages,
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

export function useCreateMarketMonitorRun() {
  return useMutation({
    mutationFn: () => createMarketMonitorRun(),
  });
}

export function useMarketMonitorRun(runId?: string | null, enabled = true) {
  return useQuery({
    queryKey: ["market-monitor-run", runId],
    queryFn: () => fetchMarketMonitorRun(runId || ""),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return enabled && runId && status === "running" ? 2000 : false;
    },
    enabled: enabled && Boolean(runId),
  });
}

export function useMarketMonitorRunStages(
  runId?: string | null,
  enabled = true,
  shouldPoll = false,
) {
  return useQuery({
    queryKey: ["market-monitor-run-stages", runId],
    queryFn: () => fetchMarketMonitorRunStages(runId || ""),
    refetchInterval: enabled && shouldPoll ? 2000 : false,
    enabled: enabled && Boolean(runId),
  });
}

export function useMarketMonitorRunEvidence(
  runId?: string | null,
  enabled = true,
  shouldPoll = false,
) {
  return useQuery({
    queryKey: ["market-monitor-run-evidence", runId],
    queryFn: () => fetchMarketMonitorRunEvidence(runId || ""),
    refetchInterval: enabled && shouldPoll ? 2000 : false,
    enabled: enabled && Boolean(runId),
  });
}

export function useMarketMonitorRunLogs(
  runId?: string | null,
  enabled = true,
  shouldPoll = false,
) {
  return useQuery({
    queryKey: ["market-monitor-run-logs", runId],
    queryFn: () => fetchMarketMonitorRunLogs(runId || ""),
    refetchInterval: enabled && shouldPoll ? 2000 : false,
    enabled: enabled && Boolean(runId),
  });
}

export function useMarketMonitorRunPrompts(
  runId?: string | null,
  enabled = true,
  shouldPoll = false,
) {
  return useQuery({
    queryKey: ["market-monitor-run-prompts", runId],
    queryFn: () => fetchMarketMonitorRunPrompts(runId || ""),
    refetchInterval: enabled && shouldPoll ? 2000 : false,
    enabled: enabled && Boolean(runId),
  });
}

export function useMarketMonitorPromptDetail(
  runId?: string | null,
  promptId?: string | null,
  enabled = true,
  shouldPoll = false,
) {
  return useQuery({
    queryKey: ["market-monitor-prompt-detail", runId, promptId],
    queryFn: () => fetchMarketMonitorPromptDetail(runId || "", promptId || ""),
    refetchInterval: enabled && shouldPoll ? 2000 : false,
    enabled: enabled && Boolean(runId) && Boolean(promptId),
  });
}

export function useMarketMonitorRunSession() {
  const createRun = useCreateMarketMonitorRun();
  const [runId, setRunId] = useState<string | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    return window.sessionStorage.getItem("market-monitor-run-id");
  });

  useEffect(() => {
    if (runId || createRun.isPending || createRun.error) {
      return;
    }
    createRun.mutate(undefined, {
      onSuccess: (data) => {
        setRunId(data.run_id);
        if (typeof window !== "undefined") {
          window.sessionStorage.setItem("market-monitor-run-id", data.run_id);
        }
      },
    });
  }, [createRun, runId]);

  const runQuery = useMarketMonitorRun(runId, Boolean(runId));
  const shouldPollPipeline = Boolean(runId) && (runQuery.isLoading || runQuery.data?.status === "running");
  const stagesQuery = useMarketMonitorRunStages(runId, Boolean(runId), shouldPollPipeline);
  const evidenceQuery = useMarketMonitorRunEvidence(runId, Boolean(runId), shouldPollPipeline);
  const logsQuery = useMarketMonitorRunLogs(runId, Boolean(runId), shouldPollPipeline);
  const promptsQuery = useMarketMonitorRunPrompts(runId, Boolean(runId), shouldPollPipeline);
  const activePromptId = promptsQuery.data?.[0]?.prompt_id ?? null;
  const promptDetailQuery = useMarketMonitorPromptDetail(
    runId,
    activePromptId,
    Boolean(runId && activePromptId),
    shouldPollPipeline,
  );

  useEffect(() => {
    if (!runId || runQuery.data?.status === "running") {
      return;
    }
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.removeItem("market-monitor-run-id");
  }, [runId, runQuery.data?.status]);

  return {
    createRun,
    runId,
    runQuery,
    stagesQuery,
    evidenceQuery,
    logsQuery,
    promptsQuery,
    activePromptId,
    promptDetailQuery,
  };
}
