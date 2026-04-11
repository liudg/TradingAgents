import { describe, expect, it } from "vitest";

import {
  MARKET_MONITOR_CARD_HELP,
  type MarketMonitorCardHelpKey,
} from "./marketMonitorCardHelp";

const REQUIRED_KEYS: MarketMonitorCardHelpKey[] = [
  "long_term_card",
  "short_term_card",
  "system_risk_card",
  "execution_card",
  "event_risk_card",
  "panic_card",
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
