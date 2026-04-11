import { describe, expect, it } from "vitest";

import {
  MARKET_MONITOR_CARD_HELP,
  type MarketMonitorCardHelpKey,
} from "./marketMonitorCardHelp";

const REQUIRED_KEYS: MarketMonitorCardHelpKey[] = [
  "panic_module",
  "long_term_score",
  "short_term_score",
  "system_risk_score",
  "model_overlay",
  "rule_snapshot",
];

describe("marketMonitorCardHelp", () => {
  it("provides help content for every supported market monitor card", () => {
    expect(Object.keys(MARKET_MONITOR_CARD_HELP).sort()).toEqual(
      [...REQUIRED_KEYS].sort(),
    );

    for (const key of REQUIRED_KEYS) {
      expect(MARKET_MONITOR_CARD_HELP[key].title.length).toBeGreaterThan(0);
      expect(MARKET_MONITOR_CARD_HELP[key].purpose.length).toBeGreaterThan(0);
      expect(MARKET_MONITOR_CARD_HELP[key].rules.length).toBeGreaterThan(0);
    }
  });
});
