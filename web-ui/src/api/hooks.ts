import { useMutation, useQuery } from "@tanstack/react-query";

import {
  createAnalysisJob,
  fetchAnalysisJob,
  fetchAnalysisJobLogs,
  fetchAnalysisReport,
  fetchHistoricalReport,
  fetchHistoricalReports,
  fetchMetadataOptions,
} from "./client";
import { AnalysisJobRequest, JobStatus } from "./types";

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
