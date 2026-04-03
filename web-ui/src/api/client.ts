import {
  AnalysisJobCreateResponse,
  AnalysisJobLogEntry,
  AnalysisJobRequest,
  AnalysisJobResponse,
  ApiError,
  HistoricalReportDetail,
  HistoricalReportSummary,
  MetadataOptionsResponse,
} from "./types";

async function parseError(response: Response): Promise<never> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json()) as { detail?: unknown };
    const detail =
      typeof payload.detail === "string"
        ? payload.detail
        : JSON.stringify(payload.detail ?? payload);
    throw new ApiError(response.status, detail);
  }

  const text = await response.text();
  throw new ApiError(response.status, text || `请求失败：${response.status}`);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    return parseError(response);
  }

  return (await response.json()) as T;
}

export async function fetchMetadataOptions() {
  return requestJson<MetadataOptionsResponse>("/api/metadata/options");
}

export async function createAnalysisJob(payload: AnalysisJobRequest) {
  return requestJson<AnalysisJobCreateResponse>("/api/analysis-jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchAnalysisJob(jobId: string) {
  return requestJson<AnalysisJobResponse>(`/api/analysis-jobs/${jobId}`);
}

export async function fetchAnalysisJobLogs(jobId: string) {
  return requestJson<AnalysisJobLogEntry[]>(
    `/api/analysis-jobs/${jobId}/logs`,
  );
}

export async function fetchAnalysisReport(jobId: string) {
  const response = await fetch(`/api/analysis-jobs/${jobId}/report`);
  if (!response.ok) {
    return parseError(response);
  }
  return response.text();
}

export async function fetchHistoricalReports() {
  return requestJson<HistoricalReportSummary[]>("/api/historical-reports");
}

export async function fetchHistoricalReport(jobId: string) {
  return requestJson<HistoricalReportDetail>(
    `/api/historical-reports/${jobId}`,
  );
}
