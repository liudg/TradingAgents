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
  green: "Green",
  yellow: "Yellow",
  yellow_green_swing: "Yellow-Green Swing",
  orange: "Orange",
  red: "Red",
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
  if (!label) return "N/A";
  return regimeLabelMap[label as MarketRegimeLabel] ?? label;
}

function ScoreCardBlock(props: { title: string; card?: MarketScoreCard | null }) {
  if (!props.card) {
    return (
      <Card className="section-card market-score-card" title={props.title}>
        <Alert type="warning" showIcon message="Rule score unavailable for this request." />
      </Card>
    );
  }

  return (
    <Card className="section-card market-score-card" title={props.title}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Statistic
          title="Score"
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

  useEffect(() => {
    if (snapshotQuery.data?.rule_snapshot.ready) {
      setHistoryEnabled(true);
    }
  }, [snapshotQuery.data?.rule_snapshot.ready]);

  if (snapshotQuery.isLoading) {
    return (
      <Card className="page-card" title="Market Monitor">
        <Skeleton active paragraph={{ rows: 14 }} />
      </Card>
    );
  }

  if (snapshotQuery.isError || !snapshotQuery.data) {
    return (
      <Result
        status="error"
        title="Market monitor failed to load"
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
  const topStatus = useMemo(() => {
    if (!ruleSnapshot.ready) return "Rule snapshot incomplete";
    if (overlay.status === "applied") return "Rule snapshot + model overlay";
    return "Rule snapshot only";
  }, [overlay.status, ruleSnapshot.ready]);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>Market Monitor</span>
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
            <ReloadOutlined /> Refresh
          </a>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="processing">As of {formatDateTime(snapshot.timestamp)}</Tag>
            <Tag color={sourceCoverage.status === "full" ? "success" : sourceCoverage.status === "partial" ? "warning" : "error"}>
              Coverage {sourceCoverage.status}
            </Tag>
            <Tag>Trade date {snapshot.as_of_date}</Tag>
            <Tag>Overlay {overlay.status}</Tag>
          </Space>
          {!ruleSnapshot.ready ? (
            <Alert
              type="warning"
              showIcon
              message="Rule snapshot is incomplete"
              description={
                ruleSnapshot.missing_inputs.length
                  ? `Missing inputs: ${ruleSnapshot.missing_inputs.join(", ")}`
                  : "Required inputs are incomplete."
              }
            />
          ) : null}
          {sourceCoverage.notes.length ? (
            <Alert
              type="info"
              showIcon
              message="Source coverage notes"
              description={sourceCoverage.notes.join(" ")}
            />
          ) : null}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="Long-Term Rule Card" card={ruleSnapshot.long_term_score} />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="Short-Term Rule Card" card={ruleSnapshot.short_term_score} />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock title="System Risk Rule Card" card={ruleSnapshot.system_risk_score} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="Rule Snapshot">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={regimeTagColor(ruleSnapshot.base_regime_label)}>
                  Base regime {displayRegime(ruleSnapshot.base_regime_label)}
                </Tag>
                <Tag>Ready {ruleSnapshot.ready ? "yes" : "no"}</Tag>
              </Space>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="Exposure">
                  {ruleSnapshot.base_execution_card?.total_exposure_range ?? "N/A"}
                </Descriptions.Item>
                <Descriptions.Item label="Conflict mode">
                  {ruleSnapshot.base_execution_card?.conflict_mode ?? "N/A"}
                </Descriptions.Item>
                <Descriptions.Item label="Risk budget">
                  {ruleSnapshot.base_execution_card?.daily_risk_budget ?? "N/A"}
                </Descriptions.Item>
                <Descriptions.Item label="Rule summary">
                  {ruleSnapshot.base_execution_card?.summary ?? "N/A"}
                </Descriptions.Item>
              </Descriptions>
              <Typography.Text strong>Missing inputs</Typography.Text>
              <Space wrap>
                {ruleSnapshot.missing_inputs.length ? (
                  ruleSnapshot.missing_inputs.map((item) => <Tag key={item}>{item}</Tag>)
                ) : (
                  <Tag color="success">None</Tag>
                )}
              </Space>
              <Typography.Text strong>Degraded factors</Typography.Text>
              <List
                size="small"
                dataSource={ruleSnapshot.degraded_factors}
                locale={{ emptyText: "None" }}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="Model Overlay">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={overlay.status === "applied" ? "success" : overlay.status === "error" ? "error" : "default"}>
                  {overlay.status}
                </Tag>
                <Tag>Confidence {overlay.model_confidence ?? "N/A"}</Tag>
                <Tag>Regime override {displayRegime(overlay.regime_override)}</Tag>
              </Space>
              <Typography.Text>{overlay.market_narrative || "No market narrative."}</Typography.Text>
              <Typography.Text>{overlay.risk_narrative || "No risk narrative."}</Typography.Text>
              <Typography.Text>{overlay.panic_narrative || "No panic narrative."}</Typography.Text>
              <Typography.Text strong>Evidence sources</Typography.Text>
              <Space wrap>
                {overlay.evidence_sources.length ? (
                  overlay.evidence_sources.map((item) => <Tag key={item}>{item}</Tag>)
                ) : (
                  <Tag>None</Tag>
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
          <Card className="page-card" title="Final Decision">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={regimeTagColor(finalExecutionCard?.regime_label)}>
                  Final regime {displayRegime(finalExecutionCard?.regime_label)}
                </Tag>
                <Tag>Exposure {finalExecutionCard?.total_exposure_range ?? "N/A"}</Tag>
                <Tag>Risk budget {finalExecutionCard?.daily_risk_budget ?? "N/A"}</Tag>
              </Space>
              <Typography.Text>{finalExecutionCard?.summary ?? "No final action summary."}</Typography.Text>
              <Space wrap>
                <Tag color={finalExecutionCard?.new_position_allowed ? "success" : "error"}>
                  New positions {finalExecutionCard?.new_position_allowed ? "allowed" : "blocked"}
                </Tag>
                <Tag color={finalExecutionCard?.chase_breakout_allowed ? "success" : "error"}>
                  Breakout chase {finalExecutionCard?.chase_breakout_allowed ? "allowed" : "blocked"}
                </Tag>
                <Tag color={finalExecutionCard?.dip_buy_allowed ? "success" : "error"}>
                  Dip buy {finalExecutionCard?.dip_buy_allowed ? "allowed" : "blocked"}
                </Tag>
                <Tag color={finalExecutionCard?.overnight_allowed ? "success" : "error"}>
                  Overnight {finalExecutionCard?.overnight_allowed ? "allowed" : "blocked"}
                </Tag>
              </Space>
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="Event risk">
                  {finalExecutionCard?.event_risk_flag.index_level.active
                    ? finalExecutionCard.event_risk_flag.index_level.type ?? "active"
                    : "inactive"}
                </Descriptions.Item>
                <Descriptions.Item label="Stock event rule">
                  {finalExecutionCard?.event_risk_flag.stock_level.rule ?? "N/A"}
                </Descriptions.Item>
              </Descriptions>
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="page-card" title="Panic Module">
            {ruleSnapshot.panic_reversal_score ? (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <Space wrap>
                  <Tag>{ruleSnapshot.panic_reversal_score.state}</Tag>
                  <Tag>{ruleSnapshot.panic_reversal_score.zone}</Tag>
                  <Tag>
                    Early entry {ruleSnapshot.panic_reversal_score.early_entry_allowed ? "allowed" : "off"}
                  </Tag>
                </Space>
                <Statistic
                  title="Score"
                  value={ruleSnapshot.panic_reversal_score.score}
                  precision={1}
                />
                <Progress percent={Math.round(ruleSnapshot.panic_reversal_score.score)} />
                <Typography.Text>{ruleSnapshot.panic_reversal_score.action}</Typography.Text>
                <Typography.Text type="secondary">
                  Stop {ruleSnapshot.panic_reversal_score.stop_loss} | Profit {ruleSnapshot.panic_reversal_score.profit_rule}
                </Typography.Text>
              </Space>
            ) : (
              <Alert type="warning" showIcon message="Panic module unavailable without a complete rule snapshot." />
            )}
          </Card>
        </Col>
      </Row>

      <Card className="page-card" title="Data Status">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Tag color={sourceCoverage.status === "full" ? "success" : sourceCoverage.status === "partial" ? "warning" : "error"}>
            {sourceCoverage.status}
          </Tag>
          <Typography.Text strong>Available sources</Typography.Text>
          <Space wrap>
            {["live_yfinance_daily", "nasdaq_100_static_universe", "fastapi_market_monitor"].map((item) => (
              <Tag key={item}>{item}</Tag>
            ))}
          </Space>
          <Typography.Text strong>Pending sources</Typography.Text>
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
        title="Recent History"
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
              Load History
            </a>
          ) : undefined
        }
      >
        <List
          dataSource={historyEnabled ? history?.points || [] : []}
          locale={{ emptyText: historyEnabled ? "No history data available" : "History loads on demand to avoid duplicate live downloads." }}
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
                  <Tag>Risk {item.system_risk_score.toFixed(1)}</Tag>
                  <Tag>Panic {item.panic_reversal_score.toFixed(1)}</Tag>
                </Space>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
