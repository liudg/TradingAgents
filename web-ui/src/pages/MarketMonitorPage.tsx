import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

import {
  useCreateMarketMonitorRun,
  useMarketMonitorRun,
  useMarketMonitorRuns,
} from "../api/hooks";
import {
  DataStatusBlock,
  EventFactSheetBlock,
  ExecutionCardBlock,
  PanicCardBlock,
  ScoreCardBlock,
  StyleCardBlock,
} from "../components/MarketMonitorBlocks";
import { extractErrorMessage, formatDateTime } from "../utils/format";

export function MarketMonitorPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const runsQuery = useMarketMonitorRuns();
  const createRunMutation = useCreateMarketMonitorRun();
  const latestSnapshotRun = runsQuery.data?.find((run) => run.trigger_endpoint === "snapshot");
  const runQuery = useMarketMonitorRun(latestSnapshotRun?.run_id || "");
  const run = runQuery.data;
  const snapshot = run?.snapshot;

  const refreshRuns = () => {
    runsQuery.refetch();
    if (latestSnapshotRun?.run_id) {
      runQuery.refetch();
    }
  };

  const startSnapshotRun = async () => {
    try {
      const created = await createRunMutation.mutateAsync({
        trigger_endpoint: "snapshot",
        force_refresh: true,
        mode: "snapshot",
        data_mode: "daily",
        llm_config: null,
      });
      navigate(`/monitor/runs/${created.run_id}`);
    } catch (error) {
      message?.error?.(extractErrorMessage(error));
    }
  };

  if (runsQuery.isError && !runsQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="市场监控加载失败"
        description={extractErrorMessage(runsQuery.error)}
        action={<Button size="small" onClick={refreshRuns}>重试</Button>}
      />
    );
  }

  if (runsQuery.isLoading) {
    return <Alert type="info" showIcon message="正在加载市场监控运行记录" />;
  }

  if (!latestSnapshotRun) {
    return (
      <Card className="page-card" title="市场监控">
        <Space direction="vertical" size={16}>
          <Alert type="info" showIcon message="暂无市场监控快照" description="创建一个后台运行后，可在详情页查看进度和最终结果。" />
          <Space wrap>
            <Button type="primary" loading={createRunMutation.isPending} onClick={startSnapshotRun}>生成市场监控</Button>
            <Button onClick={() => navigate("/monitor/create")}>新建运行</Button>
            <Button onClick={() => navigate("/monitor/history")}>查看历史记录</Button>
          </Space>
        </Space>
      </Card>
    );
  }

  if (!snapshot) {
    const isActive = latestSnapshotRun.status === "pending" || latestSnapshotRun.status === "running";
    return (
      <Card
        className="page-card"
        title="市场监控"
        extra={
          <Button icon={<ReloadOutlined />} loading={runsQuery.isFetching || runQuery.isFetching} onClick={refreshRuns}>
            刷新
          </Button>
        }
      >
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Alert
            type={isActive ? "info" : "warning"}
            showIcon
            message={isActive ? "市场监控正在后台生成" : "最近一次市场监控未生成快照"}
            description={isActive ? "详情页会自动刷新运行阶段、日志和最终结果。" : latestSnapshotRun.error_message || "可查看详情或重新创建运行。"}
          />
          <Space wrap>
            <Button type="primary" onClick={() => navigate(`/monitor/runs/${latestSnapshotRun.run_id}`)}>查看运行详情</Button>
            <Button loading={createRunMutation.isPending} onClick={startSnapshotRun}>重新生成市场监控</Button>
            <Button onClick={() => navigate("/monitor/create")}>新建运行</Button>
            <Button onClick={() => navigate("/monitor/history")}>查看历史记录</Button>
          </Space>
        </Space>
      </Card>
    );
  }

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
              refreshRuns();
            }}
          >
            <ReloadOutlined /> 刷新
          </a>
        }
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="blue">{snapshot.execution_card.regime_label}</Tag>
            <Tag>{snapshot.execution_card.conflict_mode}</Tag>
            <Tag>更新时间 {formatDateTime(snapshot.timestamp)}</Tag>
            <Tag>交易日 {snapshot.as_of_date}</Tag>
            <Tag>版本 {snapshot.scorecard_version}</Tag>
            <Tag>Prompt {snapshot.prompt_version}</Tag>
            <Tag>Model {snapshot.model_name || "-"}</Tag>
            <Tag>数据模式 {snapshot.data_mode}</Tag>
            <Tag>数据新鲜度 {snapshot.data_freshness}</Tag>
            <Tag color={snapshot.input_data_status.core_symbols_missing.length ? "warning" : "success"}>
              核心数据 {snapshot.input_data_status.core_symbols_available.length}/{snapshot.input_data_status.core_symbols_available.length + snapshot.input_data_status.core_symbols_missing.length}
            </Tag>
            {snapshot.run_id ? <Tag>运行 {snapshot.run_id.slice(0, 8)}</Tag> : null}
          </Space>
          <Typography.Text>{snapshot.execution_card.conflict_mode}</Typography.Text>
          <Space wrap>
            <Button type="primary" loading={createRunMutation.isPending} onClick={startSnapshotRun}>生成市场监控</Button>
            <Button onClick={() => navigate("/monitor/create")}>新建运行</Button>
            {snapshot.run_id ? (
              <Button onClick={() => navigate(`/monitor/runs/${snapshot.run_id}`)}>查看本次运行详情</Button>
            ) : null}
            {snapshot.prompt_traces?.length ? <Tag color="purple">Prompt Trace {snapshot.prompt_traces.length}</Tag> : null}
            <Button onClick={() => navigate("/monitor/history")}>查看历史记录</Button>
          </Space>
          {snapshot.missing_data.length ? (
            <Alert
              type="warning"
              showIcon
              message="当前结果存在缺失数据"
              description={snapshot.missing_data.map((item) => `${item.field}: ${item.reason}`).join("；")}
            />
          ) : null}
        </Space>
      </Card>

      <ExecutionCardBlock card={snapshot.execution_card} />

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
            <DataStatusBlock
              inputDataStatus={snapshot.input_data_status}
              missingData={snapshot.missing_data}
              risks={snapshot.risks}
              openGaps={snapshot.fact_sheet?.open_gaps || []}
            />
          </Space>
        </Col>
      </Row>
    </Space>
  );
}
