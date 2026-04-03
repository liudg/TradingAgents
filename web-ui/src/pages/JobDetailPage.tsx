import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
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
  ReloadOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";

import { useAnalysisJob, useAnalysisReport } from "../api/hooks";
import { AnalysisFinalState, DebateState } from "../api/types";
import { MarkdownPanel } from "../components/MarkdownPanel";
import {
  extractErrorMessage,
  formatDateTime,
  getStatusColor,
  getStatusText,
} from "../utils/format";

const analystNameMap: Record<string, string> = {
  market: "市场技术分析",
  social: "社交情绪分析",
  news: "新闻分析",
  fundamentals: "基本面分析",
};

function renderReportSections(finalState: AnalysisFinalState | null) {
  if (!finalState) {
    return null;
  }

  const sections = [
    { key: "market", label: "市场技术分析报告", value: finalState.market_report },
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
    { key: "investment", label: "研究经理决策", value: finalState.investment_plan },
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
            <MarkdownPanel content={section.value} emptyText="本模块暂无返回内容" />
          </Card>
        </Col>
      ))}
    </Row>
  );
}

function buildDebateItems(title: string, debateState?: DebateState | null) {
  if (!debateState) {
    return [
      {
        key: title,
        label: title,
        children: <MarkdownPanel content="" emptyText="暂无辩论记录" />,
      },
    ];
  }

  const fields = Object.entries(debateState).filter(([, value]) =>
    Boolean(value && String(value).trim()),
  );

  return [
    {
      key: title,
      label: title,
      children:
        fields.length === 0 ? (
          <MarkdownPanel content="" emptyText="暂无辩论记录" />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            {fields.map(([key, value]) => (
              <Card key={key} size="small" title={key}>
                <MarkdownPanel content={String(value)} />
              </Card>
            ))}
          </Space>
        ),
    },
  ];
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

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const jobQuery = useAnalysisJob(jobId);
  const reportQuery = useAnalysisReport(
    jobId,
    jobQuery.data?.status === "completed",
  );

  if (jobQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (jobQuery.isError || !jobQuery.data) {
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

  const job = jobQuery.data;
  const isCompleted = job.status === "completed";
  const isFailed = job.status === "failed";

  const handleDownload = async () => {
    try {
      const report = await reportQuery.refetch();
      if (report.data) {
        downloadMarkdown(`${job.job_id}-complete-report.md`, report.data);
        message.success("报告下载已开始");
      }
    } catch (error) {
      message.error(extractErrorMessage(error));
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        className="page-card"
        title={
          <Space>
            <span>任务详情</span>
            <Tag color={getStatusColor(job.status)}>{getStatusText(job.status)}</Tag>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => jobQuery.refetch()}>
              刷新状态
            </Button>
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
            <Statistic title="任务进度" value={job.progress} suffix="%" />
            <Progress
              percent={job.progress}
              status={isFailed ? "exception" : isCompleted ? "success" : "active"}
              style={{ marginTop: 12 }}
            />
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
              <Descriptions.Item label="创建时间">
                {formatDateTime(job.created_at)}
              </Descriptions.Item>
              <Descriptions.Item label="开始时间">
                {formatDateTime(job.started_at)}
              </Descriptions.Item>
              <Descriptions.Item label="结束时间">
                {formatDateTime(job.finished_at)}
              </Descriptions.Item>
              <Descriptions.Item label="服务端报告路径">
                {job.report_path || "-"}
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
          <MarkdownPanel content={job.decision} />
        </Card>
      ) : null}

      {renderReportSections(job.final_state)}

      <Card className="page-card" title="辩论过程">
        <Collapse
          items={[
            ...buildDebateItems(
              "多空研究员辩论",
              job.final_state?.investment_debate_state,
            ),
            ...buildDebateItems(
              "风控团队辩论",
              job.final_state?.risk_debate_state,
            ),
          ]}
          defaultActiveKey={["多空研究员辩论"]}
        />
      </Card>

      <Card
        className="page-card"
        title="完整 Markdown 报告预览"
        extra={
          reportQuery.isFetching && isCompleted ? (
            <Tag color="processing">报告加载中</Tag>
          ) : null
        }
      >
        {reportQuery.isError ? (
          <Alert
            type="warning"
            showIcon
            message="报告暂不可用"
            description={extractErrorMessage(reportQuery.error)}
          />
        ) : (
          <MarkdownPanel
            content={reportQuery.data}
            emptyText={
              isCompleted ? "报告内容为空" : "任务完成后自动加载完整 Markdown 报告"
            }
          />
        )}
      </Card>
    </Space>
  );
}
