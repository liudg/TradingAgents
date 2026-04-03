import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Menu,
  Result,
  Row,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useHistoricalReport } from "../api/hooks";
import { AnalystType, HistoricalReportItem } from "../api/types";
import { MarkdownPanel } from "../components/MarkdownPanel";
import { extractErrorMessage, formatDateTime } from "../utils/format";

const analystNameMap: Record<AnalystType, string> = {
  market: "市场技术分析师",
  social: "社交情绪分析师",
  news: "新闻分析师",
  fundamentals: "基本面分析师",
};

export function HistoricalReportDetailPage() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const detailQuery = useHistoricalReport(jobId);
  const [selectedReportKey, setSelectedReportKey] = useState<string>("");

  const reportLookup = useMemo(() => {
    const lookup = new Map<string, HistoricalReportItem & { agentName: string }>();
    detailQuery.data?.agent_reports.forEach((group) => {
      group.reports.forEach((report) => {
        lookup.set(`${group.agent_key}/${report.report_key}`, {
          ...report,
          agentName: group.agent_name,
        });
      });
    });
    return lookup;
  }, [detailQuery.data]);

  const menuItems = useMemo(
    () =>
      detailQuery.data?.agent_reports.map((group) => ({
        key: group.agent_key,
        label: group.agent_name,
        children: group.reports.map((report) => ({
          key: `${group.agent_key}/${report.report_key}`,
          label: report.title,
        })),
      })) || [],
    [detailQuery.data],
  );

  useEffect(() => {
    if (selectedReportKey || !detailQuery.data?.agent_reports.length) {
      return;
    }

    const firstGroup = detailQuery.data.agent_reports[0];
    const firstReport = firstGroup?.reports[0];
    if (firstGroup && firstReport) {
      setSelectedReportKey(`${firstGroup.agent_key}/${firstReport.report_key}`);
    }
  }, [detailQuery.data, selectedReportKey]);

  if (detailQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 14 }} />
      </Card>
    );
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <Result
        status="error"
        title="历史报告加载失败"
        subTitle={extractErrorMessage(detailQuery.error)}
        extra={
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/reports")}
          >
            返回历史报告列表
          </Button>
        }
      />
    );
  }

  const detail = detailQuery.data;
  const selectedReport = reportLookup.get(selectedReportKey);

  if (detail.agent_reports.length === 0) {
    return (
      <Alert
        type="warning"
        showIcon
        message="当前历史报告没有可展示的正文内容"
      />
    );
  }

  return (
    <Row gutter={[16, 16]} className="report-detail-grid">
      <Col xs={24} lg={6}>
        <Card className="page-card report-sidebar-card" title="报告目录">
          <Menu
            mode="inline"
            selectedKeys={selectedReportKey ? [selectedReportKey] : []}
            defaultOpenKeys={detail.agent_reports.map((group) => group.agent_key)}
            items={menuItems}
            onClick={({ key }) => setSelectedReportKey(key)}
          />
        </Card>
      </Col>

      <Col xs={24} lg={12}>
        <Card
          className="page-card report-content-card"
          title={
            <Space direction="vertical" size={2}>
              <Typography.Text strong>
                {selectedReport?.title || "报告详情"}
              </Typography.Text>
              <Typography.Text type="secondary">
                {selectedReport?.agentName || "-"}
              </Typography.Text>
            </Space>
          }
        >
          <MarkdownPanel
            content={selectedReport?.content}
            emptyText="该报告暂无正文内容"
          />
        </Card>
      </Col>

      <Col xs={24} lg={6}>
        <Card className="page-card report-meta-card" title="报告信息">
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="股票代码">
              {detail.ticker}
            </Descriptions.Item>
            <Descriptions.Item label="报告日期">
              {detail.trade_date}
            </Descriptions.Item>
            <Descriptions.Item label="生成时间">
              {formatDateTime(detail.generated_at)}
            </Descriptions.Item>
            <Descriptions.Item label="启用分析师">
              <Space wrap>
                {detail.selected_analysts.map((item) => (
                  <Tag key={item}>{analystNameMap[item] || item}</Tag>
                ))}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="研究深度">
              辩论轮数 {detail.max_debate_rounds} ｜ 风控轮数{" "}
              {detail.max_risk_discuss_rounds} ｜ 递归上限{" "}
              {detail.max_recur_limit}
            </Descriptions.Item>
            <Descriptions.Item label="LLM Provider">
              {detail.llm_provider}
            </Descriptions.Item>
            <Descriptions.Item label="Deep Model">
              {detail.deep_think_llm}
            </Descriptions.Item>
            <Descriptions.Item label="Quick Model">
              {detail.quick_think_llm}
            </Descriptions.Item>
            <Descriptions.Item label="任务 ID">
              <Typography.Text copyable>{detail.job_id}</Typography.Text>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </Col>
    </Row>
  );
}
