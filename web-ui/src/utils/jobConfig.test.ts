import { describe, expect, it } from "vitest";

import {
  resolveBackendUrl,
  resolveResearchDepth,
  resetProviderSpecificConfig,
} from "./jobConfig";

describe("jobConfig", () => {
  it("maps equal debate/risk rounds to CLI research depth values", () => {
    expect(resolveResearchDepth(1, 1)).toBe(1);
    expect(resolveResearchDepth(3, 3)).toBe(3);
    expect(resolveResearchDepth(5, 5)).toBe(5);
    expect(resolveResearchDepth(2, 3)).toBeUndefined();
    expect(resolveResearchDepth(2, 2)).toBeUndefined();
  });

  it("resolves backend URL from explicit override or provider default", () => {
    expect(resolveBackendUrl("openai", "https://proxy.example/v1")).toBe(
      "https://proxy.example/v1",
    );
    expect(resolveBackendUrl("google", null)).toBe(
      "https://generativelanguage.googleapis.com/v1",
    );
  });

  it("keeps only the selected provider specific effort field", () => {
    expect(resetProviderSpecificConfig("openai")).toEqual({
      anthropic_effort: "",
      google_thinking_level: "",
      openai_reasoning_effort: "medium",
    });
    expect(resetProviderSpecificConfig("google")).toEqual({
      anthropic_effort: "",
      google_thinking_level: "high",
      openai_reasoning_effort: "",
    });
  });
});
