from __future__ import annotations

from datetime import date, datetime

from tradingagents.web.market_monitor_data import build_market_dataset
from tradingagents.web.market_monitor_cache import load_snapshot_cache, save_snapshot_cache
from tradingagents.web.market_monitor_schemas import (
    MarketEventRiskFlag,
    MarketExecutionCard,
    MarketExecutionSignalConfirmation,
    MarketHistoryPoint,
    MarketIndexEventRisk,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryResponse,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketPanicReversalCard,
    MarketScoreCard,
    MarketSourceCoverage,
    MarketStockEventRisk,
    MarketStyleAssetLayer,
    MarketStyleEffectiveness,
    MarketStyleSignal,
    MarketStyleTacticLayer,
)
from tradingagents.web.market_monitor_scoring import (
    LONG_TERM_ZONES,
    SHORT_TERM_ZONES,
    SYSTEM_RISK_ZONES,
    build_breadth_ratio,
    build_long_term_series,
    build_short_term_series,
    build_system_risk_series,
    score_asset_layer,
    score_tactic_layer,
    summarize_score,
)
from tradingagents.web.market_monitor_universe import get_market_monitor_universe


class MarketMonitorService:
    """Market monitor service using deterministic daily-data rules."""

    def __init__(self) -> None:
        self._snapshot_cache: dict[tuple[date, bool], tuple[datetime, MarketMonitorSnapshotResponse]] = {}
        self._history_cache: dict[tuple[date, int], tuple[datetime, MarketMonitorHistoryResponse]] = {}
        self._data_status_cache: dict[date, tuple[datetime, MarketMonitorDataStatusResponse]] = {}

    def get_snapshot(
        self, request: MarketMonitorSnapshotRequest
    ) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        cache_key = (as_of_date, request.force_refresh)
        if not request.force_refresh and cache_key in self._snapshot_cache:
            cached_at, cached_value = self._snapshot_cache[cache_key]
            if (datetime.now() - cached_at).total_seconds() < 300:
                return cached_value
        if not request.force_refresh:
            disk_cached = load_snapshot_cache(as_of_date)
            if disk_cached:
                response = MarketMonitorSnapshotResponse.model_validate(disk_cached)
                self._snapshot_cache[(as_of_date, False)] = (datetime.now(), response)
                return response
        universe = get_market_monitor_universe()
        event_risk_flag = self._build_event_risk_flag()

        try:
            dataset = build_market_dataset(universe, as_of_date)
            core_data = dataset["core"]
            required_symbols = ["SPY", "QQQ", "IWM"]
            missing_required = [
                symbol for symbol in required_symbols if core_data.get(symbol) is None or core_data[symbol].empty
            ]
            if missing_required:
                raise RuntimeError(f"missing required daily data: {', '.join(missing_required)}")
            breadth_ratio = build_breadth_ratio(dataset["nasdaq_100"])
            sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}

            long_term = summarize_score(
                build_long_term_series(core_data, breadth_ratio), LONG_TERM_ZONES
            )
            short_term = summarize_score(
                build_short_term_series(core_data, sector_data, breadth_ratio),
                SHORT_TERM_ZONES,
            )
            system_risk = summarize_score(
                build_system_risk_series(core_data, breadth_ratio),
                SYSTEM_RISK_ZONES,
            )
            style_effectiveness = self._build_style_effectiveness(core_data, dataset["nasdaq_100"])
            execution_card = self._build_execution_card(
                long_term["score"], short_term["score"], system_risk["score"], event_risk_flag, style_effectiveness
            )
            panic_card = self._build_panic_card(short_term["score"], system_risk["score"])
            coverage = MarketSourceCoverage(
                status="partial",
                data_freshness="daily_yfinance",
                degraded_factors=[
                    "分钟线尾盘确认",
                    "PCR绝对值",
                    "VIX期限结构",
                    "事件日历自动抓取",
                ],
                notes=[
                    "当前版本已接入真实日线数据。",
                    "panic 模块仍为日线简化版，分钟线与事件日历将在下一阶段补齐。",
                ],
            )
        except Exception as exc:
            long_term = {
                "score": 54.0,
                "zone": "试仓区",
                "delta_1d": 1.2,
                "delta_5d": -2.8,
                "slope_state": "缓慢恶化",
            }
            short_term = {
                "score": 47.0,
                "zone": "观察区",
                "delta_1d": -1.5,
                "delta_5d": -6.4,
                "slope_state": "缓慢恶化",
            }
            system_risk = {
                "score": 58.0,
                "zone": "压力区",
                "delta_1d": 3.4,
                "delta_5d": 10.2,
                "slope_state": "加速恶化",
            }
            style_effectiveness = self._build_style_effectiveness({}, {})
            execution_card = self._build_execution_card(
                long_term["score"], short_term["score"], system_risk["score"], event_risk_flag, style_effectiveness
            )
            panic_card = self._build_panic_card(short_term["score"], system_risk["score"])
            coverage = MarketSourceCoverage(
                status="degraded",
                data_freshness="fallback_placeholder",
                degraded_factors=["全部真实市场因子"],
                notes=[f"数据抓取失败，已回退到占位响应：{exc}"],
            )

        response = MarketMonitorSnapshotResponse(
            timestamp=datetime.now(),
            as_of_date=as_of_date,
            long_term_score=MarketScoreCard(
                score=long_term["score"],
                zone=long_term["zone"],
                delta_1d=long_term["delta_1d"],
                delta_5d=long_term["delta_5d"],
                slope_state=long_term["slope_state"],
                action=self._long_term_action(long_term["score"]),
            ),
            short_term_score=MarketScoreCard(
                score=short_term["score"],
                zone=short_term["zone"],
                delta_1d=short_term["delta_1d"],
                delta_5d=short_term["delta_5d"],
                slope_state=short_term["slope_state"],
                action=self._short_term_action(short_term["score"]),
            ),
            system_risk_score=MarketScoreCard(
                score=system_risk["score"],
                zone=system_risk["zone"],
                delta_1d=system_risk["delta_1d"],
                delta_5d=system_risk["delta_5d"],
                slope_state=system_risk["slope_state"],
                action=self._system_risk_action(system_risk["score"]),
            ),
            style_effectiveness=style_effectiveness,
            execution_card=execution_card,
            panic_reversal_score=panic_card,
            event_risk_flag=event_risk_flag,
            source_coverage=coverage,
        )
        self._snapshot_cache[(as_of_date, False)] = (datetime.now(), response)
        save_snapshot_cache(as_of_date, response.model_dump(mode="json"))
        return response

    def get_history(
        self, as_of_date: date, days: int = 10
    ) -> MarketMonitorHistoryResponse:
        cache_key = (as_of_date, days)
        if cache_key in self._history_cache:
            cached_at, cached_value = self._history_cache[cache_key]
            if (datetime.now() - cached_at).total_seconds() < 300:
                return cached_value
        points: list[MarketHistoryPoint] = []
        try:
            universe = get_market_monitor_universe()
            dataset = build_market_dataset(universe, as_of_date)
            core_data = dataset["core"]
            breadth_ratio = build_breadth_ratio(dataset["nasdaq_100"])
            sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}

            long_term_series = build_long_term_series(core_data, breadth_ratio).dropna().tail(days)
            short_term_series = build_short_term_series(core_data, sector_data, breadth_ratio).dropna().reindex(long_term_series.index).fillna(method="ffill")
            system_risk_series = build_system_risk_series(core_data, breadth_ratio).dropna().reindex(long_term_series.index).fillna(method="ffill")

            for dt in long_term_series.index:
                long_score = float(long_term_series.loc[dt])
                short_score = float(short_term_series.loc[dt]) if dt in short_term_series.index else 50.0
                risk_score = float(system_risk_series.loc[dt]) if dt in system_risk_series.index else 50.0
                points.append(
                    MarketHistoryPoint(
                        trade_date=dt.date(),
                        regime_label=self._regime_label(long_score, short_score, risk_score),
                        long_term_score=long_score,
                        short_term_score=short_score,
                        system_risk_score=risk_score,
                        panic_reversal_score=max(0.0, min(100.0, (100 - short_score) * 0.4 + risk_score * 0.6)),
                    )
                )
        except Exception:
            points = []
        response = MarketMonitorHistoryResponse(as_of_date=as_of_date, points=points)
        self._history_cache[cache_key] = (datetime.now(), response)
        return response

    def get_data_status(self, as_of_date: date) -> MarketMonitorDataStatusResponse:
        if as_of_date in self._data_status_cache:
            cached_at, cached_value = self._data_status_cache[as_of_date]
            if (datetime.now() - cached_at).total_seconds() < 300:
                return cached_value
        coverage = self.get_snapshot(
            MarketMonitorSnapshotRequest(as_of_date=as_of_date, force_refresh=False)
        ).source_coverage
        response = MarketMonitorDataStatusResponse(
            as_of_date=as_of_date,
            source_coverage=coverage,
            available_sources=["本地snapshot", "本地CSV缓存", "Yahoo日线", "Nasdaq 100 静态股票池", "FastAPI"],
            pending_sources=["分钟线", "PCR", "事件日历"],
        )
        self._data_status_cache[as_of_date] = (datetime.now(), response)
        return response

    def _build_event_risk_flag(self) -> MarketEventRiskFlag:
        return MarketEventRiskFlag(
            index_level=MarketIndexEventRisk(
                active=False,
                type=None,
                days_to_event=None,
                action_modifier=None,
            ),
            stock_level=MarketStockEventRisk(
                earnings_stocks=[],
                rule="个股级事件风控骨架已预留，后续会接入财报日历。",
            ),
        )

    def _build_style_effectiveness(
        self,
        core_data: dict,
        nasdaq_frames: dict,
    ) -> MarketStyleEffectiveness:
        if core_data and nasdaq_frames:
            tactic_scores = score_tactic_layer(nasdaq_frames)
            asset_scores = score_asset_layer(core_data)
        else:
            tactic_scores = {
                "trend_breakout": 32.0,
                "dip_buy": 64.0,
                "oversold_bounce": 58.0,
            }
            asset_scores = {
                "large_cap_tech": 38.0,
                "small_cap_momentum": 25.0,
                "defensive": 76.0,
                "energy_cyclical": 62.0,
                "financials": 44.0,
            }

        top_tactic = max(tactic_scores, key=tactic_scores.get)
        avoid_tactic = min(tactic_scores, key=tactic_scores.get)
        preferred_assets = sorted(asset_scores, key=asset_scores.get, reverse=True)[:2]
        avoid_assets = sorted(asset_scores, key=asset_scores.get)[:2]

        label_map = {
            "trend_breakout": "趋势突破",
            "dip_buy": "回调低吸",
            "oversold_bounce": "超跌反弹",
            "large_cap_tech": "大盘科技",
            "small_cap_momentum": "小盘高弹性",
            "defensive": "防御板块",
            "energy_cyclical": "能源/周期",
            "financials": "金融",
        }

        return MarketStyleEffectiveness(
            tactic_layer=MarketStyleTacticLayer(
                trend_breakout=MarketStyleSignal(score=tactic_scores["trend_breakout"], valid=tactic_scores["trend_breakout"] >= 55, delta_5d=0),
                dip_buy=MarketStyleSignal(score=tactic_scores["dip_buy"], valid=tactic_scores["dip_buy"] >= 55, delta_5d=0),
                oversold_bounce=MarketStyleSignal(score=tactic_scores["oversold_bounce"], valid=tactic_scores["oversold_bounce"] >= 55, delta_5d=0),
                top_tactic=label_map[top_tactic],
                avoid_tactic=label_map[avoid_tactic],
            ),
            asset_layer=MarketStyleAssetLayer(
                large_cap_tech=MarketStyleSignal(score=asset_scores["large_cap_tech"], preferred="large_cap_tech" in preferred_assets, delta_5d=0),
                small_cap_momentum=MarketStyleSignal(score=asset_scores["small_cap_momentum"], preferred="small_cap_momentum" in preferred_assets, delta_5d=0),
                defensive=MarketStyleSignal(score=asset_scores["defensive"], preferred="defensive" in preferred_assets, delta_5d=0),
                energy_cyclical=MarketStyleSignal(score=asset_scores["energy_cyclical"], preferred="energy_cyclical" in preferred_assets, delta_5d=0),
                financials=MarketStyleSignal(score=asset_scores["financials"], preferred="financials" in preferred_assets, delta_5d=0),
                preferred_assets=[label_map[item] for item in preferred_assets],
                avoid_assets=[label_map[item] for item in avoid_assets],
            ),
        )

    def _build_execution_card(
        self,
        long_score: float,
        short_score: float,
        system_risk_score: float,
        event_risk_flag: MarketEventRiskFlag,
        style_effectiveness: MarketStyleEffectiveness,
    ) -> MarketExecutionCard:
        regime_label = self._regime_label(long_score, short_score, system_risk_score)
        if regime_label == "绿灯":
            exposure = "70%-90%"
            conflict = "长短共振-主动进攻"
            risk_budget = "1.25R"
            chase = True
            dip_buy = True
            new_position = True
            overnight = True
            leverage = True
            cap = "12%"
        elif regime_label == "黄绿灯-Swing":
            exposure = "50%-70%"
            conflict = "长线中性+短线活跃+风险低"
            risk_budget = "1.0R"
            chase = True
            dip_buy = True
            new_position = True
            overnight = True
            leverage = False
            cap = "12%"
        elif regime_label == "黄灯":
            exposure = "40%-60%"
            conflict = "确认后进攻"
            risk_budget = "0.9R"
            chase = False
            dip_buy = True
            new_position = True
            overnight = True
            leverage = False
            cap = "10%"
        elif regime_label == "橙灯":
            exposure = "25%-45%"
            conflict = "防守为主"
            risk_budget = "0.75R"
            chase = False
            dip_buy = True
            new_position = True
            overnight = True
            leverage = False
            cap = "8%"
        else:
            exposure = "0%-20%"
            conflict = "净值保护"
            risk_budget = "0.25R"
            chase = False
            dip_buy = False
            new_position = False
            overnight = False
            leverage = False
            cap = "5%"

        return MarketExecutionCard(
            regime_label=regime_label,
            conflict_mode=conflict,
            total_exposure_range=exposure,
            new_position_allowed=new_position,
            chase_breakout_allowed=chase,
            dip_buy_allowed=dip_buy,
            overnight_allowed=overnight,
            leverage_allowed=leverage,
            single_position_cap=cap,
            daily_risk_budget=risk_budget,
            tactic_preference=f"{style_effectiveness.tactic_layer.top_tactic} > {style_effectiveness.tactic_layer.avoid_tactic}",
            preferred_assets=style_effectiveness.asset_layer.preferred_assets,
            avoid_assets=style_effectiveness.asset_layer.avoid_assets,
            signal_confirmation=MarketExecutionSignalConfirmation(
                current_regime_days=1,
                downgrade_unlock_in_days=2,
                note="当前版本使用真实日线分数，regime 延迟确认机制将在后续状态持久化后接入。",
            ),
            event_risk_flag=event_risk_flag,
        )

    def _build_panic_card(self, short_score: float, system_risk_score: float) -> MarketPanicReversalCard:
        panic_gate = short_score < 35 and system_risk_score >= 45
        early_gate = short_score < 25 and system_risk_score >= 60

        if not panic_gate:
            panic_extreme = 25.0
            selling_exhaustion = 20.0
            intraday_reversal = 15.0
            followthrough = 15.0
            score = 25.0
            state = "无信号"
            zone = "无信号"
            action = "当前不满足恐慌触发门槛，不应启动反转交易模块。"
        else:
            panic_extreme = max(35.0, min(100.0, 65 + (35 - short_score) * 0.9 + (system_risk_score - 45) * 0.7))
            selling_exhaustion = max(25.0, min(100.0, 25 + (system_risk_score - short_score) * 0.45))
            intraday_reversal = max(20.0, min(100.0, 15 + (35 - short_score) * 1.1))
            followthrough = max(20.0, min(100.0, 15 + (35 - short_score) * 0.8 + max(0.0, system_risk_score - 55) * 0.2))
            score = panic_extreme * 0.4 + selling_exhaustion * 0.3 + max(intraday_reversal, followthrough) * 0.3

        if panic_gate and (panic_extreme >= 80 or score >= 50):
            state = "panic_confirmed"
            zone = "一级试错" if score < 65 else "二级反弹"
            action = "短线恐慌反转进入可执行区，但当前仍是日线简化版，建议轻仓试错。"
        elif panic_gate and panic_extreme >= 35:
            state = "panic_watch"
            zone = "观察期"
            action = "恐慌已进入观察区，等待尾盘结构和次日延续确认。"

        return MarketPanicReversalCard(
            score=round(score, 1),
            zone=zone,
            state=state,
            panic_extreme_score=round(panic_extreme, 1),
            selling_exhaustion_score=round(selling_exhaustion, 1),
            intraday_reversal_score=round(intraday_reversal, 1),
            followthrough_confirmation_score=round(followthrough, 1),
            action=action,
            system_risk_override="系统风险高于80时，即使触发也应限制反弹仓位上限。",
            stop_loss="ATR×1.0",
            profit_rule="达1R兑现50%，余仓移止损至成本线",
            timeout_warning=False,
            days_held=0,
            early_entry_allowed=state == "panic_confirmed" and early_gate and intraday_reversal >= 60,
        )

    def _regime_label(self, long_score: float, short_score: float, system_risk_score: float) -> str:
        if system_risk_score > 70 or long_score < 35:
            return "红灯"
        if 45 <= long_score < 65 and short_score >= 60 and system_risk_score <= 35:
            return "黄绿灯-Swing"
        if long_score >= 65 and short_score >= 55 and system_risk_score <= 35:
            return "绿灯"
        if long_score >= 50 and short_score >= 45 and system_risk_score <= 50:
            return "黄灯"
        return "橙灯"

    def _long_term_action(self, score: float) -> str:
        if score >= 80:
            return "强趋势环境，允许趋势型重仓。"
        if score >= 65:
            return "中期趋势健康，允许顺势增配。"
        if score >= 50:
            return "中期处于试仓区，宜分批建仓。"
        if score >= 35:
            return "长线环境偏谨慎，仓位应控制在中低区间。"
        return "长线环境防守优先，尽量避免趋势重仓。"

    def _short_term_action(self, score: float) -> str:
        if score >= 80:
            return "短线高胜率区，可积极参与但仍要控风控。"
        if score >= 65:
            return "短线活跃，允许提高交易频率。"
        if score >= 50:
            return "短线可做，优先低吸和确认后突破。"
        if score >= 35:
            return "短线观察为主，不主动进攻。"
        return "短线弱势，避免追涨和高波动隔夜。"

    def _system_risk_action(self, score: float) -> str:
        if score >= 80:
            return "系统性危机区，优先保现金和对冲。"
        if score >= 60:
            return "高压区，禁杠杆并显著压低总仓。"
        if score >= 45:
            return "压力区，减少追高并收紧单票风险。"
        if score >= 20:
            return "风险处于正常区，维持常规风控。"
        return "系统风险较低，可按主趋势卡执行。"
