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

import { useMarketMonitorRun, useMarketMonitorRunLogs } from "../api/hooks";
import {
  DataStatusBlock,
  EventRiskBlock,
  ExecutionCardBlock,
  HistoryBlock,
  PanicCardBlock,
  ScoreCardBlock,
  StyleCardBlock,
} from "../components/MarketMonitorBlocks";
import { extractErrorMessage, formatDateTime, getStatusColor, getStatusText } from "../utils/format";

export function MarketMonitorRunDetailPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const runQuery = useMarketMonitorRun(runId);
  const logsQuery = useMarketMonitorRunLogs(runId);
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
            <Button icon={<ReloadOutlined />} loading={runQuery.isFetching || logsQuery.isFetching} onClick={() => { runQuery.refetch(); logsQuery.refetch(); }}>
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
        </Descriptions>
        {run.error_message ? (
          <Alert type="error" showIcon style={{ marginTop: 16 }} message="运行失败" description={run.error_message} />
        ) : null}
      </Card>

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
          <Col xs={24} lg={12}>
            <DataStatusBlock
              sourceCoverage={dataStatus?.source_coverage || snapshot.source_coverage}
              degradedFactors={dataStatus?.degraded_factors || snapshot.degraded_factors}
              notes={dataStatus?.notes || snapshot.notes}
              openGaps={dataStatus?.open_gaps || []}
            />
          </Col>
        </Row>
      ) : null}

      {history ? <HistoryBlock points={history.points} /> : null}

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
