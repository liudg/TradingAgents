import { Alert, Card, List, Space, Tag, Typography } from "antd";

import type { MarketMonitorRunLogEntry } from "../api/types";

interface MarketMonitorTraceDetail {
  status?: string | null;
  request?: Record<string, unknown>;
  cache_decision?: Record<string, unknown>;
  dataset_summary?: Record<string, unknown>;
  context_summary?: Record<string, unknown>;
  assessment_summary?: Record<string, unknown>;
  response_summary?: Record<string, unknown>;
  error?: Record<string, unknown>;
}

type MarketMonitorTraceLogEntry = MarketMonitorRunLogEntry;
import { formatDateTime } from "../utils/format";

type TraceStepStatus = "waiting" | "running" | "completed" | "failed" | "skipped";

interface MarketMonitorExecutionTraceProps {
  logs: MarketMonitorTraceLogEntry[];
  traceDetail?: MarketMonitorTraceDetail | null;
  isLoading: boolean;
  isFetching: boolean;
  isCompleted: boolean;
  errorMessage?: string | null;
}

interface TraceStepDefinition {
  key: string;
  title: string;
  levels: string[];
  stageKey: keyof Pick<
    MarketMonitorTraceDetail,
    | "request"
    | "cache_decision"
    | "dataset_summary"
    | "context_summary"
    | "assessment_summary"
    | "response_summary"
  >;
}

interface TraceStepItem extends TraceStepDefinition {
  status: TraceStepStatus;
  timestamp: string | null;
  content: string;
  rawLevel: string | null;
}

const TRACE_STEPS: TraceStepDefinition[] = [
  { key: "request", title: "接收请求", levels: ["Request"], stageKey: "request" },
  { key: "cache", title: "检查缓存", levels: ["Cache"], stageKey: "cache_decision" },
  { key: "dataset", title: "准备市场数据", levels: ["Dataset"], stageKey: "dataset_summary" },
  { key: "context", title: "组装裁决上下文", levels: ["Context"], stageKey: "context_summary" },
  { key: "assessment", title: "生成 LLM 裁决", levels: ["Assessment"], stageKey: "assessment_summary" },
  { key: "response", title: "返回结果", levels: ["Response"], stageKey: "response_summary" },
];

const STEP_INDEX_BY_LEVEL = new Map(
  TRACE_STEPS.flatMap((step, index) => step.levels.map((level) => [level, index] as const)),
);

const STEP_INDEX_BY_STAGE_KEY = new Map([
  ["input_bundle", 1],
  ["search_slots", 2],
  ["fact_sheet", 2],
  ["judgment_group_a", 4],
  ["judgment_group_b", 4],
  ["execution_decision", 5],
]);

function getStepStatusTag(status: TraceStepStatus) {
  if (status === "completed") return <Tag color="success">已完成</Tag>;
  if (status === "running") return <Tag color="processing">进行中</Tag>;
  if (status === "failed") return <Tag color="error">执行失败</Tag>;
  if (status === "skipped") return <Tag>已跳过</Tag>;
  return <Tag>等待中</Tag>;
}

function hasStageData(value: unknown) {
  return Boolean(value) && typeof value === "object" && Object.keys(value as Record<string, unknown>).length > 0;
}

function getStepIndex(log: MarketMonitorTraceLogEntry) {
  if (log.stage_key) {
    const byStageKey = STEP_INDEX_BY_STAGE_KEY.get(log.stage_key);
    if (byStageKey !== undefined) return byStageKey;
  }
  return STEP_INDEX_BY_LEVEL.get(log.level);
}

function deriveLatestByStage(
  logs: MarketMonitorTraceLogEntry[],
  traceDetail?: MarketMonitorTraceDetail | null,
) {
  const latestByStep = new Map<number, MarketMonitorTraceLogEntry>();
  let errorLog: MarketMonitorTraceLogEntry | null = null;

  for (const log of logs) {
    if (log.level === "Error") {
      errorLog = log;
      continue;
    }

    const stepIndex = getStepIndex(log);
    if (stepIndex === undefined) continue;
    latestByStep.set(stepIndex, log);
  }

  const completedStageIndexes = TRACE_STEPS.flatMap((step, index) =>
    traceDetail && hasStageData(traceDetail[step.stageKey]) ? [index] : [],
  );
  const lastCompletedStageIndex =
    completedStageIndexes.length > 0 ? completedStageIndexes[completedStageIndexes.length - 1] : -1;
  const latestLoggedStepIndex = latestByStep.size > 0 ? Math.max(...latestByStep.keys()) : -1;

  return { latestByStep, errorLog, lastCompletedStageIndex, latestLoggedStepIndex };
}

function isCacheHit(traceDetail?: MarketMonitorTraceDetail | null) {
  return Boolean(traceDetail?.cache_decision && traceDetail.cache_decision["snapshot_cache_hit"]);
}

function buildTraceSteps(
  logs: MarketMonitorTraceLogEntry[],
  traceDetail: MarketMonitorTraceDetail | null | undefined,
  isCompleted: boolean,
): TraceStepItem[] {
  const { latestByStep, errorLog, lastCompletedStageIndex, latestLoggedStepIndex } = deriveLatestByStage(logs, traceDetail);
  const runningStepIndex =
    traceDetail?.status === "running"
      ? Math.max(lastCompletedStageIndex, latestLoggedStepIndex, 0)
      : null;
  const cacheHit = isCacheHit(traceDetail);

  let failedStepIndex: number | null = null;
  if (errorLog) {
    const errorStageIndexFromLogs = [...latestByStep.keys()].sort((a, b) => b - a)[0];
    failedStepIndex =
      typeof errorStageIndexFromLogs === "number"
        ? errorStageIndexFromLogs
        : lastCompletedStageIndex >= 0
          ? lastCompletedStageIndex
          : 0;
  }

  return TRACE_STEPS.map((step, index) => {
    const latest = latestByStep.get(index);
    const completedByStage = traceDetail ? hasStageData(traceDetail[step.stageKey]) : Boolean(latest);
    let status: TraceStepStatus = "waiting";

    if (failedStepIndex !== null && index === failedStepIndex) {
      status = "failed";
    } else if (
      cacheHit &&
      traceDetail?.status === "completed" &&
      (step.key === "dataset" || step.key === "context")
    ) {
      status = "skipped";
    } else if (runningStepIndex !== null && index === runningStepIndex) {
      status = "running";
    } else if (completedByStage) {
      status = "completed";
    } else if (isCompleted && latest) {
      status = "completed";
    }

    return {
      ...step,
      status,
      timestamp:
        (failedStepIndex !== null && index === failedStepIndex ? errorLog?.timestamp : latest?.timestamp) ?? null,
      content:
        (failedStepIndex !== null && index === failedStepIndex ? errorLog?.content : latest?.content) ??
        (status === "skipped" ? "本次命中缓存，当前步骤未执行。" : ""),
      rawLevel: (failedStepIndex !== null && index === failedStepIndex ? errorLog?.level : latest?.level) ?? null,
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
            <Typography.Text type="secondary">{formatDateTime(step.timestamp)}</Typography.Text>
          ) : null}
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {step.content || "等待当前步骤开始。"}
        </Typography.Paragraph>
      </Space>
    </List.Item>
  );
}

export function MarketMonitorExecutionTrace(props: MarketMonitorExecutionTraceProps) {
  const steps = buildTraceSteps(props.logs, props.traceDetail, props.isCompleted);

  return (
    <Card
      className="page-card"
      title="执行过程"
      extra={props.isFetching ? <Tag color="processing">步骤更新中</Tag> : null}
    >
      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {props.errorMessage ? (
          <Alert type="warning" showIcon message="执行日志加载失败" description={props.errorMessage} />
        ) : null}
        {!props.logs.length && props.isLoading ? (
          <Alert
            type="info"
            showIcon
            message="正在分析市场状态，步骤会实时展示在这里。"
          />
        ) : null}
        <List dataSource={steps} locale={{ emptyText: "暂无执行步骤" }} renderItem={renderTraceStep} />
      </Space>
    </Card>
  );
}

export { buildTraceSteps };
