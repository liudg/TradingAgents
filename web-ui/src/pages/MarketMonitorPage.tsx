import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Progress,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { useNavigate } from "react-router-dom";

import {
  useCreateMarketMonitorRun,
  useMarketMonitorRun,
  useMarketMonitorRuns,
} from "../api/hooks";
import { extractErrorMessage, formatDateTime } from "../utils/format";

function scoreColor(score: number) {
  if (score >= 80) return "success";
  if (score >= 60) return "processing";
  if (score >= 40) return "warning";
  return "error";
}

function permissionTag(label: string, enabled: boolean) {
  return <Tag color={enabled ? "success" : "error"}>{label}{enabled ? "允许" : "禁止"}</Tag>;
}

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
      <Card className="page-card" title="市场监控">
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
      <Card className="page-card" title="市场监控">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="blue">{snapshot.execution_card.regime_label}</Tag>
            <Tag>更新时间 {formatDateTime(snapshot.timestamp)}</Tag>
            <Tag>美东交易日 {snapshot.as_of_date}</Tag>
            <Tag color={snapshot.input_data_status.core_symbols_missing.length ? "warning" : "success"}>
              核心数据 {snapshot.input_data_status.core_symbols_available.length}/{snapshot.input_data_status.core_symbols_available.length + snapshot.input_data_status.core_symbols_missing.length}
            </Tag>
          </Space>
          <Typography.Text>{snapshot.execution_card.decision_reasoning || snapshot.execution_card.conflict_mode}</Typography.Text>
          <Space wrap>
            <Button type="primary" loading={createRunMutation.isPending} onClick={startSnapshotRun}>生成市场监控</Button>
            <Button onClick={() => navigate("/monitor/create")}>新建运行</Button>
            {snapshot.run_id ? (
              <Button onClick={() => navigate(`/monitor/runs/${snapshot.run_id}`)}>查看本次运行详情</Button>
            ) : null}
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

      <Card className="page-card" title="执行结论">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="blue">{snapshot.execution_card.regime_label}</Tag>
            <Tag>总仓位 {snapshot.execution_card.total_exposure_range}</Tag>
            <Tag>单票上限 {snapshot.execution_card.single_position_cap}</Tag>
            <Tag>风险预算 {snapshot.execution_card.daily_risk_budget}</Tag>
          </Space>
          <Typography.Text>{snapshot.execution_card.decision_reasoning || snapshot.execution_card.conflict_mode}</Typography.Text>
          <Space wrap>
            {permissionTag("新开仓", snapshot.execution_card.new_position_allowed)}
            {permissionTag("追高", snapshot.execution_card.chase_breakout_allowed)}
            {permissionTag("低吸", snapshot.execution_card.dip_buy_allowed)}
            {permissionTag("隔夜", snapshot.execution_card.overnight_allowed)}
            {permissionTag("杠杆", snapshot.execution_card.leverage_allowed)}
          </Space>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        {[{
          title: "长线",
          score: snapshot.long_term_score.score,
          zone: snapshot.long_term_score.zone,
          hint: snapshot.long_term_score.action_hint || snapshot.long_term_score.recommended_exposure || "-",
        }, {
          title: "短线",
          score: snapshot.short_term_score.score,
          zone: snapshot.short_term_score.zone,
          hint: snapshot.short_term_score.action_hint || "-",
        }, {
          title: "系统风险",
          score: snapshot.system_risk_score.score,
          zone: snapshot.system_risk_score.zone,
          hint: snapshot.system_risk_score.action_hint || "-",
        }, {
          title: "恐慌反转",
          score: snapshot.panic_reversal_score.score,
          zone: snapshot.panic_reversal_score.state,
          hint: snapshot.panic_reversal_score.action_hint || snapshot.panic_reversal_score.action,
        }].map((item) => (
          <Col xs={24} md={12} xl={6} key={item.title}>
            <Card className="section-card" title={item.title}>
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Space wrap><Tag color={scoreColor(item.score)}>分数 {item.score.toFixed(1)}</Tag><Tag>{item.zone}</Tag></Space>
                <Progress percent={item.score} showInfo={false} />
                <Typography.Text type="secondary">{item.hint}</Typography.Text>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Card className="page-card" title="交易偏好与风险提示">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Tag color="success">手法 {snapshot.style_effectiveness.tactic_layer.top_tactic}</Tag>
            <Tag color="warning">回避 {snapshot.style_effectiveness.tactic_layer.avoid_tactic}</Tag>
            <Tag>偏好 {snapshot.execution_card.preferred_assets.join("、") || "无"}</Tag>
            <Tag>回避 {snapshot.execution_card.avoid_assets.join("、") || "无"}</Tag>
            <Tag color={snapshot.execution_card.event_risk_flag.index_level.active ? "warning" : "success"}>指数事件 {snapshot.execution_card.event_risk_flag.index_level.active ? "激活" : "未激活"}</Tag>
            <Tag color={snapshot.missing_data.length ? "warning" : "success"}>缺失数据 {snapshot.missing_data.length}</Tag>
          </Space>
          <Typography.Text>{snapshot.execution_card.event_risk_flag.index_level.action_modifier?.note || "当前无指数级事件修正。"}</Typography.Text>
          {snapshot.risks.length ? <Typography.Text type="secondary">风险提示：{snapshot.risks.join("；")}</Typography.Text> : null}
        </Space>
      </Card>
    </Space>
  );
}
