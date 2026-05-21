import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  List,
  Result,
  Row,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import {
  useMarketMonitorArtifact,
  useMarketMonitorPromptTraces,
  useMarketMonitorRun,
  useMarketMonitorRunLogs,
  useRecoverMarketMonitorRun,
} from "../api/hooks";
import {
  DataStatusBlock,
  EventFactSheetBlock,
  EventRiskBlock,
  ExecutionCardBlock,
  FactSheetBlock,
  HistoryArtifactsBlock,
  HistoryBlock,
  PanicCardBlock,
  PromptTraceBlock,
  ScoreCardBlock,
  StageTimelineBlock,
  StyleCardBlock,
} from "../components/MarketMonitorBlocks";
import { extractErrorMessage, formatDateTime, getStatusColor, getStatusText } from "../utils/format";

function getLogLevelColor(level: string) {
  const normalized = level.toLowerCase();
  if (normalized === "error") return "red";
  if (normalized === "warning" || normalized === "warn") return "orange";
  if (normalized === "system" || normalized === "info") return "blue";
  return "default";
}

function getLogLevelText(level: string) {
  const normalized = level.toLowerCase();
  if (normalized === "error") return "错误";
  if (normalized === "warning" || normalized === "warn") return "警告";
  if (normalized === "system" || normalized === "info") return "系统";
  return level;
}

export function MarketMonitorRunDetailPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const runQuery = useMarketMonitorRun(runId);
  const run = runQuery.data;
  const logsQuery = useMarketMonitorRunLogs(runId, run?.status);
  const promptTracesQuery = useMarketMonitorPromptTraces(runId, run?.status);
  const factSheetArtifactQuery = useMarketMonitorArtifact(runId, "fact_sheet", Boolean(runId));
  const recoverMutation = useRecoverMarketMonitorRun();

  if (runQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (runQuery.isError || !run) {
    return (
      <Result
        status="error"
        title="市场监控运行详情加载失败"
        subTitle={extractErrorMessage(runQuery.error)}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => runQuery.refetch()}>
              重试
            </Button>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/monitor/history")}>
              返回历史列表
            </Button>
          </Space>
        }
      />
    );
  }

  const isActive = run.status === "pending" || run.status === "running";
  const snapshot = run.snapshot;
  const history = run.history;
  const dataStatus = run.data_status;
  const inputDataStatus = dataStatus?.input_data_status || snapshot?.input_data_status;
  const missingData = dataStatus?.missing_data || snapshot?.missing_data || [];
  const dataRisks = dataStatus?.risks || snapshot?.risks || [];
  const dataStatusOpenGaps = dataStatus?.open_gaps || snapshot?.fact_sheet?.open_gaps || [];
  const logs = logsQuery.data || [];
  const historyArtifacts = Object.keys(run.manifest?.artifact_paths || {})
    .filter((name) => name.startsWith("history_snapshot_") || name.startsWith("history_fact_sheet_"))
    .sort()
    .map((name) => ({
      artifactName: name,
      tradeDate: name.replace(/^history_(?:snapshot|fact_sheet)_/, ""),
      artifactType: name.startsWith("history_snapshot_") ? "snapshot" as const : "fact_sheet" as const,
    }));

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>市场监控运行详情</span>
            <Tag color={getStatusColor(run.status)}>{getStatusText(run.status)}</Tag>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/monitor/history")}>
              返回历史
            </Button>
            {run.recoverable ? (
              <Button loading={recoverMutation.isPending} onClick={() => recoverMutation.mutate(runId)}>
                恢复运行
              </Button>
            ) : null}
            <Button icon={<ReloadOutlined />} loading={runQuery.isFetching || logsQuery.isFetching || promptTracesQuery.isFetching || factSheetArtifactQuery.isFetching || recoverMutation.isPending} onClick={() => { runQuery.refetch(); logsQuery.refetch(); promptTracesQuery.refetch(); factSheetArtifactQuery.refetch(); }}>
              刷新
            </Button>
          </Space>
        }
      >
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="Run ID" span={2}>
            <Typography.Text copyable>{run.run_id}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="触发入口">{run.trigger_endpoint}</Descriptions.Item>
          <Descriptions.Item label="美东交易日">{run.as_of_date}</Descriptions.Item>
          <Descriptions.Item label="状态">{getStatusText(run.status)}</Descriptions.Item>
          <Descriptions.Item label="历史天数">{run.days ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="生成时间">{formatDateTime(run.generated_at)}</Descriptions.Item>
          <Descriptions.Item label="开始时间">{formatDateTime(run.started_at)}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{formatDateTime(run.finished_at)}</Descriptions.Item>
          <Descriptions.Item label="数据新鲜度">{run.data_freshness || "-"}</Descriptions.Item>
          <Descriptions.Item label="Prompt version">{snapshot?.prompt_version || "-"}</Descriptions.Item>
          <Descriptions.Item label="Model">{snapshot?.model_name || run.manifest?.llm_config?.model || "-"}</Descriptions.Item>
          <Descriptions.Item label="Regime">{run.regime_label || "-"}</Descriptions.Item>
          <Descriptions.Item label="V2.3.1 缺失数据">{missingData.length}</Descriptions.Item>
          <Descriptions.Item label="force_refresh">{run.request.force_refresh ? "true" : "false"}</Descriptions.Item>
          <Descriptions.Item label="可恢复">{run.recoverable ? "是" : "否"}</Descriptions.Item>
          <Descriptions.Item label="Prompt traces">{run.prompt_traces.length}</Descriptions.Item>
        </Descriptions>
        {isActive ? (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="运行正在后台执行"
            description="本页会自动刷新阶段、日志、Prompt traces 和最终产物；完成或失败后轮询会停止。"
          />
        ) : null}
        {run.error_message ? (
          <Alert type="error" showIcon style={{ marginTop: 16 }} message="运行失败" description={run.error_message} />
        ) : null}
      </Card>

      <StageTimelineBlock stages={run.stage_results} />

      <FactSheetBlock
        factSheet={run.fact_sheet || snapshot?.fact_sheet || dataStatus?.fact_sheet || (factSheetArtifactQuery.data as never)}
      />

      <PromptTraceBlock traces={promptTracesQuery.data || run.prompt_traces} />

      {isActive && !snapshot && !history && !dataStatus ? (
        <Alert type="info" showIcon message="等待最终结果" description="当前可先查看阶段时间线和执行日志。" />
      ) : null}

      {snapshot ? <ExecutionCardBlock card={snapshot.execution_card} /> : null}
      {snapshot ? <EventRiskBlock card={snapshot.execution_card.event_risk_flag} /> : null}

      {snapshot ? (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={8}>
            <ScoreCardBlock title="长线环境卡" helpKey="long_term_card" card={snapshot.long_term_score} />
          </Col>
          <Col xs={24} lg={8}>
            <ScoreCardBlock title="短线环境卡" helpKey="short_term_card" card={snapshot.short_term_score} />
          </Col>
          <Col xs={24} lg={8}>
            <ScoreCardBlock title="系统风险卡" helpKey="system_risk_card" card={snapshot.system_risk_score} />
          </Col>
        </Row>
      ) : null}

      {snapshot ? (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <StyleCardBlock card={snapshot.style_effectiveness} />
              <EventFactSheetBlock events={snapshot.event_fact_sheet} />
            </Space>
          </Col>
          <Col xs={24} lg={12}>
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <PanicCardBlock card={snapshot.panic_reversal_score} />
              {inputDataStatus ? (
                <DataStatusBlock
                  inputDataStatus={inputDataStatus}
                  missingData={missingData}
                  risks={dataRisks}
                  openGaps={dataStatusOpenGaps}
                />
              ) : null}
            </Space>
          </Col>
        </Row>
      ) : null}

      {!snapshot && inputDataStatus ? (
        <DataStatusBlock
          inputDataStatus={inputDataStatus}
          missingData={missingData}
          risks={dataRisks}
          openGaps={dataStatusOpenGaps}
        />
      ) : null}

      {history ? <HistoryBlock points={history.points} /> : null}

      {historyArtifacts.length ? <HistoryArtifactsBlock runId={runId} items={historyArtifacts} /> : null}

      <Card
        className="page-card"
        title={`执行日志（${logs.length} 条）`}
        extra={
          <Space>
            {isActive ? <Typography.Text type="secondary">运行中每 2 秒自动刷新</Typography.Text> : null}
            <Button icon={<ReloadOutlined />} loading={logsQuery.isFetching} onClick={() => logsQuery.refetch()}>
              刷新日志
            </Button>
          </Space>
        }
      >
        <List
          dataSource={logs}
          locale={{ emptyText: "暂无日志" }}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Space size={8} wrap>
                  <Typography.Text type="secondary">{formatDateTime(item.timestamp)}</Typography.Text>
                  <Tag color={getLogLevelColor(item.level)}>{getLogLevelText(item.level)}</Tag>
                  <Typography.Text type="secondary">#{item.line_no}</Typography.Text>
                </Space>
                <Typography.Text style={{ whiteSpace: "pre-wrap" }}>{item.content}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
