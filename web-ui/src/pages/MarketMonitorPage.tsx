import {
  Alert,
  Card,
  Col,
  Descriptions,
  List,
  Progress,
  Result,
  Row,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";

import {
  useMarketMonitorHistory,
  useMarketMonitorSnapshot,
} from "../api/hooks";
import { MarketRegimeLabel, MarketScoreCard } from "../api/types";
import { extractErrorMessage, formatDateTime } from "../utils/format";

const regimeLabelMap: Record<MarketRegimeLabel, string> = {
  green: "绿色",
  yellow: "黄色",
  yellow_green_swing: "黄绿震荡",
  orange: "橙色",
  red: "红色",
};

function scoreColor(score: number) {
  if (score >= 65) return "#389e0d";
  if (score >= 50) return "#d48806";
  return "#cf1322";
}

function regimeTagColor(label?: string | null) {
  if (label === "green") return "success";
  if (label === "yellow" || label === "yellow_green_swing") return "warning";
  if (label === "orange") return "orange";
  return "error";
}

function displayRegime(label?: string | null) {
  if (!label) return "暂无";
  return regimeLabelMap[label as MarketRegimeLabel] ?? label;
}

function displayCoverageStatus(status?: string | null) {
  if (status === "full") return "完整";
  if (status === "partial") return "部分可用";
  if (status === "degraded") return "降级";
  return status ?? "暂无";
}

function displayOverlayStatus(status?: string | null) {
  if (status === "applied") return "已应用";
  if (status === "skipped") return "已跳过";
  if (status === "error") return "异常";
  return status ?? "暂无";
}

function displayPanicState(state?: string | null) {
  if (state === "none") return "无信号";
  if (state === "watch") return "观察中";
  if (state === "confirmed") return "已确认";
  return state ?? "暂无";
}

function ScoreCardBlock(props: { title: string; card?: MarketScoreCard | null }) {
  if (!props.card) {
    return (
      <Card className="section-card market-score-card" title={props.title}>
        <Alert type="warning" showIcon message="当前请求暂无规则评分。" />
      </Card>
    );
  }

  return (
    <Card className="section-card market-score-card" title={props.title}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Statistic
          title="评分"
          value={props.card.score}
          precision={1}
          valueStyle={{ color: scoreColor(props.card.score) }}
        />
        <Space wrap>
          <Tag color="blue">{props.card.zone}</Tag>
          <Tag>1D {props.card.delta_1d >= 0 ? "+" : ""}{props.card.delta_1d.toFixed(1)}</Tag>
          <Tag>5D {props.card.delta_5d >= 0 ? "+" : ""}{props.card.delta_5d.toFixed(1)}</Tag>
          <Tag>{props.card.slope_state}</Tag>
        </Space>
        <Progress
          percent={Math.round(props.card.score)}
          showInfo={false}
          strokeColor={scoreColor(props.card.score)}
        />
        <Typography.Text>{props.card.action}</Typography.Text>
      </Space>
    </Card>
  );
}

export function MarketMonitorPage() {
  const [historyEnabled, setHistoryEnabled] = useState(false);
  const snapshotQuery = useMarketMonitorSnapshot();
  const historyQuery = useMarketMonitorHistory(historyEnabled);
  const ruleSnapshotReady = snapshotQuery.data?.rule_snapshot.ready;
  const overlayStatus = snapshotQuery.data?.model_overlay.status;
  const topStatus = useMemo(() => {
    if (!ruleSnapshotReady) return "规则快照不完整";
    if (overlayStatus === "applied") return "规则快照 + 模型叠加";
    return "仅规则快照";
  }, [overlayStatus, ruleSnapshotReady]);

  useEffect(() => {
    if (snapshotQuery.data?.rule_snapshot.ready) {
      setHistoryEnabled(true);
    }
  }, [snapshotQuery.data?.rule_snapshot.ready]);

  if (snapshotQuery.isLoading) {
    return (
      <Card className="page-card" title="市场监控">
        <Skeleton active paragraph={{ rows: 14 }} />
      </Card>
    );
  }

  if (snapshotQuery.isError || !snapshotQuery.data) {
    return (
      <Result
        status="error"
        title="市场监控加载失败"
        subTitle={extractErrorMessage(snapshotQuery.error)}
      />
    );
  }

  const snapshot = snapshotQuery.data;
  const history = historyEnabled ? historyQuery.data : undefined;
  const ruleSnapshot = snapshot.rule_snapshot;
  const overlay = snapshot.model_overlay;
  const finalExecutionCard = snapshot.final_execution_card;
  const sourceCoverage = ruleSnapshot.source_coverage;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>市场监控</span>
            <Tag color={regimeTagColor(finalExecutionCard?.regime_label ?? ruleSnapshot.base_regime_label)}>
              {displayRegime(finalExecutionCard?.regime_label ?? ruleSnapshot.base_regime_label)}
            </Tag>
            <Tag>{topStatus}</Tag>
          </Space>
        }
        extra={
          <a
            className="page-card-extra-button ant-btn ant-btn-default"
            onClick={(event) => {
              event.preventDefault();
              snapshotQuery.refetch();
              if (historyEnabled) {
                historyQuery.refetch();
              }
            }}
          >
            <ReloadOutlined /> 刷新
          </a>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="processing">更新时间 {formatDateTime(snapshot.timestamp)}</Tag>
            <Tag color={sourceCoverage.status === "full" ? "success" : sourceCoverage.status === "partial" ? "warning" : "error"}>
              覆盖度 {displayCoverageStatus(sourceCoverage.status)}
            </Tag>
            <Tag>交易日 {snapshot.as_of_date}</Tag>
            <Tag>模型叠加 {displayOverlayStatus(overlay.status)}</Tag>
          </Space>
          {!ruleSnapshot.ready ? (
            <Alert
              type="warning"
              showIcon
              message="规则快照不完整"
              description={
                ruleSnapshot.missing_inputs.length
                  ? `缺失输入：${ruleSnapshot.missing_inputs.join(", ")}`
                  : "必需输入尚未完整。"
              }
            />
          ) : null}
          {sourceCoverage.notes.length ? (
            <Alert
              type="info"
              showIcon
              message="数据覆盖说明"
              description={sourceCoverage.notes.join(" ")}
            />
          ) : null}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="长期规则卡" card={ruleSnapshot.long_term_score} />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="短期规则卡" card={ruleSnapshot.short_term_score} />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="系统风险规则卡" card={ruleSnapshot.system_risk_score} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="规则快照">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={regimeTagColor(ruleSnapshot.base_regime_label)}>
                  基础市场状态 {displayRegime(ruleSnapshot.base_regime_label)}
                </Tag>
                <Tag>就绪 {ruleSnapshot.ready ? "是" : "否"}</Tag>
              </Space>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="仓位暴露">
                  {ruleSnapshot.base_execution_card?.total_exposure_range ?? "暂无"}
                </Descriptions.Item>
                <Descriptions.Item label="冲突模式">
                  {ruleSnapshot.base_execution_card?.conflict_mode ?? "暂无"}
                </Descriptions.Item>
                <Descriptions.Item label="风险预算">
                  {ruleSnapshot.base_execution_card?.daily_risk_budget ?? "暂无"}
                </Descriptions.Item>
                <Descriptions.Item label="规则摘要">
                  {ruleSnapshot.base_execution_card?.summary ?? "暂无"}
                </Descriptions.Item>
              </Descriptions>
              <Typography.Text strong>缺失输入</Typography.Text>
              <Space wrap>
                {ruleSnapshot.missing_inputs.length ? (
                  ruleSnapshot.missing_inputs.map((item) => <Tag key={item}>{item}</Tag>)
                ) : (
                  <Tag color="success">无</Tag>
                )}
              </Space>
              <Typography.Text strong>降级因子</Typography.Text>
              <List
                size="small"
                dataSource={ruleSnapshot.degraded_factors}
                locale={{ emptyText: "无" }}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="模型叠加">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={overlay.status === "applied" ? "success" : overlay.status === "error" ? "error" : "default"}>
                  {displayOverlayStatus(overlay.status)}
                </Tag>
                <Tag>置信度 {overlay.model_confidence ?? "暂无"}</Tag>
                <Tag>状态覆盖 {displayRegime(overlay.regime_override)}</Tag>
              </Space>
              <Typography.Text>{overlay.market_narrative || "暂无市场叙述。"}</Typography.Text>
              <Typography.Text>{overlay.risk_narrative || "暂无风险叙述。"}</Typography.Text>
              <Typography.Text>{overlay.panic_narrative || "暂无恐慌叙述。"}</Typography.Text>
              <Typography.Text strong>证据来源</Typography.Text>
              <Space wrap>
                {overlay.evidence_sources.length ? (
                  overlay.evidence_sources.map((item) => <Tag key={item}>{item}</Tag>)
                ) : (
                  <Tag>无</Tag>
                )}
              </Space>
              {overlay.notes.length ? (
                <Alert type="info" showIcon message={overlay.notes.join(" ")} />
              ) : null}
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card className="page-card" title="最终决策">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={regimeTagColor(finalExecutionCard?.regime_label)}>
                  最终市场状态 {displayRegime(finalExecutionCard?.regime_label)}
                </Tag>
                <Tag>仓位暴露 {finalExecutionCard?.total_exposure_range ?? "暂无"}</Tag>
                <Tag>风险预算 {finalExecutionCard?.daily_risk_budget ?? "暂无"}</Tag>
              </Space>
              <Typography.Text>{finalExecutionCard?.summary ?? "暂无最终动作摘要。"}</Typography.Text>
              <Space wrap>
                <Tag color={finalExecutionCard?.new_position_allowed ? "success" : "error"}>
                  新开仓 {finalExecutionCard?.new_position_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={finalExecutionCard?.chase_breakout_allowed ? "success" : "error"}>
                  追突破 {finalExecutionCard?.chase_breakout_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={finalExecutionCard?.dip_buy_allowed ? "success" : "error"}>
                  低吸 {finalExecutionCard?.dip_buy_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={finalExecutionCard?.overnight_allowed ? "success" : "error"}>
                  隔夜持仓 {finalExecutionCard?.overnight_allowed ? "允许" : "禁止"}
                </Tag>
              </Space>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="事件风险">
                  {finalExecutionCard?.event_risk_flag.index_level.active
                    ? finalExecutionCard.event_risk_flag.index_level.type ?? "启用"
                    : "未启用"}
                </Descriptions.Item>
                <Descriptions.Item label="个股事件规则">
                  {finalExecutionCard?.event_risk_flag.stock_level.rule ?? "暂无"}
                </Descriptions.Item>
              </Descriptions>
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="page-card" title="恐慌模块">
            {ruleSnapshot.panic_reversal_score ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space wrap>
                  <Tag>{displayPanicState(ruleSnapshot.panic_reversal_score.state)}</Tag>
                  <Tag>{ruleSnapshot.panic_reversal_score.zone}</Tag>
                  <Tag>
                    提前入场 {ruleSnapshot.panic_reversal_score.early_entry_allowed ? "允许" : "关闭"}
                  </Tag>
                </Space>
                <Statistic
                  title="评分"
                  value={ruleSnapshot.panic_reversal_score.score}
                  precision={1}
                />
                <Progress percent={Math.round(ruleSnapshot.panic_reversal_score.score)} />
                <Typography.Text>{ruleSnapshot.panic_reversal_score.action}</Typography.Text>
                <Typography.Text type="secondary">
                  止损 {ruleSnapshot.panic_reversal_score.stop_loss} | 止盈 {ruleSnapshot.panic_reversal_score.profit_rule}
                </Typography.Text>
              </Space>
            ) : (
              <Alert type="warning" showIcon message="规则快照不完整时，恐慌模块不可用。" />
            )}
          </Card>
        </Col>
      </Row>

      <Card className="page-card" title="数据状态">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Tag color={sourceCoverage.status === "full" ? "success" : sourceCoverage.status === "partial" ? "warning" : "error"}>
            {displayCoverageStatus(sourceCoverage.status)}
          </Tag>
          <Typography.Text strong>可用数据源</Typography.Text>
          <Space wrap>
            {["live_yfinance_daily", "etf_index_proxy_universe", "fastapi_market_monitor"].map((item) => (
              <Tag key={item}>{item}</Tag>
            ))}
          </Space>
          <Typography.Text strong>待接入数据源</Typography.Text>
          <Space wrap>
            {[
              "intraday_panic_confirmation",
              "put_call_ratio",
              "vix_term_structure",
              "calendar_events",
              "web_search_overlay",
            ].map((item) => (
              <Tag key={item}>{item}</Tag>
            ))}
          </Space>
        </Space>
      </Card>

      <Card
        className="page-card"
        title="近期历史"
        extra={
          !historyEnabled ? (
            <a
              className="page-card-extra-button ant-btn ant-btn-default"
              onClick={(event) => {
                event.preventDefault();
                setHistoryEnabled(true);
                historyQuery.refetch();
              }}
            >
              加载历史
            </a>
          ) : undefined
        }
      >
        <List
          dataSource={historyEnabled ? history?.points || [] : []}
          locale={{ emptyText: historyEnabled ? "暂无历史数据" : "历史数据按需加载，以避免重复拉取实时数据。" }}
          renderItem={(item) => (
            <List.Item>
              <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
                <Space wrap>
                  <Typography.Text strong>{item.trade_date}</Typography.Text>
                  <Tag color={regimeTagColor(item.regime_label)}>{displayRegime(item.regime_label)}</Tag>
                </Space>
                <Space wrap>
                  <Tag>LT {item.long_term_score.toFixed(1)}</Tag>
                  <Tag>ST {item.short_term_score.toFixed(1)}</Tag>
                  <Tag>风险 {item.system_risk_score.toFixed(1)}</Tag>
                  <Tag>恐慌 {item.panic_reversal_score.toFixed(1)}</Tag>
                </Space>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
