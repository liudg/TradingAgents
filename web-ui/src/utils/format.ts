import dayjs from "dayjs";

import { ApiError, JobStatus } from "../api/types";

const statusTextMap: Record<JobStatus, string> = {
  pending: "等待执行",
  running: "分析中",
  completed: "已完成",
  failed: "执行失败",
};

const statusColorMap: Record<JobStatus, string> = {
  pending: "default",
  running: "processing",
  completed: "success",
  failed: "error",
};

export function getStatusText(status: JobStatus) {
  return statusTextMap[status] ?? status;
}

export function getStatusColor(status: JobStatus) {
  return statusColorMap[status] ?? "default";
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}

export function formatElapsedTime(startedAt?: string | null, finishedAt?: string | null) {
  if (!startedAt) {
    return "未开始";
  }

  const startTime = dayjs(startedAt);
  const endTime = finishedAt ? dayjs(finishedAt) : dayjs();
  const totalSeconds = Math.max(0, endTime.diff(startTime, "second"));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export function extractErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 422) {
      return `请求参数校验失败：${error.detail}`;
    }
    return `接口错误 ${error.status}：${error.detail}`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "请求失败，请稍后重试";
}
