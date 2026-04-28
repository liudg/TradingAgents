import {
  Alert,
  Button,
  Card,
  Col,
  Row,
  Space,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  useMarketMonitorDataStatus,
  useMarketMonitorHistory,
  useMarketMonitorSnapshot,
} from "../api/hooks";
import {
  DataStatusBlock,
  EventFactSheetBlock,
  ExecutionCardBlock,
  HistoryBlock,
  PanicCardBlock,
  ScoreCardBlock,
  StyleCardBlock,
} from "../components/MarketMonitorBlocks";
import { extractErrorMessage, formatDateTime } from "../utils/format";

export function MarketMonitorPage() {
  const navigate = useNavigate();
  const [refreshToken, setRefreshToken] = useState(0);
  const forceRefresh = refreshToken > 0;
  const snapshotQuery = useMarketMonitorSnapshot(undefined, forceRefresh, refreshToken);
  const historyQuery = useMarketMonitorHistory(20, undefined, forceRefresh, refreshToken);
  const dataStatusQuery = useMarketMonitorDataStatus(undefined, forceRefresh, refreshToken);

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

  if (!snapshotQuery.data) {
    return <Alert type="info" showIcon message="正在加载市场监控快照" />;
  }

  const snapshot = snapshotQuery.data;
  const dataStatus = dataStatusQuery.data;

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
              setRefreshToken((value) => value + 1);
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
            <Button type="primary" onClick={() => navigate("/monitor/create")}>新建运行</Button>
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
              inputDataStatus={dataStatus?.input_data_status || snapshot.input_data_status}
              missingData={dataStatus?.missing_data || snapshot.missing_data}
              risks={dataStatus?.risks || snapshot.risks}
              openGaps={dataStatus?.open_gaps || snapshot.fact_sheet?.open_gaps || []}
            />
          </Space>
        </Col>
      </Row>

      <HistoryBlock points={historyQuery.data?.points || []} />
    </Space>
  );
}
