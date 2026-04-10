import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.schemas import MarketMonitorModelOverlay, MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor.data import _expected_market_close_date, _is_cache_usable
from tradingagents.web.market_monitor.service import MarketMonitorService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.4 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([1_000_000 + i * 100 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(18, days=320)
    return {"core": core}


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
        friday_frame = _make_frame(100, days=120)

        self.assertFalse(_is_cache_usable(friday_frame, date(2026, 4, 13), 60))
        self.assertTrue(_is_cache_usable(friday_frame, date(2026, 4, 12), 60))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 12)), pd.Timestamp("2026-04-10"))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 3)), pd.Timestamp("2026-04-02"))

    def test_snapshot_uses_cache_between_requests(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()
        cached_payload: dict[str, object] = {}

        def fake_load_snapshot_cache(_as_of_date: date) -> dict[str, object] | None:
            return cached_payload or None

        def fake_save_snapshot_cache(_as_of_date: date, payload: dict[str, object]) -> None:
            cached_payload.clear()
            cached_payload.update(payload)

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ) as mocked_dataset, patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["test"]),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            side_effect=fake_load_snapshot_cache,
        ) as mocked_load_cache, patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
            side_effect=fake_save_snapshot_cache,
        ):
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(mocked_dataset.call_count, 1)
        self.assertEqual(mocked_load_cache.call_count, 2)

    def test_snapshot_force_refresh_bypasses_snapshot_cache(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            side_effect=[dataset, dataset],
        ) as mocked_dataset, patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["test"]),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
        ) as mocked_load_cache, patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ):
            service.get_snapshot(
                MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10), force_refresh=True)
            )
            service.get_snapshot(
                MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10), force_refresh=True)
            )

        self.assertEqual(mocked_dataset.call_count, 2)
        mocked_load_cache.assert_not_called()

    def test_snapshot_error_overlay_is_not_returned_from_cache(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()
        error_overlay = MarketMonitorModelOverlay(status="error", notes=["transient"])

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ) as mocked_dataset, patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["ok"]),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value={
                "timestamp": "2026-04-10T16:00:00",
                "as_of_date": "2026-04-10",
                "rule_snapshot": {
                    "ready": False,
                    "base_event_risk_flag": {
                        "index_level": {"active": False},
                        "stock_level": {"earnings_stocks": [], "rule": "none"},
                    },
                    "source_coverage": {
                        "status": "partial",
                        "data_freshness": "live_request_yfinance_daily",
                        "degraded_factors": [],
                        "notes": [],
                    },
                    "missing_inputs": [],
                    "degraded_factors": [],
                    "key_indicators": {},
                },
                "model_overlay": error_overlay.model_dump(mode="json"),
                "final_execution_card": None,
            },
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ) as mocked_save_cache:
            response = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(mocked_dataset.call_count, 1)
        self.assertEqual(response.model_overlay.status, "skipped")
        mocked_save_cache.assert_called_once()

    def test_snapshot_stale_live_cache_is_rebuilt(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()
        today = date.today()
        stale_timestamp = (datetime.now() - timedelta(minutes=10)).isoformat()

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ) as mocked_dataset, patch.object(
            service,
            "_is_live_market_date",
            return_value=True,
        ), patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["rebuilt"]),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value={
                "timestamp": stale_timestamp,
                "as_of_date": today.isoformat(),
                "rule_snapshot": {
                    "ready": True,
                    "long_term_score": {
                        "score": 70,
                        "zone": "green",
                        "delta_1d": 1,
                        "delta_5d": 2,
                        "slope_state": "up",
                        "action": "cached",
                    },
                    "short_term_score": {
                        "score": 68,
                        "zone": "green",
                        "delta_1d": 1,
                        "delta_5d": 2,
                        "slope_state": "up",
                        "action": "cached",
                    },
                    "system_risk_score": {
                        "score": 20,
                        "zone": "green",
                        "delta_1d": -1,
                        "delta_5d": -2,
                        "slope_state": "down",
                        "action": "cached",
                    },
                    "style_effectiveness": {
                        "tactic_layer": {
                            "trend_breakout": {"score": 70, "valid": True, "delta_5d": 0},
                            "dip_buy": {"score": 60, "valid": True, "delta_5d": 0},
                            "oversold_bounce": {"score": 40, "valid": False, "delta_5d": 0},
                            "top_tactic": "trend_breakout",
                            "avoid_tactic": "oversold_bounce",
                        },
                        "asset_layer": {
                            "large_cap_tech": {"score": 75, "preferred": True, "delta_5d": 0},
                            "small_cap_momentum": {"score": 60, "preferred": True, "delta_5d": 0},
                            "defensive": {"score": 45, "preferred": False, "delta_5d": 0},
                            "energy_cyclical": {"score": 40, "preferred": False, "delta_5d": 0},
                            "financials": {"score": 42, "preferred": False, "delta_5d": 0},
                            "preferred_assets": ["large_cap_tech", "small_cap_momentum"],
                            "avoid_assets": ["energy_cyclical", "financials"],
                        },
                    },
                    "panic_reversal_score": {
                        "score": 25,
                        "zone": "inactive",
                        "state": "none",
                        "panic_extreme_score": 25,
                        "selling_exhaustion_score": 20,
                        "intraday_reversal_score": 15,
                        "followthrough_confirmation_score": 15,
                        "action": "cached",
                        "stop_loss": "ATR x 1.0",
                        "profit_rule": "Take 50% at 1R and trail the remainder at breakeven.",
                        "timeout_warning": False,
                        "days_held": 0,
                        "early_entry_allowed": False,
                    },
                    "base_regime_label": "green",
                    "base_execution_card": {
                        "regime_label": "green",
                        "conflict_mode": "trend_and_tape_aligned",
                        "total_exposure_range": "70%-90%",
                        "new_position_allowed": True,
                        "chase_breakout_allowed": True,
                        "dip_buy_allowed": True,
                        "overnight_allowed": True,
                        "leverage_allowed": True,
                        "single_position_cap": "12%",
                        "daily_risk_budget": "1.25R",
                        "tactic_preference": "trend_breakout>oversold_bounce",
                        "preferred_assets": ["large_cap_tech", "small_cap_momentum"],
                        "avoid_assets": ["energy_cyclical", "financials"],
                        "signal_confirmation": {
                            "current_regime_days": 1,
                            "downgrade_unlock_in_days": 2,
                            "note": "cached",
                        },
                        "event_risk_flag": {
                            "index_level": {"active": False},
                            "stock_level": {"earnings_stocks": [], "rule": "none"},
                        },
                        "summary": "cached",
                    },
                    "base_event_risk_flag": {
                        "index_level": {"active": False},
                        "stock_level": {"earnings_stocks": [], "rule": "none"},
                    },
                    "source_coverage": {
                        "status": "partial",
                        "data_freshness": "live_request_yfinance_daily",
                        "degraded_factors": [],
                        "notes": [],
                    },
                    "missing_inputs": [],
                    "degraded_factors": [],
                    "key_indicators": {},
                },
                "model_overlay": {"status": "skipped", "notes": ["cached"]},
                "final_execution_card": {
                    "regime_label": "green",
                    "conflict_mode": "trend_and_tape_aligned",
                    "total_exposure_range": "70%-90%",
                    "new_position_allowed": True,
                    "chase_breakout_allowed": True,
                    "dip_buy_allowed": True,
                    "overnight_allowed": True,
                    "leverage_allowed": True,
                    "single_position_cap": "12%",
                    "daily_risk_budget": "1.25R",
                    "tactic_preference": "trend_breakout>oversold_bounce",
                    "preferred_assets": ["large_cap_tech", "small_cap_momentum"],
                    "avoid_assets": ["energy_cyclical", "financials"],
                    "signal_confirmation": {
                        "current_regime_days": 1,
                        "downgrade_unlock_in_days": 2,
                        "note": "cached",
                    },
                    "event_risk_flag": {
                        "index_level": {"active": False},
                        "stock_level": {"earnings_stocks": [], "rule": "none"},
                    },
                    "summary": "cached",
                },
            },
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ):
            response = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=today))

        self.assertEqual(mocked_dataset.call_count, 1)
        self.assertEqual(response.model_overlay.notes, ["rebuilt"])

    def test_failed_force_refresh_does_not_overwrite_good_dataset_cache(self) -> None:
        service = MarketMonitorService()
        good_dataset = _complete_dataset()
        bad_dataset = {"core": {**good_dataset["core"], "SPY": pd.DataFrame()}}

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            side_effect=[good_dataset, bad_dataset],
        ) as mocked_dataset, patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ):
            first = service.get_history(date(2026, 4, 10), days=3)
            forced = service.get_history(date(2026, 4, 10), days=3)
            service._get_dataset(get_market_monitor_universe(), date(2026, 4, 10), force_refresh=True)
            second = service.get_history(date(2026, 4, 10), days=3)

        self.assertEqual(len(first.points), 3)
        self.assertEqual(len(forced.points), 3)
        self.assertEqual(len(second.points), 3)
        self.assertEqual(mocked_dataset.call_count, 2)

    def test_history_and_data_status_reuse_dataset_for_same_date(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ) as mocked_dataset, patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ):
            service.get_history(date(2026, 4, 10), days=5)
            service.get_data_status(date(2026, 4, 10))

        self.assertEqual(mocked_dataset.call_count, 1)


if __name__ == "__main__":
    unittest.main()
