import {
  Alert,
  App,
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
  Tag,
  Typography,
} from "antd";
import {
  ArrowLeftOutlined,
  DownloadOutlined,
  FileTextOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import {
  useAnalysisJob,
  useAnalysisJobLogs,
  useAnalysisReport,
} from "../api/hooks";
import { AnalysisFinalState, AnalysisJobLogEntry } from "../api/types";
import { MarkdownPanel } from "../components/MarkdownPanel";
import {
  extractErrorMessage,
  formatDateTime,
  formatElapsedTime,
  getStatusColor,
  getStatusText,
} from "../utils/format";

const analystNameMap: Record<string, string> = {
  market: "市场技术分析师",
  social: "社交情绪分析师",
  news: "新闻分析师",
  fundamentals: "基本面分析师",
};

const logLevelColorMap: Record<string, string> = {
  System: "blue",
  Agent: "purple",
  "Tool Call": "cyan",
  Data: "green",
  Control: "default",
  User: "gold",
  Error: "red",
  Raw: "default",
};

function renderReportSections(finalState: AnalysisFinalState | null) {
  if (!finalState) {
    return null;
  }

  const sections = [
    {
      key: "market",
      label: "市场技术分析报告",
      value: finalState.market_report,
    },
    {
      key: "sentiment",
      label: "社交情绪分析报告",
      value: finalState.sentiment_report,
    },
    { key: "news", label: "新闻分析报告", value: finalState.news_report },
    {
      key: "fundamentals",
      label: "基本面分析报告",
      value: finalState.fundamentals_report,
    },
    {
      key: "investment",
      label: "研究经理决策",
      value: finalState.investment_plan,
    },
    {
      key: "trader",
      label: "交易员方案",
      value: finalState.trader_investment_plan,
    },
    {
      key: "decision",
      label: "组合经理最终决策",
      value: finalState.final_trade_decision,
    },
  ];

  return (
    <Row gutter={[16, 16]}>
      {sections.map((section) => (
        <Col xs={24} xl={12} key={section.key}>
          <Card className="section-card" title={section.label}>
            <MarkdownPanel
              content={section.value}
              emptyText="本模块暂无返回内容"
            />
          </Card>
        </Col>
      ))}
    </Row>
  );
}

function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function renderExecutionLogItem(item: AnalysisJobLogEntry) {
  return (
    <List.Item>
      <Space direction="vertical" size={6} style={{ width: "100%" }}>
        <Space size={8} wrap>
          <Tag color={logLevelColorMap[item.level] || "default"}>
            {item.level}
          </Tag>
          <Typography.Text type="secondary">
            #{item.line_no}
          </Typography.Text>
          <Typography.Text type="secondary">
            {formatDateTime(item.timestamp)}
          </Typography.Text>
        </Space>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          {item.content || "-"}
        </Typography.Paragraph>
      </Space>
    </List.Item>
  );
}

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const jobQuery = useAnalysisJob(jobId);
  const job = jobQuery.data;
  const reportQuery = useAnalysisReport(jobId, false);
  const logsQuery = useAnalysisJobLogs(jobId, job?.status);

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
        title="任务加载失败"
        subTitle={extractErrorMessage(jobQuery.error)}
        extra={
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
            返回新建任务
          </Button>
        }
      />
    );
  }

  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";
  const executionLogs = [...(logsQuery.data || [])].reverse();

  const handleDownload = async () => {
    const report = await reportQuery.refetch();

    if (report.isError) {
      message.error(extractErrorMessage(report.error));
      return;
    }

    if (!report.data) {
      message.warning("报告内容为空，暂时无法下载");
      return;
    }

    downloadMarkdown(`${job.job_id}-complete-report.md`, report.data);
    message.success("报告下载已开始");
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>任务详情</span>
            <Tag color={getStatusColor(job.status)}>
              {getStatusText(job.status)}
            </Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Button
              icon={<ReloadOutlined />}
              loading={jobQuery.isFetching}
              onClick={() => {
                jobQuery.refetch();
                logsQuery.refetch();
              }}
            >
              刷新状态
            </Button>
            {isCompleted ? (
              <Button
                icon={<FileTextOutlined />}
                onClick={() => navigate(`/reports/${job.job_id}`)}
              >
                查看报告
              </Button>
            ) : null}
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              disabled={!isCompleted}
              loading={reportQuery.isFetching}
              onClick={handleDownload}
            >
              下载 Markdown 报告
            </Button>
          </Space>
        }
      >
        <Row gutter={[24, 24]}>
          <Col xs={24} lg={8}>
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <div>
                <Statistic title="任务进度" value={job.progress} suffix="%" />
                <Progress
                  percent={job.progress}
                  status={
                    isFailed ? "exception" : isCompleted ? "success" : "active"
                  }
                  style={{ marginTop: 12 }}
                />
              </div>
              <Statistic
                title="已消耗时间"
                value={formatElapsedTime(job.started_at, job.finished_at)}
              />
            </Space>
          </Col>
          <Col xs={24} lg={16}>
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="任务 ID" span={2}>
                <Typography.Text copyable>{job.job_id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="股票代码">
                {job.request.ticker}
              </Descriptions.Item>
              <Descriptions.Item label="分析日期">
                {job.request.trade_date}
              </Descriptions.Item>
              <Descriptions.Item label="启用分析师" span={2}>
                <Space wrap>
                  {job.request.selected_analysts.map((item) => (
                    <Tag key={item}>{analystNameMap[item] || item}</Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="模型供应商">
                {job.request.llm_provider}
              </Descriptions.Item>
              <Descriptions.Item label="输出语言">
                {job.request.output_language}
              </Descriptions.Item>
              <Descriptions.Item label="Backend URL" span={2}>
                {job.request.backend_url || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Deep Model">
                {job.request.deep_think_llm}
              </Descriptions.Item>
              <Descriptions.Item label="Quick Model">
                {job.request.quick_think_llm}
              </Descriptions.Item>
              <Descriptions.Item label="OpenAI Reasoning Effort">
                {job.request.openai_reasoning_effort || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Codex Reasoning Effort">
                {job.request.codex_reasoning_effort || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Google Thinking Level">
                {job.request.google_thinking_level || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Anthropic Effort">
                {job.request.anthropic_effort || "-"}
              </Descriptions.Item>
              <Descriptions.Item label="Research Depth">
                {job.request.max_debate_rounds ===
                job.request.max_risk_discuss_rounds
                  ? job.request.max_debate_rounds
                  : `${job.request.max_debate_rounds}/${job.request.max_risk_discuss_rounds}`}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {formatDateTime(job.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {formatDateTime(job.started_at)}
              </Descriptions.Item>
              <Descriptions.Item label="结束时间">
                {formatDateTime(job.finished_at)}
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {isFailed ? (
        <Alert
          type="error"
          showIcon
          message="分析任务执行失败"
          description={job.error_message || "后端未返回失败原因"}
        />
      ) : null}

      {job.decision ? (
        <Card className="page-card" title="提取后的交易决策">
          <div className="decision-highlight-panel">
            <MarkdownPanel content={job.decision} />
          </div>
        </Card>
      ) : null}

      {renderReportSections(job.final_state)}

      <Card
        className="page-card"
        title="执行过程"
        extra={
          logsQuery.isFetching ? <Tag color="processing">日志更新中</Tag> : null
        }
      >
        {logsQuery.isError ? (
          <Alert
            type="warning"
            showIcon
            message="执行日志加载失败"
            description={extractErrorMessage(logsQuery.error)}
          />
        ) : (
          <List
            dataSource={executionLogs}
            locale={{ emptyText: "暂无执行日志" }}
            renderItem={renderExecutionLogItem}
          />
        )}
      </Card>
    </Space>
  );
}
