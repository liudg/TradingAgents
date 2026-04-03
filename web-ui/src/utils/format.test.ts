import { describe, expect, it } from "vitest";

import { ApiError } from "../api/types";
import { extractErrorMessage, formatDateTime, getStatusText } from "./format";

describe("format helpers", () => {
  it("maps job status to Chinese text", () => {
    expect(getStatusText("running")).toBe("分析中");
    expect(getStatusText("completed")).toBe("已完成");
  });

  it("formats datetime strings", () => {
    expect(formatDateTime("2026-04-03T08:30:00")).toBe("2026-04-03 08:30:00");
    expect(formatDateTime(null)).toBe("-");
  });

  it("extracts API validation errors", () => {
    const error = new ApiError(422, "ticker field required");
    expect(extractErrorMessage(error)).toContain("请求参数校验失败");
    expect(extractErrorMessage(error)).toContain("ticker field required");
  });
});
