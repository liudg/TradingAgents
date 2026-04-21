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

export function MarketMonitorRunDetailPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const runQuery = useMarketMonitorRun(runId);
  const logsQuery = useMarketMonitorRunLogs(runId);
  const promptTracesQuery = useMarketMonitorPromptTraces(runId);
  const factSheetArtifactQuery = useMarketMonitorArtifact(runId, "fact_sheet", Boolean(runId));
  const recoverMutation = useRecoverMarketMonitorRun();
  const run = runQuery.data;

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
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/monitor/history")}>
            返回历史列表
          </Button>
        }
      />
    );
  }

  const snapshot = run.snapshot;
  const history = run.history;
  const dataStatus = run.data_status;
  const dataStatusSourceCoverage = dataStatus?.source_coverage || snapshot?.source_coverage;
  const dataStatusDegradedFactors = dataStatus?.degraded_factors || snapshot?.degraded_factors || [];
  const dataStatusNotes = dataStatus?.notes || snapshot?.notes || [];
  const dataStatusOpenGaps = dataStatus?.open_gaps || [];
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
          <Descriptions.Item label="交易日">{run.as_of_date}</Descriptions.Item>
          <Descriptions.Item label="状态">{getStatusText(run.status)}</Descriptions.Item>
          <Descriptions.Item label="历史天数">{run.days ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="生成时间">{formatDateTime(run.generated_at)}</Descriptions.Item>
          <Descriptions.Item label="开始时间">{formatDateTime(run.started_at)}</Descriptions.Item>
          <Descriptions.Item label="完成时间">{formatDateTime(run.finished_at)}</Descriptions.Item>
          <Descriptions.Item label="数据新鲜度">{run.data_freshness || "-"}</Descriptions.Item>
          <Descriptions.Item label="完整度">{run.source_completeness || "-"}</Descriptions.Item>
          <Descriptions.Item label="Regime">{run.regime_label || "-"}</Descriptions.Item>
          <Descriptions.Item label="force_refresh">{run.request.force_refresh ? "true" : "false"}</Descriptions.Item>
          <Descriptions.Item label="可恢复">{run.recoverable ? "是" : "否"}</Descriptions.Item>
          <Descriptions.Item label="Prompt traces">{run.prompt_traces.length}</Descriptions.Item>
        </Descriptions>
        {run.error_message ? (
          <Alert type="error" showIcon style={{ marginTop: 16 }} message="运行失败" description={run.error_message} />
        ) : null}
      </Card>

      <StageTimelineBlock stages={run.stage_results} />

      <FactSheetBlock
        factSheet={run.fact_sheet || snapshot?.fact_sheet || dataStatus?.fact_sheet || (factSheetArtifactQuery.data as never)}
      />

      <PromptTraceBlock traces={promptTracesQuery.data || run.prompt_traces} />

      {snapshot ? <ExecutionCardBlock card={snapshot.execution_card} /> : null}

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
            <StyleCardBlock card={snapshot.style_effectiveness} />
          </Col>
          <Col xs={24} lg={12}>
            <PanicCardBlock card={snapshot.panic_reversal_score} />
          </Col>
        </Row>
      ) : null}

      {snapshot ? (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <EventRiskBlock card={snapshot.event_risk_flag} />
          </Col>
          {dataStatusSourceCoverage ? (
            <Col xs={24} lg={12}>
              <DataStatusBlock
                sourceCoverage={dataStatusSourceCoverage}
                degradedFactors={dataStatusDegradedFactors}
                notes={dataStatusNotes}
                openGaps={dataStatusOpenGaps}
              />
            </Col>
          ) : null}
        </Row>
      ) : null}

      {!snapshot && dataStatusSourceCoverage ? (
        <DataStatusBlock
          sourceCoverage={dataStatusSourceCoverage}
          degradedFactors={dataStatusDegradedFactors}
          notes={dataStatusNotes}
          openGaps={dataStatusOpenGaps}
        />
      ) : null}

      {history ? <HistoryBlock points={history.points} /> : null}

      {historyArtifacts.length ? <HistoryArtifactsBlock items={historyArtifacts} /> : null}

      <Card className="page-card" title="执行日志">
        <List
          dataSource={logsQuery.data || []}
          locale={{ emptyText: "暂无日志" }}
          renderItem={(item) => (
            <List.Item>
              <Space direction="vertical" size={2} style={{ width: "100%" }}>
                <Typography.Text type="secondary">
                  {formatDateTime(item.timestamp)} [{item.level}]
                </Typography.Text>
                <Typography.Text>{item.content}</Typography.Text>
              </Space>
            </List.Item>
          )}
        />
      </Card>
    </Space>
  );
}
