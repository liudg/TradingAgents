import {
  Alert,
  Card,
  Col,
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
import { useEffect, useState } from "react";

import {
  useMarketMonitorDataStatus,
  useMarketMonitorHistory,
  useMarketMonitorSnapshot,
} from "../api/hooks";
import { extractErrorMessage, formatDateTime } from "../utils/format";

function scoreColor(score: number) {
  if (score >= 65) return "#389e0d";
  if (score >= 50) return "#d48806";
  return "#cf1322";
}

function regimeTagColor(label: string) {
  if (label === "绿灯") return "success";
  if (label === "黄灯" || label === "黄绿灯-Swing") return "warning";
  if (label === "橙灯") return "orange";
  return "error";
}

function ScoreCardBlock(props: {
  title: string;
  score: number;
  zone: string;
  delta1d: number;
  delta5d: number;
  slope: string;
  action: string;
}) {
  return (
    <Card className="section-card market-score-card" title={props.title}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Statistic
          title="当前评分"
          value={props.score}
          precision={1}
          valueStyle={{ color: scoreColor(props.score) }}
        />
        <Space wrap>
          <Tag color="blue">{props.zone}</Tag>
          <Tag>1日 {props.delta1d >= 0 ? "+" : ""}{props.delta1d.toFixed(1)}</Tag>
          <Tag>5日 {props.delta5d >= 0 ? "+" : ""}{props.delta5d.toFixed(1)}</Tag>
          <Tag>{props.slope}</Tag>
        </Space>
        <Progress
          percent={Math.round(props.score)}
          showInfo={false}
          strokeColor={scoreColor(props.score)}
        />
        <Typography.Text>{props.action}</Typography.Text>
      </Space>
    </Card>
  );
}

export function MarketMonitorPage() {
  const [forceRefresh, setForceRefresh] = useState(false);
  const snapshotQuery = useMarketMonitorSnapshot(forceRefresh);
  const historyQuery = useMarketMonitorHistory();
  const dataStatusQuery = useMarketMonitorDataStatus();

  useEffect(() => {
    if (forceRefresh && !snapshotQuery.isFetching) {
      setForceRefresh(false);
    }
  }, [forceRefresh, snapshotQuery.isFetching]);

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
  const history = historyQuery.data;
  const dataStatus = dataStatusQuery.data;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>市场监控</span>
            <Tag color={regimeTagColor(snapshot.execution_card.regime_label)}>
              {snapshot.execution_card.regime_label}
            </Tag>
            <Tag>{snapshot.execution_card.conflict_mode}</Tag>
          </Space>
        }
        extra={
          <a
            className="page-card-extra-button ant-btn ant-btn-default"
            onClick={(event) => {
              event.preventDefault();
              setForceRefresh(true);
              snapshotQuery.refetch();
              historyQuery.refetch();
              dataStatusQuery.refetch();
            }}
          >
            <ReloadOutlined /> 刷新
          </a>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="processing">数据时间 {formatDateTime(snapshot.timestamp)}</Tag>
            <Tag color={snapshot.source_coverage.status === "full" ? "success" : "warning"}>
              数据完整度 {snapshot.source_coverage.status}
            </Tag>
            <Tag>观察日 {snapshot.as_of_date}</Tag>
          </Space>
          {snapshot.source_coverage.notes.length ? (
            <Alert
              type="info"
              showIcon
              message="当前为骨架版本"
              description={snapshot.source_coverage.notes.join(" ")}
            />
          ) : null}
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <ScoreCardBlock
            title="长线环境卡"
            score={snapshot.long_term_score.score}
            zone={snapshot.long_term_score.zone}
            delta1d={snapshot.long_term_score.delta_1d}
            delta5d={snapshot.long_term_score.delta_5d}
            slope={snapshot.long_term_score.slope_state}
            action={snapshot.long_term_score.action}
          />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock
            title="短线环境卡"
            score={snapshot.short_term_score.score}
            zone={snapshot.short_term_score.zone}
            delta1d={snapshot.short_term_score.delta_1d}
            delta5d={snapshot.short_term_score.delta_5d}
            slope={snapshot.short_term_score.slope_state}
            action={snapshot.short_term_score.action}
          />
        </Col>
        <Col xs={24} lg={8}>
          <ScoreCardBlock
            title="系统风险卡"
            score={snapshot.system_risk_score.score}
            zone={snapshot.system_risk_score.zone}
            delta1d={snapshot.system_risk_score.delta_1d}
            delta5d={snapshot.system_risk_score.delta_5d}
            slope={snapshot.system_risk_score.slope_state}
            action={snapshot.system_risk_score.action}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="风格有效性">
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              <div>
                <Typography.Title level={5}>策略手法层</Typography.Title>
                <Space wrap>
                  <Tag color="success">
                    最佳手法 {snapshot.style_effectiveness.tactic_layer.top_tactic}
                  </Tag>
                  <Tag color="error">
                    回避手法 {snapshot.style_effectiveness.tactic_layer.avoid_tactic}
                  </Tag>
                </Space>
              </div>
              <div>
                <Typography.Title level={5}>资产风格层</Typography.Title>
                <Space wrap>
                  {snapshot.style_effectiveness.asset_layer.preferred_assets.map((item) => (
                    <Tag key={item} color="blue">{item}</Tag>
                  ))}
                  {snapshot.style_effectiveness.asset_layer.avoid_assets.map((item) => (
                    <Tag key={item}>{item}</Tag>
                  ))}
                </Space>
              </div>
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="执行动作卡">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag color={regimeTagColor(snapshot.execution_card.regime_label)}>
                  {snapshot.execution_card.regime_label}
                </Tag>
                <Tag>{snapshot.execution_card.total_exposure_range}</Tag>
                <Tag>单票上限 {snapshot.execution_card.single_position_cap}</Tag>
                <Tag>风险预算 {snapshot.execution_card.daily_risk_budget}</Tag>
              </Space>
              <Typography.Text>{snapshot.execution_card.tactic_preference}</Typography.Text>
              <Space wrap>
                <Tag color={snapshot.execution_card.new_position_allowed ? "success" : "error"}>
                  新开仓 {snapshot.execution_card.new_position_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={snapshot.execution_card.chase_breakout_allowed ? "success" : "error"}>
                  追强势 {snapshot.execution_card.chase_breakout_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={snapshot.execution_card.dip_buy_allowed ? "success" : "error"}>
                  低吸 {snapshot.execution_card.dip_buy_allowed ? "允许" : "禁止"}
                </Tag>
                <Tag color={snapshot.execution_card.leverage_allowed ? "success" : "error"}>
                  杠杆 {snapshot.execution_card.leverage_allowed ? "允许" : "禁止"}
                </Tag>
              </Space>
              <Typography.Text type="secondary">
                {snapshot.execution_card.signal_confirmation.note}
              </Typography.Text>
            </Space>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card className="page-card" title="恐慌反转模块">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Space wrap>
                <Tag
                  color={
                    snapshot.panic_reversal_score.state === "panic_confirmed"
                      ? "success"
                      : snapshot.panic_reversal_score.state === "panic_watch"
                        ? "warning"
                        : "default"
                  }
                >
                  {snapshot.panic_reversal_score.state}
                </Tag>
                <Tag>{snapshot.panic_reversal_score.zone}</Tag>
                <Tag>
                  early entry {snapshot.panic_reversal_score.early_entry_allowed ? "允许" : "关闭"}
                </Tag>
              </Space>
              <Statistic
                title="综合评分"
                value={snapshot.panic_reversal_score.score}
                precision={1}
              />
              <Progress percent={Math.round(snapshot.panic_reversal_score.score)} />
              <Space wrap>
                <Tag>恐慌 {snapshot.panic_reversal_score.panic_extreme_score.toFixed(1)}</Tag>
                <Tag>衰竭 {snapshot.panic_reversal_score.selling_exhaustion_score.toFixed(1)}</Tag>
                <Tag>日内反转 {snapshot.panic_reversal_score.intraday_reversal_score.toFixed(1)}</Tag>
                <Tag>次日延续 {snapshot.panic_reversal_score.followthrough_confirmation_score.toFixed(1)}</Tag>
              </Space>
              <Typography.Text>{snapshot.panic_reversal_score.action}</Typography.Text>
              <Typography.Text type="secondary">
                止损 {snapshot.panic_reversal_score.stop_loss}，止盈 {snapshot.panic_reversal_score.profit_rule}
              </Typography.Text>
            </Space>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="page-card" title="数据状态">
            <Space direction="vertical" size={12} style={{ width: "100%" }}>
              <Tag color={dataStatus?.source_coverage.status === "full" ? "success" : "warning"}>
                {dataStatus?.source_coverage.status ?? snapshot.source_coverage.status}
              </Tag>
              <List
                size="small"
                header="降级因子"
                dataSource={snapshot.source_coverage.degraded_factors}
                renderItem={(item) => <List.Item>{item}</List.Item>}
              />
            </Space>
          </Card>
        </Col>
      </Row>

      <Card className="page-card" title="最近趋势">
        <List
          dataSource={history?.points || []}
          locale={{ emptyText: "暂无历史数据" }}
          renderItem={(item) => (
            <List.Item>
              <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
                <Space wrap>
                  <Typography.Text strong>{item.trade_date}</Typography.Text>
                  <Tag color={regimeTagColor(item.regime_label)}>{item.regime_label}</Tag>
                </Space>
                <Space wrap>
                  <Tag>长线 {item.long_term_score.toFixed(1)}</Tag>
                  <Tag>短线 {item.short_term_score.toFixed(1)}</Tag>
                  <Tag>风险 {item.system_risk_score.toFixed(1)}</Tag>
                  <Tag>恐慌反转 {item.panic_reversal_score.toFixed(1)}</Tag>
                </Space>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
