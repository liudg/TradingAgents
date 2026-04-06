import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  List,
  Progress,
  Result,
  Row,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import { useBacktestJob, useBacktestJobLogs } from "../api/hooks";
import { extractErrorMessage, formatDateTime, getStatusColor, getStatusText } from "../utils/format";

function formatPercent(value?: number | null) {
  return value === null || value === undefined ? "-" : `${value.toFixed(2)}%`;
}

export function BacktestDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const jobQuery = useBacktestJob(jobId);
  const job = jobQuery.data;
  const logsQuery = useBacktestJobLogs(jobId, job?.status);

  if (jobQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (jobQuery.isError || !job) {
    return (
      <Result
        status="error"
        title="回测任务加载失败"
        subTitle={extractErrorMessage(jobQuery.error)}
        extra={
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/backtests")}>
            返回回测创建页
          </Button>
        }
      />
    );
  }

  const sampleColumns = [
    { title: "日期", dataIndex: "trade_date", key: "trade_date" },
    { title: "信号", dataIndex: "signal", key: "signal", render: (value: string) => <Tag>{value}</Tag> },
    { title: "结果", dataIndex: "outcome_label", key: "outcome_label", render: (value: string) => <Tag color={value === "correct" ? "success" : value.includes("incorrect") || value.includes("missed") ? "error" : "default"}>{value}</Tag> },
    { title: "收益", dataIndex: "return_pct", key: "return_pct", render: (value: number | null) => formatPercent(value) },
    { title: "基准", dataIndex: "benchmark_return_pct", key: "benchmark_return_pct", render: (value: number | null) => formatPercent(value) },
    { title: "超额", dataIndex: "excess_return_pct", key: "excess_return_pct", render: (value: number | null) => formatPercent(value) },
    { title: "复盘", dataIndex: "reflection_text", key: "reflection_text", render: (value: string | null) => value || "-" },
  ];

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>回测任务详情</span>
            <Tag color={getStatusColor(job.status)}>{getStatusText(job.status)}</Tag>
          </Space>
        }
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={jobQuery.isFetching}
            onClick={() => {
              jobQuery.refetch();
              logsQuery.refetch();
            }}
          >
            刷新
          </Button>
        }
      >
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={8}>
            <Statistic title="任务进度" value={job.progress} suffix="%" />
            <Progress percent={job.progress} status={job.status === "failed" ? "exception" : job.status === "completed" ? "success" : "active"} style={{ marginTop: 12 }} />
          </Col>
          <Col xs={24} lg={16}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="任务 ID" span={2}>
                <Typography.Text copyable>{job.job_id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="股票代码">{job.request.ticker}</Descriptions.Item>
              <Descriptions.Item label="阶段">{job.stage}</Descriptions.Item>
              <Descriptions.Item label="开始日期">{job.request.start_date}</Descriptions.Item>
              <Descriptions.Item label="结束日期">{job.request.end_date}</Descriptions.Item>
              <Descriptions.Item label="持有期">{job.request.holding_period} 天</Descriptions.Item>
              <Descriptions.Item label="Provider">{job.request.llm_provider}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(job.created_at)}</Descriptions.Item>
              <Descriptions.Item label="完成时间">{formatDateTime(job.finished_at)}</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>

        {job.error_message ? (
          <Alert type="error" showIcon style={{ marginTop: 16 }} message="回测执行失败" description={job.error_message} />
        ) : null}
      </Card>

      {job.summary ? (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8}><Card><Statistic title="样本数" value={job.summary.sample_count} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="评估样本" value={job.summary.evaluated_count} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="BUY 胜率" value={job.summary.win_rate ?? 0} suffix="%" /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="平均收益" value={job.summary.avg_return_pct ?? 0} suffix="%" precision={2} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="平均超额收益" value={job.summary.excess_return_pct ?? 0} suffix="%" precision={2} /></Card></Col>
          <Col xs={24} md={8}><Card><Statistic title="Memory 写回数" value={job.summary.memory_write_count} /></Card></Col>
        </Row>
      ) : null}

      <Card className="page-card" title="单笔样本">
        <Table
          rowKey={(record) => `${record.trade_date}-${record.signal}`}
          columns={sampleColumns}
          dataSource={job.samples}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="Memory 写回">
            <List
              dataSource={job.memory_entries}
              locale={{ emptyText: "当前实验没有写回 memory 的样本" }}
              renderItem={(item) => (
                <List.Item>
                  <Space direction="vertical" size={4} style={{ width: "100%" }}>
                    <Space wrap>
                      <Tag color="blue">{item.memory_type}</Tag>
                      <Tag>{item.signal}</Tag>
                      <Typography.Text>{item.trade_date}</Typography.Text>
                    </Space>
                    <Typography.Text>{item.recommendation}</Typography.Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="page-card" title="任务日志">
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
        </Col>
      </Row>
    </Space>
  );
}
