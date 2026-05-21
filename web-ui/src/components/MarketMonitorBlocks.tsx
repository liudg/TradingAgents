import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Input,
  List,
  Popover,
  Progress,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { ExclamationCircleOutlined } from "@ant-design/icons";
import { type ReactNode, useMemo, useState } from "react";

import { fetchMarketMonitorArtifact } from "../api/client";
import {
  MarketMonitorArtifactPayload,
  MarketMonitorEventFact,
  MarketMonitorExecutionCard,
  MarketMonitorEventRiskFlag,
  MarketMonitorFactSheet,
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

function formatUnknownValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

function metricEntries(value: Record<string, unknown> | undefined) {
  return Object.entries(value || {}).map(([key, item]) => ({ key, value: item }));
}

function downloadJson(filename: string, payload: MarketMonitorArtifactPayload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${filename}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function renderReasoningBlock(card: { score_reasoning?: string | null; action_hint?: string | null; decision_reasoning?: string | null; risks?: string[]; confidence?: number | null }) {
  const reasoning = card.score_reasoning || card.decision_reasoning;
  if (!reasoning && !card.action_hint && !card.risks?.length && card.confidence === undefined) {
    return null;
  }
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {reasoning ? <Typography.Text>{reasoning}</Typography.Text> : null}
      {card.action_hint ? <Typography.Text>操作含义：{card.action_hint}</Typography.Text> : null}
      {card.confidence !== undefined ? <Tag color="purple">置信度 {confidenceText(card.confidence)}</Tag> : null}
      {card.risks?.length ? <List size="small" header="风险与缺口" dataSource={card.risks} renderItem={(item) => <List.Item>{item}</List.Item>} /> : null}
    </Space>
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
        <Space wrap>
          <Tag color={scoreTagColor(props.card.score)}>最终分 {props.card.score.toFixed(1)}</Tag>
          <Tag>基础分 {props.card.deterministic_score.toFixed(1)}</Tag>
        </Space>
        {props.card.score_adjustment ? <Alert type="info" showIcon message={`评分调整 ${props.card.score_adjustment.value}`} description={props.card.score_adjustment.reason} /> : null}
        <Typography.Text strong>策略手法层</Typography.Text>
        <Space wrap><Tag color="success">最佳手法 {props.card.tactic_layer.top_tactic}</Tag><Tag color="error">回避手法 {props.card.tactic_layer.avoid_tactic}</Tag></Space>
        <List size="small" dataSource={tacticItems} renderItem={({ name, item }) => <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>} />
        <Typography.Text strong>资产风格层</Typography.Text>
        <Space wrap><Tag color="success">偏好 {props.card.asset_layer.preferred_assets.join("、") || "无"}</Tag><Tag color="warning">回避 {props.card.asset_layer.avoid_assets.join("、") || "无"}</Tag></Space>
        <List size="small" dataSource={assetItems} renderItem={({ name, item }) => <List.Item>{name}：{item.score.toFixed(1)}（5日 {item.delta_5d >= 0 ? "+" : ""}{item.delta_5d.toFixed(1)}）</List.Item>} />
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
          <Tag>基础分 {props.card.deterministic_score.toFixed(1)}</Tag>
          <Tag>极端恐慌 {props.card.panic_extreme_score.toFixed(1)}</Tag>
          <Tag>抛压衰竭 {props.card.selling_exhaustion_score.toFixed(1)}</Tag>
          <Tag>反弹确认 {props.card.reversal_confirmation_score.toFixed(1)}</Tag>
        </Space>
        <Typography.Text>{props.card.action}</Typography.Text>
        <Space wrap>{boolTag("先手仓", props.card.early_entry_allowed)}<Tag>仓位上限 {props.card.max_position_hint}</Tag><Tag>止损 {props.card.stop_loss}</Tag><Tag>已保持 {props.card.refreshes_held} 次刷新</Tag></Space>
        <Typography.Text type="secondary">盈利规则：{props.card.profit_rule}</Typography.Text>
        {props.card.system_risk_override ? <Alert type="warning" showIcon message={props.card.system_risk_override} /> : null}
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

function HistoryTrendChart(props: { points: MarketMonitorHistoryPoint[] }) {
  const series = [
    { key: "long_term_score", label: "长线", color: "#1677ff" },
    { key: "short_term_score", label: "短线", color: "#52c41a" },
    { key: "system_risk_score", label: "系统风险", color: "#fa8c16" },
    { key: "panic_reversal_score", label: "恐慌反转", color: "#722ed1" },
  ] as const;
  const width = 640;
  const height = 180;
  const padding = 24;
  const sorted = [...props.points].sort((a, b) => a.trade_date.localeCompare(b.trade_date));
  if (sorted.length < 2) {
    return <Alert type="info" showIcon message="历史点不足，暂无法绘制趋势图" />;
  }
  const x = (index: number) => padding + (index / Math.max(1, sorted.length - 1)) * (width - padding * 2);
  const y = (score: number) => height - padding - (score / 100) * (height - padding * 2);
  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <svg role="img" aria-label="市场监控分数趋势图" viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", maxWidth: width, height }}>
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line x1={padding} x2={width - padding} y1={y(tick)} y2={y(tick)} stroke="#f0f0f0" />
            <text x={4} y={y(tick) + 4} fontSize="10" fill="#8c8c8c">{tick}</text>
          </g>
        ))}
        {series.map((item) => (
          <polyline
            key={item.key}
            fill="none"
            stroke={item.color}
            strokeWidth="2"
            points={sorted.map((point, index) => `${x(index)},${y(point[item.key])}`).join(" ")}
          />
        ))}
      </svg>
      <Space wrap>{series.map((item) => <Tag key={item.key} color={item.color}>{item.label}</Tag>)}</Space>
    </Space>
  );
}

export function HistoryBlock(props: { points: MarketMonitorHistoryPoint[] }) {
  return (
    <Card className="page-card" title="历史趋势回看">
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <HistoryTrendChart points={props.points} />
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
      </Space>
    </Card>
  );
}

export function HistoryArtifactsBlock(props: { runId: string; items: MarketMonitorHistoryDailyArtifactItem[] }) {
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [payload, setPayload] = useState<MarketMonitorArtifactPayload | null>(null);
  const [loadingName, setLoadingName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadArtifact = async (artifactName: string) => {
    setLoadingName(artifactName);
    setError(null);
    try {
      const artifactPayload = await fetchMarketMonitorArtifact(props.runId, artifactName);
      setSelectedName(artifactName);
      setPayload(artifactPayload);
      return artifactPayload;
    } catch (artifactError) {
      setError(artifactError instanceof Error ? artifactError.message : String(artifactError));
      return null;
    } finally {
      setLoadingName(null);
    }
  };

  const downloadArtifact = async (artifactName: string) => {
    const artifactPayload = selectedName === artifactName && payload ? payload : await loadArtifact(artifactName);
    if (artifactPayload) downloadJson(artifactName, artifactPayload);
  };

  return (
    <Card className="page-card" title="History 日级产物">
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {error ? <Alert type="error" showIcon message="产物加载失败" description={error} /> : null}
        <List size="small" dataSource={props.items} locale={{ emptyText: "暂无日级产物" }} renderItem={(item) => (
          <List.Item>
            <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
              <Typography.Text strong>{item.tradeDate}</Typography.Text>
              <Space wrap>
                <Tag color={item.artifactType === "snapshot" ? "blue" : "purple"}>{item.artifactType === "snapshot" ? "snapshot" : "fact_sheet"}</Tag>
                <Typography.Text copyable>{item.artifactName}</Typography.Text>
                <Button size="small" loading={loadingName === item.artifactName} onClick={() => loadArtifact(item.artifactName)}>查看</Button>
                <Button size="small" onClick={() => downloadArtifact(item.artifactName)}>下载</Button>
              </Space>
            </Space>
          </List.Item>
        )} />
        {selectedName && payload ? (
          <Collapse items={[{ key: selectedName, label: `产物内容：${selectedName}`, children: <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(payload, null, 2)}</pre> }]} />
        ) : null}
      </Space>
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
  const factSheet = props.factSheet;
  if (!factSheet) return null;
  const symbols = factSheet.local_facts.symbols && typeof factSheet.local_facts.symbols === "object"
    ? metricEntries(factSheet.local_facts.symbols as Record<string, unknown>)
    : [];
  const marketProxies = factSheet.local_facts.market_proxies && typeof factSheet.local_facts.market_proxies === "object"
    ? metricEntries(factSheet.local_facts.market_proxies as Record<string, unknown>)
    : [];
  return (
    <Card className="page-card" title="Fact Sheet">
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Descriptions bordered size="small" column={1}>
          <Descriptions.Item label="美东交易日">{factSheet.as_of_date}</Descriptions.Item>
          <Descriptions.Item label="生成时间">{factSheet.generated_at}</Descriptions.Item>
          <Descriptions.Item label="Open gaps">{factSheet.open_gaps.join("、") || "无"}</Descriptions.Item>
          <Descriptions.Item label="Notes">{factSheet.notes.join("、") || "无"}</Descriptions.Item>
        </Descriptions>
        <Collapse items={[
          {
            key: "event_fact_sheet",
            label: `Event fact sheet（${factSheet.event_fact_sheet.length}）`,
            children: <EventFactSheetBlock events={factSheet.event_fact_sheet} />,
          },
          {
            key: "local_facts",
            label: "Local facts",
            children: (
              <Space direction="vertical" size={12} style={{ width: "100%" }}>
                <List size="small" header="Symbols" dataSource={symbols} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item><Typography.Text strong>{item.key}</Typography.Text><Typography.Text>{formatUnknownValue(item.value)}</Typography.Text></List.Item>} />
                <List size="small" header="Market proxies" dataSource={marketProxies} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item><Typography.Text strong>{item.key}</Typography.Text><Typography.Text>{formatUnknownValue(item.value)}</Typography.Text></List.Item>} />
              </Space>
            ),
          },
          {
            key: "derived_metrics",
            label: "Derived metrics",
            children: <List size="small" dataSource={metricEntries(factSheet.derived_metrics)} locale={{ emptyText: "无" }} renderItem={(item) => <List.Item><Typography.Text strong>{item.key}</Typography.Text><Typography.Text>{formatUnknownValue(item.value)}</Typography.Text></List.Item>} />,
          },
        ]} />
      </Space>
    </Card>
  );
}

export function PromptTraceBlock(props: { traces: MarketMonitorPromptTrace[] }) {
  const [query, setQuery] = useState("");
  const [cardType, setCardType] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [model, setModel] = useState<string>("all");
  const [provider, setProvider] = useState<string>("all");
  const cardOptions = useMemo(() => Array.from(new Set(props.traces.map((trace) => trace.card_type || "unknown"))).sort(), [props.traces]);
  const modelOptions = useMemo(() => Array.from(new Set(props.traces.map((trace) => trace.model || "unknown"))).sort(), [props.traces]);
  const providerOptions = useMemo(() => Array.from(new Set(props.traces.map((trace) => trace.provider || "unknown"))).sort(), [props.traces]);
  const filteredTraces = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return props.traces.filter((trace) => {
      if (cardType !== "all" && (trace.card_type || "unknown") !== cardType) return false;
      if (status === "parsed" && !trace.parsed_ok) return false;
      if (status === "fallback" && trace.parsed_ok) return false;
      if (model !== "all" && (trace.model || "unknown") !== model) return false;
      if (provider !== "all" && (trace.provider || "unknown") !== provider) return false;
      if (!normalizedQuery) return true;
      return [trace.stage, trace.card_type, trace.model, trace.provider, trace.input_summary, trace.error]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));
    });
  }, [props.traces, query, cardType, status, model, provider]);
  return (
    <Card id="prompt-traces" className="page-card" title={`Prompt Traces（${filteredTraces.length}/${props.traces.length}）`}>
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Input.Search allowClear placeholder="搜索 card/status/model/provider" style={{ width: 260 }} value={query} onChange={(event) => setQuery(event.target.value)} />
          <Select value={cardType} style={{ width: 160 }} onChange={setCardType} options={[{ label: "全部卡片", value: "all" }, ...cardOptions.map((value) => ({ label: value, value }))]} />
          <Select value={status} style={{ width: 140 }} onChange={setStatus} options={[{ label: "全部状态", value: "all" }, { label: "parsed", value: "parsed" }, { label: "fallback", value: "fallback" }]} />
          <Select value={model} style={{ width: 180 }} onChange={setModel} options={[{ label: "全部模型", value: "all" }, ...modelOptions.map((value) => ({ label: value, value }))]} />
          <Select value={provider} style={{ width: 160 }} onChange={setProvider} options={[{ label: "全部 Provider", value: "all" }, ...providerOptions.map((value) => ({ label: value, value }))]} />
        </Space>
        <Collapse items={filteredTraces.map((trace, index) => ({ key: `${trace.stage}-${trace.card_type || index}`, label: `${trace.stage}${trace.card_type ? ` / ${trace.card_type}` : ""}`, children: (
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Space wrap><Tag>{trace.model || "unknown model"}</Tag><Tag color={trace.parsed_ok ? "success" : "error"}>{trace.parsed_ok ? "parsed" : "fallback"}</Tag>{trace.provider ? <Tag>{trace.provider}</Tag> : null}{trace.latency_ms ? <Tag>{trace.latency_ms} ms</Tag> : null}{Object.keys(trace.token_usage || {}).length ? <Tag color="purple">tokens {Object.values(trace.token_usage).reduce((sum, value) => sum + value, 0)}</Tag> : null}</Space>
            {trace.input_summary ? <Typography.Text>{trace.input_summary}</Typography.Text> : null}
            {trace.error ? <Alert type="error" showIcon message={trace.error} /> : null}
            {trace.prompt_text ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.prompt_text}</pre> : null}
            {trace.raw_response ? <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trace.raw_response}</pre> : null}
          </Space>
        ) }))} />
      </Space>
    </Card>
  );
}
