import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  List,
  Popover,
  Progress,
  Space,
  Tag,
  Typography,
} from "antd";
import { ExclamationCircleOutlined } from "@ant-design/icons";
import { type ReactNode } from "react";

import {
  MarketMonitorExecutionCard,
  MarketMonitorEventRiskFlag,
  MarketMonitorFactSheet,
  MarketMonitorHistoryDailyArtifactItem,
  MarketMonitorHistoryPoint,
  MarketMonitorPanicCard,
  MarketMonitorPromptTrace,
  MarketMonitorScoreCard,
  MarketMonitorSourceCoverage,
  MarketMonitorStageResult,
  MarketMonitorStyleEffectiveness,
  MarketMonitorSystemRiskCard,
} from "../api/types";
import {
  MARKET_MONITOR_CARD_HELP,
  type MarketMonitorCardHelpKey,
} from "../config/marketMonitorCardHelp";

function CardHelpContent(props: { helpKey: MarketMonitorCardHelpKey }) {
  const help = MARKET_MONITOR_CARD_HELP[props.helpKey];
  return (
    <div>
      <Typography.Text strong>{help.title}</Typography.Text>
      <Typography.Paragraph>{help.purpose}</Typography.Paragraph>
      <Typography.Paragraph>{help.rules}</Typography.Paragraph>
    </div>
  );
}

function CardTitleWithHelp(props: {
  title: ReactNode;
  helpKey: MarketMonitorCardHelpKey;
}) {
  const help = MARKET_MONITOR_CARD_HELP[props.helpKey];
  return (
    <div className="market-card-title">
      <span>{props.title}</span>
      <Popover content={<CardHelpContent helpKey={props.helpKey} />}>
        <Button
          type="text"
          shape="circle"
          size="small"
          aria-label={`${help.title}说明`}
          icon={<ExclamationCircleOutlined />}
        />
      </Popover>
    </div>
  );
}

function scoreTagColor(score: number) {
  if (score >= 80) return "success";
  if (score >= 60) return "processing";
  if (score >= 40) return "warning";
  return "error";
}

function boolTag(label: string, value: boolean) {
  return <Tag color={value ? "success" : "error"}>{label} {value ? "允许" : "禁止"}</Tag>;
}

function renderReasoningBlock(card: {
  reasoning_summary?: string | null;
  key_drivers?: string[];
  risks?: string[];
  confidence?: string | null;
}) {
  if (!card.reasoning_summary && !card.key_drivers?.length && !card.risks?.length && !card.confidence) {
    return null;
  }
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {card.reasoning_summary ? <Typography.Text>{card.reasoning_summary}</Typography.Text> : null}
      {card.confidence ? <Tag color="purple">置信度 {card.confidence}</Tag> : null}
      {card.key_drivers?.length ? (
        <List size="small" header="关键驱动" dataSource={card.key_drivers} renderItem={(item) => <List.Item>{item}</List.Item>} />
      ) : null}
      {card.risks?.length ? (
        <List size="small" header="风险与缺口" dataSource={card.risks} renderItem={(item) => <List.Item>{item}</List.Item>} />
      ) : null}
    </Space>
  );
}

export function ScoreCardBlock(props: {
  title: string;
  helpKey: MarketMonitorCardHelpKey;
  card: MarketMonitorScoreCard | MarketMonitorSystemRiskCard;
}) {
  return (
    <Card
      className="section-card market-assessment-card"
      title={<CardTitleWithHelp title={props.title} helpKey={props.helpKey} />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={scoreTagColor(props.card.score)}>分数 {props.card.score.toFixed(1)}</Tag>
          <Tag>{props.card.zone}</Tag>
          <Tag>1日 {props.card.delta_1d >= 0 ? "+" : ""}{props.card.delta_1d.toFixed(1)}</Tag>
          <Tag>5日 {props.card.delta_5d >= 0 ? "+" : ""}{props.card.delta_5d.toFixed(1)}</Tag>
          <Tag>{props.card.slope_state}</Tag>
        </Space>
        <Progress percent={props.card.score} showInfo={false} strokeColor="#1677ff" />
        <Typography.Text>{props.card.summary}</Typography.Text>
        <Typography.Text type="secondary">{props.card.action}</Typography.Text>
        {"liquidity_stress_score" in props.card ? (
          <Space wrap>
            <Tag>流动性压力 {props.card.liquidity_stress_score.toFixed(1)}</Tag>
            <Tag>风险偏好 {props.card.risk_appetite_score.toFixed(1)}</Tag>
          </Space>
        ) : null}
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function ExecutionCardBlock(props: { card: MarketMonitorExecutionCard }) {
  return (
    <Card
      className="page-card"
      title={<CardTitleWithHelp title="执行动作卡" helpKey="execution_card" />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">{props.card.regime_label}</Tag>
          <Tag>{props.card.conflict_mode}</Tag>
          <Tag>总仓位 {props.card.total_exposure_range}</Tag>
          <Tag>风险预算 {props.card.daily_risk_budget}</Tag>
          <Tag>单票上限 {props.card.single_position_cap}</Tag>
        </Space>
        <Typography.Text>{props.card.summary}</Typography.Text>
        <Space wrap>
          {boolTag("新开仓", props.card.new_position_allowed)}
          {boolTag("追高", props.card.chase_breakout_allowed)}
          {boolTag("低吸", props.card.dip_buy_allowed)}
          {boolTag("隔夜", props.card.overnight_allowed)}
          {boolTag("杠杆", props.card.leverage_allowed)}
        </Space>
        <Typography.Text>手法偏好：{props.card.tactic_preference}</Typography.Text>
        <Typography.Text>优先方向：{props.card.preferred_assets.join("、") || "无"}</Typography.Text>
        {props.card.avoid_assets.length ? (
          <Typography.Text type="secondary">回避方向：{props.card.avoid_assets.join("、")}</Typography.Text>
        ) : null}
        <Space wrap>
          <Typography.Text type="secondary">确认状态：{props.card.signal_confirmation.note}</Typography.Text>
          <Tag>已观察 {props.card.signal_confirmation.current_regime_observations} 次</Tag>
          <Tag>放宽解锁还需 {props.card.signal_confirmation.risk_loosening_unlock_in_observations} 次</Tag>
        </Space>
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function StyleCardBlock(props: { card: MarketMonitorStyleEffectiveness }) {
  const tacticItems: Array<{ name: string; item: MarketMonitorStyleEffectiveness["tactic_layer"]["trend_breakout"] }> = [
    { name: "趋势突破", item: props.card.tactic_layer.trend_breakout },
    { name: "回调低吸", item: props.card.tactic_layer.dip_buy },
    { name: "超跌反弹", item: props.card.tactic_layer.oversold_bounce },
  ];
  const assetItems: Array<{ name: string; item: MarketMonitorStyleEffectiveness["asset_layer"]["large_cap_tech"] }> = [
    { name: "大盘科技", item: props.card.asset_layer.large_cap_tech },
    { name: "小盘高弹性", item: props.card.asset_layer.small_cap_momentum },
    { name: "防御板块", item: props.card.asset_layer.defensive },
    { name: "能源/周期", item: props.card.asset_layer.energy_cyclical },
    { name: "金融", item: props.card.asset_layer.financials },
  ];

  return (
    <Card
      className="page-card"
      title={<CardTitleWithHelp title="风格有效性卡" helpKey="style_effectiveness_card" />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Typography.Text strong>策略手法层</Typography.Text>
        <Space wrap>
          <Tag color="success">最佳手法 {props.card.tactic_layer.top_tactic}</Tag>
          <Tag color="error">回避手法 {props.card.tactic_layer.avoid_tactic}</Tag>
        </Space>
        <List
          size="small"
          dataSource={tacticItems}
          renderItem={({ name, item }) => (
            <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>
          )}
        />
        <Typography.Text strong>资产风格层</Typography.Text>
        <Space wrap>
          <Tag color="success">偏好 {props.card.asset_layer.preferred_assets.join("、") || "无"}</Tag>
          <Tag color="warning">回避 {props.card.asset_layer.avoid_assets.join("、") || "无"}</Tag>
        </Space>
        <List
          size="small"
          dataSource={assetItems}
          renderItem={({ name, item }) => (
            <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>
          )}
        />
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function PanicCardBlock(props: { card: MarketMonitorPanicCard }) {
  return (
    <Card
      className="page-card"
      title={<CardTitleWithHelp title="恐慌反转卡" helpKey="panic_card" />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={scoreTagColor(props.card.score)}>{props.card.state}</Tag>
          <Tag>{props.card.zone}</Tag>
          <Tag>总分 {props.card.score.toFixed(1)}</Tag>
          <Tag>极端恐慌 {props.card.panic_extreme_score.toFixed(1)}</Tag>
          <Tag>衰竭 {props.card.selling_exhaustion_score.toFixed(1)}</Tag>
          <Tag>盘中反转 {props.card.intraday_reversal_score.toFixed(1)}</Tag>
        </Space>
        <Typography.Text>{props.card.action}</Typography.Text>
        <Space wrap>
          {boolTag("Early entry", props.card.early_entry_allowed)}
          <Tag>仓位上限 {props.card.max_position_hint}</Tag>
          <Tag>止损 {props.card.stop_loss}</Tag>
          <Tag>已保持 {props.card.refreshes_held} 次刷新</Tag>
        </Space>
        <Typography.Text type="secondary">盈利规则：{props.card.profit_rule}</Typography.Text>
        {props.card.system_risk_override ? (
          <Alert type="warning" showIcon message={props.card.system_risk_override} />
        ) : null}
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function EventRiskBlock(props: { card: MarketMonitorEventRiskFlag }) {
  return (
    <Card
      className="page-card"
      title={<CardTitleWithHelp title="事件风险" helpKey="event_risk_card" />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={props.card.index_level.active ? "warning" : "success"}>
            指数级 {props.card.index_level.active ? "激活" : "未激活"}
          </Tag>
          {props.card.index_level.type ? <Tag>{props.card.index_level.type}</Tag> : null}
          {props.card.index_level.days_to_event !== undefined && props.card.index_level.days_to_event !== null ? (
            <Tag>T-{props.card.index_level.days_to_event}</Tag>
          ) : null}
        </Space>
        <Typography.Text>
          {props.card.index_level.action_modifier?.note || "当前无指数级事件修正。"}
        </Typography.Text>
        <Typography.Text strong>个股级事件</Typography.Text>
        <Typography.Text>
          {props.card.stock_level.earnings_stocks.length
            ? props.card.stock_level.earnings_stocks.join("、")
            : "当前无重点财报股。"}
        </Typography.Text>
        {props.card.stock_level.rule ? (
          <Typography.Text type="secondary">{props.card.stock_level.rule}</Typography.Text>
        ) : null}
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function DataStatusBlock(props: {
  sourceCoverage: MarketMonitorSourceCoverage;
  degradedFactors: string[];
  notes: string[];
  openGaps: string[];
}) {
  return (
    <Card className="page-card" title="数据完整度与降级说明">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={props.sourceCoverage.completeness === "high" ? "success" : props.sourceCoverage.completeness === "medium" ? "warning" : "error"}>
            完整度 {props.sourceCoverage.completeness}
          </Tag>
          <Tag color={props.sourceCoverage.degraded ? "warning" : "success"}>
            {props.sourceCoverage.degraded ? "已降级输出" : "无降级"}
          </Tag>
        </Space>
        <Typography.Text>可用来源：{props.sourceCoverage.available_sources.join("、") || "无"}</Typography.Text>
        <Typography.Text type="secondary">缺失来源：{props.sourceCoverage.missing_sources.join("、") || "无"}</Typography.Text>
        <List size="small" header="降级因子" dataSource={props.degradedFactors} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item}</List.Item>} />
        <List size="small" header="数据缺口" dataSource={props.openGaps} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item}</List.Item>} />
        <List size="small" header="备注" dataSource={props.notes} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item}</List.Item>} />
      </Space>
    </Card>
  );
}

export function HistoryBlock(props: { points: MarketMonitorHistoryPoint[] }) {
  return (
    <Card className="page-card" title="历史趋势回看">
      <List
        size="small"
        dataSource={[...props.points].reverse()}
        locale={{ emptyText: "暂无历史数据" }}
        renderItem={(point) => (
          <List.Item>
            <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
              <Typography.Text strong>{point.trade_date}</Typography.Text>
              <Space wrap>
                <Tag>长线 {point.long_term_score.toFixed(1)}</Tag>
                <Tag>短线 {point.short_term_score.toFixed(1)}</Tag>
                <Tag>风险 {point.system_risk_score.toFixed(1)}</Tag>
                <Tag>恐慌 {point.panic_score.toFixed(1)}</Tag>
                <Tag color="blue">{point.regime_label}</Tag>
              </Space>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

export function HistoryArtifactsBlock(props: { items: MarketMonitorHistoryDailyArtifactItem[] }) {
  return (
    <Card className="page-card" title="History 日级产物">
      <List
        size="small"
        dataSource={props.items}
        locale={{ emptyText: "暂无日级产物" }}
        renderItem={(item) => (
          <List.Item>
            <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
              <Typography.Text strong>{item.tradeDate}</Typography.Text>
              <Space wrap>
                <Tag color={item.artifactType === "snapshot" ? "blue" : "purple"}>
                  {item.artifactType === "snapshot" ? "snapshot" : "fact_sheet"}
                </Tag>
                <Typography.Text copyable>{item.artifactName}</Typography.Text>
              </Space>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

export function StageTimelineBlock(props: { stages: MarketMonitorStageResult[] }) {
  return (
    <Card className="page-card" title="阶段时间线">
      <List
        size="small"
        dataSource={props.stages}
        locale={{ emptyText: "暂无阶段信息" }}
        renderItem={(stage) => (
          <List.Item>
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Space wrap>
                <Typography.Text strong>{stage.stage_name}</Typography.Text>
                <Tag>{stage.status}</Tag>
                {stage.started_at ? <Tag>开始 {stage.started_at}</Tag> : null}
                {stage.finished_at ? <Tag>结束 {stage.finished_at}</Tag> : null}
              </Space>
              {stage.error ? <Alert type="error" showIcon message={stage.error} /> : null}
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

export function FactSheetBlock(props: { factSheet?: MarketMonitorFactSheet | null }) {
  if (!props.factSheet) {
    return null;
  }
  return (
    <Card className="page-card" title="Fact Sheet">
      <Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="交易日">{props.factSheet.as_of_date}</Descriptions.Item>
        <Descriptions.Item label="生成时间">{props.factSheet.generated_at}</Descriptions.Item>
        <Descriptions.Item label="Open gaps">{props.factSheet.open_gaps.join("、") || "无"}</Descriptions.Item>
        <Descriptions.Item label="Notes">{props.factSheet.notes.join("、") || "无"}</Descriptions.Item>
      </Descriptions>
      <Collapse
        style={{ marginTop: 16 }}
        items={[
          {
            key: "derived_metrics",
            label: "Derived metrics",
            children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(props.factSheet.derived_metrics, null, 2)}</pre>,
          },
          {
            key: "local_facts",
            label: "Local facts",
            children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(props.factSheet.local_facts, null, 2)}</pre>,
          },
        ]}
      />
    </Card>
  );
}

export function PromptTraceBlock(props: { traces: MarketMonitorPromptTrace[] }) {
  return (
    <Card className="page-card" title="Prompt Traces">
      <Collapse
        items={props.traces.map((trace, index) => ({
          key: `${trace.stage}-${trace.card_type || index}`,
          label: `${trace.stage}${trace.card_type ? ` / ${trace.card_type}` : ""}`,
          children: (
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space wrap>
                <Tag>{trace.model || "unknown model"}</Tag>
                <Tag color={trace.parsed_ok ? "success" : "error"}>{trace.parsed_ok ? "parsed" : "fallback"}</Tag>
                {trace.provider ? <Tag>{trace.provider}</Tag> : null}
                {trace.latency_ms ? <Tag>{trace.latency_ms} ms</Tag> : null}
              </Space>
              {trace.input_summary ? <Typography.Text>{trace.input_summary}</Typography.Text> : null}
              {trace.error ? <Alert type="error" showIcon message={trace.error} /> : null}
              {trace.prompt_text ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.prompt_text}</pre> : null}
              {trace.raw_response ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.raw_response}</pre> : null}
            </Space>
          ),
        }))}
      />
    </Card>
  );
}
