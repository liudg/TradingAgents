import {
  AnalysisJobCreateResponse,
  AnalysisJobLogEntry,
  AnalysisJobRequest,
  AnalysisJobResponse,
  ApiError,
  BacktestJobCreateResponse,
  BacktestJobRequest,
  BacktestJobResponse,
  HistoricalBacktestDetail,
  HistoricalBacktestSummary,
  HistoricalReportDetail,
  HistoricalReportSummary,
  MarketMonitorDataStatusResponse,
  MarketMonitorHistoryResponse,
  MarketMonitorSnapshotResponse,
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

export async function createBacktestJob(payload: BacktestJobRequest) {
  return requestJson<BacktestJobCreateResponse>("/api/backtest-jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchBacktestJob(jobId: string) {
  return requestJson<BacktestJobResponse>(`/api/backtest-jobs/${jobId}`);
}

export async function fetchBacktestJobLogs(jobId: string) {
  return requestJson<AnalysisJobLogEntry[]>(`/api/backtest-jobs/${jobId}/logs`);
}

export async function fetchHistoricalBacktests() {
  return requestJson<HistoricalBacktestSummary[]>("/api/historical-backtests");
}

export async function fetchHistoricalBacktest(jobId: string) {
  return requestJson<HistoricalBacktestDetail>(
    `/api/historical-backtests/${jobId}`,
  );
}

export async function fetchMarketMonitorSnapshot(
  asOfDate?: string,
  forceRefresh = false,
) {
  const params = new URLSearchParams();
  if (asOfDate) params.set("as_of_date", asOfDate);
  if (forceRefresh) params.set("force_refresh", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<MarketMonitorSnapshotResponse>(`/api/market-monitor/snapshot${suffix}`);
}

export async function fetchMarketMonitorHistory(
  days = 20,
  asOfDate?: string,
  forceRefresh = false,
) {
  const params = new URLSearchParams();
  params.set("days", String(days));
  if (asOfDate) params.set("as_of_date", asOfDate);
  if (forceRefresh) params.set("force_refresh", "true");
  return requestJson<MarketMonitorHistoryResponse>(`/api/market-monitor/history?${params.toString()}`);
}

export async function fetchMarketMonitorDataStatus(
  asOfDate?: string,
  forceRefresh = false,
) {
  const params = new URLSearchParams();
  if (asOfDate) params.set("as_of_date", asOfDate);
  if (forceRefresh) params.set("force_refresh", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<MarketMonitorDataStatusResponse>(`/api/market-monitor/data-status${suffix}`);
}
