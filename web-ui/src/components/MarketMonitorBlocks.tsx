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
  MarketMonitorEventFact,
  MarketMonitorExecutionCard,
  MarketMonitorEventRiskFlag,
  MarketMonitorFactSheet,
  MarketMonitorFactorBreakdown,
  MarketMonitorHistoryDailyArtifactItem,
  MarketMonitorHistoryPoint,
  MarketMonitorInputDataStatus,
  MarketMonitorMissingDataItem,
  MarketMonitorPanicCard,
  MarketMonitorPromptTrace,
  MarketMonitorScoreCard,
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

function CardTitleWithHelp(props: { title: ReactNode; helpKey: MarketMonitorCardHelpKey }) {
  const help = MARKET_MONITOR_CARD_HELP[props.helpKey];
  return (
    <div className="market-card-title">
      <span>{props.title}</span>
      <Popover content={<CardHelpContent helpKey={props.helpKey} />}>
        <Button type="text" shape="circle" size="small" aria-label={`${help.title}说明`} icon={<ExclamationCircleOutlined />} />
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

function confidenceText(value?: number | null) {
  if (value === undefined || value === null) return "-";
  return `${Math.round(value * 100)}%`;
}

function renderReasoningBlock(card: { reasoning_summary?: string | null; key_drivers?: string[]; risks?: string[]; confidence?: number | null }) {
  if (!card.reasoning_summary && !card.key_drivers?.length && !card.risks?.length && card.confidence === undefined) {
    return null;
  }
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {card.reasoning_summary ? <Typography.Text>{card.reasoning_summary}</Typography.Text> : null}
      {card.confidence !== undefined ? <Tag color="purple">置信度 {confidenceText(card.confidence)}</Tag> : null}
      {card.key_drivers?.length ? <List size="small" header="关键驱动" dataSource={card.key_drivers} renderItem={(item) => <List.Item>{item}</List.Item>} /> : null}
      {card.risks?.length ? <List size="small" header="风险与缺口" dataSource={card.risks} renderItem={(item) => <List.Item>{item}</List.Item>} /> : null}
    </Space>
  );
}

function FactorBreakdownList(props: { factors: MarketMonitorFactorBreakdown[] }) {
  return (
    <List
      size="small"
      header="因子拆解"
      dataSource={props.factors}
      locale={{ emptyText: "暂无因子" }}
      renderItem={(factor) => (
        <List.Item>
          <Space direction="vertical" size={2} style={{ width: "100%" }}>
            <Space wrap>
              <Typography.Text strong>{factor.factor}</Typography.Text>
              <Tag>分 {factor.score.toFixed(1)}</Tag>
              <Tag>权重 {(factor.weight * 100).toFixed(0)}%</Tag>
              <Tag>{factor.polarity}</Tag>
              <Tag color={factor.data_status === "available" ? "success" : "warning"}>{factor.data_status}</Tag>
            </Space>
            <Typography.Text type="secondary">
              原始值 {String(factor.raw_value ?? "-")}{factor.raw_value_unit ? ` ${factor.raw_value_unit}` : ""}；{factor.reason}
            </Typography.Text>
          </Space>
        </List.Item>
      )}
    />
  );
}

export function ScoreCardBlock(props: { title: string; helpKey: MarketMonitorCardHelpKey; card: MarketMonitorScoreCard | MarketMonitorSystemRiskCard }) {
  return (
    <Card className="section-card market-assessment-card" title={<CardTitleWithHelp title={props.title} helpKey={props.helpKey} />}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={scoreTagColor(props.card.score)}>最终分 {props.card.score.toFixed(1)}</Tag>
          <Tag>基础分 {props.card.deterministic_score.toFixed(1)}</Tag>
          <Tag>{props.card.zone}</Tag>
          <Tag>1日 {props.card.delta_1d >= 0 ? "+" : ""}{props.card.delta_1d.toFixed(1)}</Tag>
          <Tag>5日 {props.card.delta_5d >= 0 ? "+" : ""}{props.card.delta_5d.toFixed(1)}</Tag>
          <Tag>{props.card.slope_state}</Tag>
        </Space>
        <Progress percent={props.card.score} showInfo={false} strokeColor="#1677ff" />
        {props.card.recommended_exposure ? <Typography.Text>建议仓位：{props.card.recommended_exposure}</Typography.Text> : null}
        {props.card.score_adjustment ? (
          <Alert type="info" showIcon message={`评分调整 ${props.card.score_adjustment.value}`} description={props.card.score_adjustment.reason} />
        ) : null}
        {"liquidity_stress_score" in props.card ? (
          <Space wrap>
            <Tag>流动性压力 {props.card.liquidity_stress_score.toFixed(1)}</Tag>
            <Tag>风险偏好 {props.card.risk_appetite_score.toFixed(1)}</Tag>
            {props.card.event_triggers.map((trigger) => <Tag key={`${trigger.trigger_type}-${trigger.event}`} color="warning">{trigger.event} {trigger.score_impact}</Tag>)}
          </Space>
        ) : null}
        <FactorBreakdownList factors={props.card.factor_breakdown} />
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function ExecutionCardBlock(props: { card: MarketMonitorExecutionCard }) {
  return (
    <Card className="page-card" title={<CardTitleWithHelp title="执行动作卡" helpKey="execution_card" />}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">{props.card.regime_label}</Tag>
          <Tag>{props.card.conflict_mode}</Tag>
          <Tag>总仓位 {props.card.total_exposure_range}</Tag>
          <Tag>风险预算 {props.card.daily_risk_budget}</Tag>
          <Tag>单票上限 {props.card.single_position_cap}</Tag>
        </Space>
        <Space wrap>
          {boolTag("新开仓", props.card.new_position_allowed)}
          {boolTag("追高", props.card.chase_breakout_allowed)}
          {boolTag("低吸", props.card.dip_buy_allowed)}
          {boolTag("隔夜", props.card.overnight_allowed)}
          {boolTag("杠杆", props.card.leverage_allowed)}
        </Space>
        <Typography.Text>手法偏好：{props.card.tactic_preference}</Typography.Text>
        <Typography.Text>优先方向：{props.card.preferred_assets.join("、") || "无"}</Typography.Text>
        {props.card.avoid_assets.length ? <Typography.Text type="secondary">回避方向：{props.card.avoid_assets.join("、")}</Typography.Text> : null}
        <Space wrap>
          <Typography.Text type="secondary">确认状态：{props.card.signal_confirmation.note}</Typography.Text>
          <Tag>已观察 {props.card.signal_confirmation.current_regime_observations} 次</Tag>
          <Tag>放宽解锁还需 {props.card.signal_confirmation.risk_loosening_unlock_in_observations} 次</Tag>
        </Space>
        <EventRiskBlock card={props.card.event_risk_flag} />
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function StyleCardBlock(props: { card: MarketMonitorStyleEffectiveness }) {
  const tacticItems = [
    { name: "趋势突破", item: props.card.tactic_layer.trend_breakout },
    { name: "回调低吸", item: props.card.tactic_layer.dip_buy },
    { name: "超跌反弹", item: props.card.tactic_layer.oversold_bounce },
  ];
  const assetItems = [
    { name: "大盘科技", item: props.card.asset_layer.large_cap_tech },
    { name: "小盘高弹性", item: props.card.asset_layer.small_cap_momentum },
    { name: "防御板块", item: props.card.asset_layer.defensive },
    { name: "能源/周期", item: props.card.asset_layer.energy_cyclical },
    { name: "金融", item: props.card.asset_layer.financials },
  ];
  return (
    <Card className="page-card" title={<CardTitleWithHelp title="市场手法与风格有效性卡" helpKey="style_effectiveness_card" />}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Typography.Text strong>策略手法层</Typography.Text>
        <Space wrap><Tag color="success">最佳手法 {props.card.tactic_layer.top_tactic}</Tag><Tag color="error">回避手法 {props.card.tactic_layer.avoid_tactic}</Tag></Space>
        <List size="small" dataSource={tacticItems} renderItem={({ name, item }) => <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>} />
        <Typography.Text strong>资产风格层</Typography.Text>
        <Space wrap><Tag color="success">偏好 {props.card.asset_layer.preferred_assets.join("、") || "无"}</Tag><Tag color="warning">回避 {props.card.asset_layer.avoid_assets.join("、") || "无"}</Tag></Space>
        <List size="small" dataSource={assetItems} renderItem={({ name, item }) => <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>} />
        <FactorBreakdownList factors={props.card.asset_layer.factor_breakdown} />
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function PanicCardBlock(props: { card: MarketMonitorPanicCard }) {
  return (
    <Card className="page-card" title={<CardTitleWithHelp title="恐慌反转卡" helpKey="panic_card" />}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={props.card.state === "panic_confirmed" ? "success" : props.card.state === "capitulation_watch" ? "warning" : "default"}>{props.card.state}</Tag>
          <Tag>{props.card.zone}</Tag>
          <Tag>反转分 {props.card.score.toFixed(1)}</Tag>
          <Tag>极端恐慌 {props.card.panic_extreme_score.toFixed(1)}</Tag>
          <Tag>抛压衰竭 {props.card.selling_exhaustion_score.toFixed(1)}</Tag>
          <Tag>反弹确认 {props.card.intraday_reversal_score.toFixed(1)}</Tag>
        </Space>
        <Typography.Text>{props.card.action}</Typography.Text>
        <Space wrap>{boolTag("先手仓", props.card.early_entry_allowed)}<Tag>仓位上限 {props.card.max_position_hint}</Tag><Tag>止损 {props.card.stop_loss}</Tag><Tag>已保持 {props.card.refreshes_held} 次刷新</Tag></Space>
        <Typography.Text type="secondary">盈利规则：{props.card.profit_rule}</Typography.Text>
        {props.card.system_risk_override ? <Alert type="warning" showIcon message={props.card.system_risk_override} /> : null}
        <FactorBreakdownList factors={props.card.factor_breakdown} />
        {renderReasoningBlock(props.card)}
      </Space>
    </Card>
  );
}

export function EventRiskBlock(props: { card: MarketMonitorEventRiskFlag }) {
  return (
    <Card className="page-card" title={<CardTitleWithHelp title="事件风险" helpKey="event_risk_card" />}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={props.card.index_level.active ? "warning" : "success"}>指数级 {props.card.index_level.active ? "激活" : "未激活"}</Tag>
          {props.card.index_level.events.map((event) => <Tag key={event}>{event}</Tag>)}
        </Space>
        <Typography.Text>{props.card.index_level.action_modifier?.note || "当前无指数级事件修正。"}</Typography.Text>
        <Typography.Text strong>个股级事件</Typography.Text>
        <Typography.Text>{props.card.stock_level.earnings_stocks.length ? props.card.stock_level.earnings_stocks.join("、") : "当前无重点财报股。"}</Typography.Text>
        {props.card.stock_level.rule ? <Typography.Text type="secondary">{props.card.stock_level.rule}</Typography.Text> : null}
      </Space>
    </Card>
  );
}

export function EventFactSheetBlock(props: { events: MarketMonitorEventFact[] }) {
  return (
    <Card className="page-card" title="统一事件事实表">
      <List
        size="small"
        dataSource={props.events}
        locale={{ emptyText: "当前刷新周期无结构化事件事实" }}
        renderItem={(event) => (
          <List.Item>
            <Space direction="vertical" size={2} style={{ width: "100%" }}>
              <Space wrap><Typography.Text strong>{event.event}</Typography.Text><Tag>{event.scope}</Tag><Tag color={event.severity === "high" || event.severity === "critical" ? "warning" : "default"}>{event.severity}</Tag><Tag>置信度 {confidenceText(event.confidence)}</Tag></Space>
              <Typography.Text>{event.source_summary}</Typography.Text>
              <Typography.Text type="secondary">来源：{event.source_name}；窗口：{event.time_window}；过期：{event.expires_at}</Typography.Text>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}

export function DataStatusBlock(props: { inputDataStatus: MarketMonitorInputDataStatus; missingData: MarketMonitorMissingDataItem[]; risks: string[]; openGaps: string[] }) {
  return (
    <Card className="page-card" title="数据状态与缺失说明">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color={props.inputDataStatus.core_symbols_missing.length ? "warning" : "success"}>核心可用 {props.inputDataStatus.core_symbols_available.length}</Tag>
          <Tag>interval {props.inputDataStatus.interval}</Tag>
          <Tag>{props.inputDataStatus.source}</Tag>
        </Space>
        <Typography.Text>缺失核心标的：{props.inputDataStatus.core_symbols_missing.join("、") || "无"}</Typography.Text>
        <Typography.Text type="secondary">stale 标的：{props.inputDataStatus.stale_symbols.join("、") || "无"}</Typography.Text>
        <List size="small" header="缺失数据" dataSource={props.missingData} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item.field}：{item.reason}{item.impact ? `（${item.impact}）` : ""}</List.Item>} />
        <List size="small" header="数据缺口" dataSource={props.openGaps} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item}</List.Item>} />
        <List size="small" header="风险提示" dataSource={props.risks} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item>{item}</List.Item>} />
      </Space>
    </Card>
  );
}

export function HistoryBlock(props: { points: MarketMonitorHistoryPoint[] }) {
  return (
    <Card className="page-card" title="历史趋势回看">
      <List size="small" dataSource={[...props.points].reverse()} locale={{ emptyText: "暂无历史数据" }} renderItem={(point) => (
        <List.Item>
          <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{point.trade_date}</Typography.Text>
            <Space wrap>
              <Tag>长线 {point.long_term_score.toFixed(1)}</Tag>
              <Tag>短线 {point.short_term_score.toFixed(1)}</Tag>
              <Tag>风险 {point.system_risk_score.toFixed(1)}</Tag>
              <Tag>恐慌反转 {point.panic_reversal_score.toFixed(1)}</Tag>
              <Tag>{point.panic_state}</Tag>
              <Tag color="blue">{point.regime_label}</Tag>
            </Space>
          </Space>
        </List.Item>
      )} />
    </Card>
  );
}

export function HistoryArtifactsBlock(props: { items: MarketMonitorHistoryDailyArtifactItem[] }) {
  return (
    <Card className="page-card" title="History 日级产物">
      <List size="small" dataSource={props.items} locale={{ emptyText: "暂无日级产物" }} renderItem={(item) => (
        <List.Item>
          <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Text strong>{item.tradeDate}</Typography.Text>
            <Space wrap><Tag color={item.artifactType === "snapshot" ? "blue" : "purple"}>{item.artifactType === "snapshot" ? "snapshot" : "fact_sheet"}</Tag><Typography.Text copyable>{item.artifactName}</Typography.Text></Space>
          </Space>
        </List.Item>
      )} />
    </Card>
  );
}

export function StageTimelineBlock(props: { stages: MarketMonitorStageResult[] }) {
  return (
    <Card className="page-card" title="阶段时间线">
      <List size="small" dataSource={props.stages} locale={{ emptyText: "暂无阶段信息" }} renderItem={(stage) => (
        <List.Item>
          <Space direction="vertical" size={4} style={{ width: "100%" }}>
            <Space wrap><Typography.Text strong>{stage.stage_name}</Typography.Text><Tag>{stage.status}</Tag>{stage.started_at ? <Tag>开始 {stage.started_at}</Tag> : null}{stage.finished_at ? <Tag>结束 {stage.finished_at}</Tag> : null}</Space>
            {stage.error ? <Alert type="error" showIcon message={stage.error} /> : null}
          </Space>
        </List.Item>
      )} />
    </Card>
  );
}

export function FactSheetBlock(props: { factSheet?: MarketMonitorFactSheet | null }) {
  if (!props.factSheet) return null;
  return (
    <Card className="page-card" title="Fact Sheet">
      <Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="交易日">{props.factSheet.as_of_date}</Descriptions.Item>
        <Descriptions.Item label="生成时间">{props.factSheet.generated_at}</Descriptions.Item>
        <Descriptions.Item label="Open gaps">{props.factSheet.open_gaps.join("、") || "无"}</Descriptions.Item>
        <Descriptions.Item label="Notes">{props.factSheet.notes.join("、") || "无"}</Descriptions.Item>
      </Descriptions>
      <Collapse style={{ marginTop: 16 }} items={[{ key: "event_fact_sheet", label: "Event fact sheet", children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(props.factSheet.event_fact_sheet, null, 2)}</pre> }, { key: "derived_metrics", label: "Derived metrics", children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(props.factSheet.derived_metrics, null, 2)}</pre> }, { key: "local_facts", label: "Local facts", children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(props.factSheet.local_facts, null, 2)}</pre> }]} />
    </Card>
  );
}

export function PromptTraceBlock(props: { traces: MarketMonitorPromptTrace[] }) {
  return (
    <Card className="page-card" title="Prompt Traces">
      <Collapse items={props.traces.map((trace, index) => ({ key: `${trace.stage}-${trace.card_type || index}`, label: `${trace.stage}${trace.card_type ? ` / ${trace.card_type}` : ""}`, children: (
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Space wrap><Tag>{trace.model || "unknown model"}</Tag><Tag color={trace.parsed_ok ? "success" : "error"}>{trace.parsed_ok ? "parsed" : "fallback"}</Tag>{trace.provider ? <Tag>{trace.provider}</Tag> : null}{trace.latency_ms ? <Tag>{trace.latency_ms} ms</Tag> : null}</Space>
          {trace.input_summary ? <Typography.Text>{trace.input_summary}</Typography.Text> : null}
          {trace.error ? <Alert type="error" showIcon message={trace.error} /> : null}
          {trace.prompt_text ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.prompt_text}</pre> : null}
          {trace.raw_response ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.raw_response}</pre> : null}
        </Space>
      ) }))} />
    </Card>
  );
}
