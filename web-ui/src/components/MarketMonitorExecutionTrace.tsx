import { Alert, Card, List, Space, Tag, Typography } from "antd";

import { MarketMonitorTraceLogEntry } from "../api/types";
import { formatDateTime } from "../utils/format";

type TraceStepStatus = "waiting" | "running" | "completed" | "failed";

interface MarketMonitorExecutionTraceProps {
  logs: MarketMonitorTraceLogEntry[];
  isLoading: boolean;
  isFetching: boolean;
  isCompleted: boolean;
  errorMessage?: string | null;
}

interface TraceStepDefinition {
  key: string;
  title: string;
  levels: string[];
}

interface TraceStepItem extends TraceStepDefinition {
  status: TraceStepStatus;
  timestamp: string | null;
  content: string;
  rawLevel: string | null;
}

const TRACE_STEPS: TraceStepDefinition[] = [
  { key: "request", title: "接收请求", levels: ["Request"] },
  { key: "cache", title: "检查缓存", levels: ["Cache"] },
  { key: "dataset", title: "准备市场数据", levels: ["Dataset"] },
  { key: "rule", title: "生成规则快照", levels: ["Rule"] },
  { key: "overlay", title: "生成模型叠加", levels: ["Overlay"] },
  { key: "merge", title: "合并最终决策", levels: ["Merge"] },
  { key: "response", title: "返回结果", levels: ["Response"] },
];

const STEP_INDEX_BY_LEVEL = new Map(
  TRACE_STEPS.flatMap((step, index) => step.levels.map((level) => [level, index] as const)),
);

function getStepStatusTag(status: TraceStepStatus) {
  if (status === "completed") return <Tag color="success">已完成</Tag>;
  if (status === "running") return <Tag color="processing">进行中</Tag>;
  if (status === "failed") return <Tag color="error">执行失败</Tag>;
  return <Tag>等待中</Tag>;
}

function buildTraceSteps(
  logs: MarketMonitorTraceLogEntry[],
  isCompleted: boolean,
): TraceStepItem[] {
  const latestByStep = new Map<number, MarketMonitorTraceLogEntry>();
  let lastMatchedStepIndex = -1;
  let errorLog: MarketMonitorTraceLogEntry | null = null;

  for (const log of logs) {
    if (log.level === "Error") {
      errorLog = log;
      continue;
    }

    const stepIndex = STEP_INDEX_BY_LEVEL.get(log.level);
    if (stepIndex === undefined) continue;
    latestByStep.set(stepIndex, log);
    lastMatchedStepIndex = Math.max(lastMatchedStepIndex, stepIndex);
  }

  const errorStepIndex =
    errorLog && lastMatchedStepIndex >= 0 ? lastMatchedStepIndex : null;

  return TRACE_STEPS.map((step, index) => {
    const latest = latestByStep.get(index);
    let status: TraceStepStatus = "waiting";

    if (errorStepIndex !== null && index === errorStepIndex) {
      status = "failed";
    } else if (latest) {
      if (isCompleted || index < lastMatchedStepIndex) {
        status = "completed";
      } else {
        status = "running";
      }
    }

    return {
      ...step,
      status,
      timestamp: (errorStepIndex !== null && index === errorStepIndex ? errorLog?.timestamp : latest?.timestamp) ?? null,
      content: (errorStepIndex !== null && index === errorStepIndex ? errorLog?.content : latest?.content) ?? "",
      rawLevel: (errorStepIndex !== null && index === errorStepIndex ? errorLog?.level : latest?.level) ?? null,
    };
  });
}

function renderTraceStep(step: TraceStepItem) {
  return (
    <List.Item>
      <Space direction="vertical" size={6} style={{ width: "100%" }}>
        <Space size={8} wrap>
          <Typography.Text strong>{step.title}</Typography.Text>
          {getStepStatusTag(step.status)}
          {step.timestamp ? (
            <Typography.Text type="secondary">
              {formatDateTime(step.timestamp)}
            </Typography.Text>
          ) : null}
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {step.content || "等待当前步骤开始。"}
        </Typography.Paragraph>
      </Space>
    </List.Item>
  );
}

export function MarketMonitorExecutionTrace(
  props: MarketMonitorExecutionTraceProps,
) {
  const steps = buildTraceSteps(props.logs, props.isCompleted);

  return (
    <Card
      className="page-card"
      title="执行过程"
      extra={
        props.isFetching ? <Tag color="processing">步骤更新中</Tag> : null
      }
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {props.errorMessage ? (
          <Alert
            type="warning"
            showIcon
            message="执行日志加载失败"
            description={props.errorMessage}
          />
        ) : null}
        {!props.logs.length && props.isLoading ? (
          <Alert
            type="info"
            showIcon
            message="正在分析市场状态，步骤会实时展示在这里。"
          />
        ) : null}
        <List
          dataSource={steps}
          locale={{ emptyText: "暂无执行步骤" }}
          renderItem={renderTraceStep}
        />
      </Space>
    </Card>
  );
}

export { buildTraceSteps };
