export const researchDepthOptions = [
  {
    label: "Shallow - Quick research, few debate and strategy discussion rounds",
    value: 1,
  },
  {
    label:
      "Medium - Middle ground, moderate debate rounds and strategy discussion",
    value: 3,
  },
  {
    label:
      "Deep - Comprehensive research, in depth debate and strategy discussion",
    value: 5,
  },
];

export const outputLanguageOptions = [
  { label: "Chinese", value: "Chinese" },
  { label: "English", value: "English" },
  { label: "Custom language", value: "custom" },
];

export const presetOutputLanguageValues = new Set(
  outputLanguageOptions
    .map((option) => option.value)
    .filter((value) => value !== "custom"),
);

export const backendUrlByProvider: Record<string, string> = {
  anthropic: "https://api.anthropic.com/",
  codex: "http://127.0.0.1:8317/v1",
  google: "https://generativelanguage.googleapis.com/v1",
  ollama: "http://localhost:11434/v1",
  openai: "https://api.openai.com/v1",
  openrouter: "https://openrouter.ai/api/v1",
  xai: "https://api.x.ai/v1",
};

export const openaiReasoningEffortOptions = [
  { label: "Medium (Default)", value: "medium" },
  { label: "High (More thorough)", value: "high" },
  { label: "Low (Faster)", value: "low" },
];

export const googleThinkingLevelOptions = [
  { label: "Enable Thinking (recommended)", value: "high" },
  { label: "Minimal/Disable Thinking", value: "minimal" },
];

export const anthropicEffortOptions = [
  { label: "High (recommended)", value: "high" },
  { label: "Medium (balanced)", value: "medium" },
  { label: "Low (faster, cheaper)", value: "low" },
];

export function resolveResearchDepth(
  maxDebateRounds?: number,
  maxRiskDiscussRounds?: number,
) {
  if (
    maxDebateRounds &&
    maxDebateRounds === maxRiskDiscussRounds &&
    researchDepthOptions.some((option) => option.value === maxDebateRounds)
  ) {
    return maxDebateRounds;
  }

  return undefined;
}

export function resolveBackendUrl(provider: string, explicitUrl?: string | null) {
  return explicitUrl || backendUrlByProvider[provider] || "";
}

export function resetProviderSpecificConfig(nextProvider: string) {
  return {
    anthropic_effort: nextProvider === "anthropic" ? "high" : "",
    codex_reasoning_effort: nextProvider === "codex" ? "medium" : "",
    google_thinking_level: nextProvider === "google" ? "high" : "",
    openai_reasoning_effort: nextProvider === "openai" ? "medium" : "",
  };
}

export function resolveOutputLanguageFields(outputLanguage?: string) {
  if (!outputLanguage || presetOutputLanguageValues.has(outputLanguage)) {
    return {
      output_language: outputLanguage || "Chinese",
      custom_output_language: "",
    };
  }

  return {
    output_language: "custom",
    custom_output_language: outputLanguage,
  };
}
