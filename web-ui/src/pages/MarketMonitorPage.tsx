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
  EventRiskBlock,
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
            <Tag>数据新鲜度 {snapshot.data_freshness}</Tag>
            <Tag color={snapshot.source_coverage.completeness === "high" ? "success" : snapshot.source_coverage.completeness === "medium" ? "warning" : "error"}>
              完整度 {snapshot.source_coverage.completeness}
            </Tag>
            {snapshot.run_id ? <Tag>运行 {snapshot.run_id.slice(0, 8)}</Tag> : null}
          </Space>
          <Typography.Text>{snapshot.execution_card.summary}</Typography.Text>
          <Space wrap>
            {snapshot.run_id ? (
              <Button onClick={() => navigate(`/monitor/runs/${snapshot.run_id}`)}>查看本次运行详情</Button>
            ) : null}
            {snapshot.prompt_traces.length ? <Tag color="purple">Prompt Trace {snapshot.prompt_traces.length}</Tag> : null}
            <Button onClick={() => navigate("/monitor/history")}>查看历史记录</Button>
          </Space>
          {snapshot.degraded_factors.length ? (
            <Alert
              type="warning"
              showIcon
              message="当前结果包含降级输出"
              description={snapshot.degraded_factors.join("；")}
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
          <StyleCardBlock card={snapshot.style_effectiveness} />
        </Col>
        <Col xs={24} lg={12}>
          <PanicCardBlock card={snapshot.panic_reversal_score} />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <EventRiskBlock card={snapshot.event_risk_flag} />
        </Col>
        <Col xs={24} lg={12}>
          <DataStatusBlock
            sourceCoverage={dataStatus?.source_coverage || snapshot.source_coverage}
            degradedFactors={dataStatus?.degraded_factors || snapshot.degraded_factors}
            notes={dataStatus?.notes || snapshot.notes}
            openGaps={dataStatus?.open_gaps || snapshot.fact_sheet?.open_gaps || []}
          />
        </Col>
      </Row>

      <HistoryBlock points={historyQuery.data?.points || []} />
    </Space>
  );
}
