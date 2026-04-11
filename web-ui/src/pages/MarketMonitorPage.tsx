import {
  Alert,
  Button,
  Card,
  Col,
  List,
  Popover,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { ExclamationCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { type ReactNode } from "react";

import {
  useMarketMonitorHistory,
  useMarketMonitorSnapshot,
  useMarketMonitorTraceDetail,
  useMarketMonitorTraceLogs,
  useMarketMonitorTraces,
} from "../api/hooks";
import {
  MarketAssessmentCard,
  MarketAssessmentExecutionCard,
} from "../api/types";
import { MarketMonitorExecutionTrace } from "../components/MarketMonitorExecutionTrace";
import {
  MARKET_MONITOR_CARD_HELP,
  type MarketMonitorCardHelpKey,
} from "../config/marketMonitorCardHelp";
import { extractErrorMessage, formatDateTime } from "../utils/format";

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

function confidenceTag(confidence: number) {
  if (confidence >= 0.8) return "success";
  if (confidence >= 0.6) return "warning";
  return "default";
}

function AssessmentCardBlock(props: {
  title: string;
  helpKey: MarketMonitorCardHelpKey;
  card: MarketAssessmentCard;
}) {
  return (
    <Card
      className="section-card market-assessment-card"
      title={<CardTitleWithHelp title={props.title} helpKey={props.helpKey} />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">{props.card.label}</Tag>
          <Tag color={confidenceTag(props.card.confidence)}>
            置信度 {props.card.confidence.toFixed(2)}
          </Tag>
          <Tag>完整度 {props.card.data_completeness}</Tag>
        </Space>
        <Typography.Text>{props.card.summary}</Typography.Text>
        <Typography.Text type="secondary">{props.card.action}</Typography.Text>
        <Typography.Text strong>关键证据</Typography.Text>
        <List
          size="small"
          dataSource={props.card.key_evidence}
          locale={{ emptyText: "无" }}
          renderItem={(item) => <List.Item>{item}</List.Item>}
        />
      </Space>
    </Card>
  );
}

function ExecutionCardBlock(props: { card: MarketAssessmentExecutionCard }) {
  return (
    <Card
      className="page-card"
      title={<CardTitleWithHelp title="执行建议" helpKey="execution_card" />}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        <Space wrap>
          <Tag color="blue">{props.card.label}</Tag>
          <Tag color={confidenceTag(props.card.confidence)}>
            置信度 {props.card.confidence.toFixed(2)}
          </Tag>
          <Tag>总仓位 {props.card.total_exposure_range}</Tag>
          <Tag>风险预算 {props.card.daily_risk_budget}</Tag>
        </Space>
        <Typography.Text>{props.card.summary}</Typography.Text>
        <Space wrap>
          <Tag color={props.card.new_position_allowed ? "success" : "error"}>
            新开仓 {props.card.new_position_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag color={props.card.chase_breakout_allowed ? "success" : "error"}>
            追突破 {props.card.chase_breakout_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag color={props.card.dip_buy_allowed ? "success" : "error"}>
            低吸 {props.card.dip_buy_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag color={props.card.overnight_allowed ? "success" : "error"}>
            隔夜 {props.card.overnight_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag color={props.card.leverage_allowed ? "success" : "error"}>
            杠杆 {props.card.leverage_allowed ? "允许" : "禁止"}
          </Tag>
          <Tag>单票上限 {props.card.single_position_cap}</Tag>
        </Space>
        <Typography.Text type="secondary">{props.card.action}</Typography.Text>
      </Space>
    </Card>
  );
}

export function MarketMonitorPage() {
  const snapshotQuery = useMarketMonitorSnapshot();
  const historyQuery = useMarketMonitorHistory(true);
  const runningTracesQuery = useMarketMonitorTraces(
    "running",
    !snapshotQuery.data?.trace_id,
    1,
  );
  const activeTraceId =
    snapshotQuery.data?.trace_id ?? runningTracesQuery.data?.[0]?.trace_id;
  const traceDetailQuery = useMarketMonitorTraceDetail(
    activeTraceId,
    Boolean(activeTraceId),
  );
  const traceLogsQuery = useMarketMonitorTraceLogs(
    activeTraceId,
    Boolean(activeTraceId),
  );

  if (snapshotQuery.isError && !snapshotQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="市场监控加载失败"
        description={extractErrorMessage(snapshotQuery.error)}
      />
    );
  }

  const snapshot = snapshotQuery.data;
  const assessment = snapshot?.assessment;
  const traceLogs = Array.isArray(traceLogsQuery.data)
    ? traceLogsQuery.data
    : [];
  const hasTerminalTraceLog = traceLogs.some(
    (item) => item.level === "Response" || item.level === "Error",
  );
  const isSnapshotPending = snapshotQuery.isLoading && !snapshot;
  const isTraceLoading =
    Boolean(activeTraceId) &&
    ((traceLogsQuery.isLoading && traceLogs.length === 0) ||
      traceDetailQuery.isLoading);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title="市场监控"
        extra={
          <a
            className="page-card-extra-button ant-btn ant-btn-default"
            onClick={(event) => {
              event.preventDefault();
              snapshotQuery.refetch();
              historyQuery.refetch();
            }}
          >
            <ReloadOutlined /> 刷新
          </a>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          {isSnapshotPending ? (
            <Alert
              type="info"
              showIcon
              message="正在生成市场裁决"
              description="系统会先读取本地数据，再补充外部搜索后输出结构化结论。"
            />
          ) : snapshot && assessment ? (
            <>
              <Space wrap>
                <Tag>更新时间 {formatDateTime(snapshot.timestamp)}</Tag>
                <Tag>交易日 {snapshot.as_of_date}</Tag>
                <Tag color={confidenceTag(snapshot.overall_confidence)}>
                  整体置信度 {snapshot.overall_confidence.toFixed(2)}
                </Tag>
              </Space>
              <Typography.Text>{assessment.execution_card.summary}</Typography.Text>
            </>
          ) : (
            <Alert
              type="warning"
              showIcon
              message="暂未获取到市场监控快照"
              description="可以先查看执行过程，待后端完成后页面会自动刷新结果。"
            />
          )}
        </Space>
      </Card>

      {assessment ? (
        <>
          <ExecutionCardBlock card={assessment.execution_card} />

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={8}>
              <AssessmentCardBlock
                title="长期环境"
                helpKey="long_term_card"
                card={assessment.long_term_card}
              />
            </Col>
            <Col xs={24} lg={8}>
              <AssessmentCardBlock
                title="短线环境"
                helpKey="short_term_card"
                card={assessment.short_term_card}
              />
            </Col>
            <Col xs={24} lg={8}>
              <AssessmentCardBlock
                title="系统风险"
                helpKey="system_risk_card"
                card={assessment.system_risk_card}
              />
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <AssessmentCardBlock
                title="事件风险"
                helpKey="event_risk_card"
                card={assessment.event_risk_card}
              />
            </Col>
            <Col xs={24} lg={12}>
              <AssessmentCardBlock
                title="恐慌模块"
                helpKey="panic_card"
                card={assessment.panic_card}
              />
            </Col>
          </Row>
        </>
      ) : null}

      <MarketMonitorExecutionTrace
        logs={traceLogs}
        traceDetail={traceDetailQuery.data}
        isLoading={isTraceLoading}
        isFetching={
          traceLogsQuery.isFetching ||
          traceDetailQuery.isFetching ||
          runningTracesQuery.isFetching
        }
        isCompleted={hasTerminalTraceLog}
        errorMessage={
          traceLogsQuery.isError
            ? extractErrorMessage(traceLogsQuery.error)
            : traceDetailQuery.isError
              ? extractErrorMessage(traceDetailQuery.error)
              : null
        }
      />
    </Space>
  );
}
