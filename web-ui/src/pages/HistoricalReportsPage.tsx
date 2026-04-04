import {
  Alert,
  Card,
  List,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { BarChartOutlined, RightOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

import { useHistoricalReports } from "../api/hooks";
import { AnalystType } from "../api/types";
import { extractErrorMessage, formatDateTime } from "../utils/format";

const analystNameMap: Record<AnalystType, string> = {
  market: "市场技术分析师",
  social: "社交情绪分析师",
  news: "新闻分析师",
  fundamentals: "基本面分析师",
};

export function HistoricalReportsPage() {
  const navigate = useNavigate();
  const reportsQuery = useHistoricalReports();

  if (reportsQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (reportsQuery.isError || !reportsQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="历史报告加载失败"
        description={extractErrorMessage(reportsQuery.error)}
      />
    );
  }

  return (
    <Card className="page-card" title="历史分析报告">
      <List
        className="history-report-list"
        dataSource={reportsQuery.data}
        locale={{ emptyText: "暂无历史分析报告" }}
        renderItem={(report) => (
          <List.Item
            className="history-report-item"
            onClick={() => navigate(`/reports/${report.job_id}`)}
            actions={[
              <RightOutlined key="enter" className="meta-text" />,
            ]}
          >
            <List.Item.Meta
              avatar={<BarChartOutlined className="history-report-icon" />}
              title={
                <Space size="middle" wrap>
                  <Typography.Text strong>{report.ticker}</Typography.Text>
                  <Typography.Text>{report.trade_date}</Typography.Text>
                  <Tag color="blue">{report.llm_provider}</Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={8}>
                  <Space wrap>
                    {report.selected_analysts.map((analyst) => (
                      <Tag key={analyst}>
                        {analystNameMap[analyst] || analyst}
                      </Tag>
                    ))}
                  </Space>
                  <Typography.Text type="secondary">
                    生成时间：{formatDateTime(report.generated_at)} ｜ 深度参数：
                    {report.max_debate_rounds}/
                    {report.max_risk_discuss_rounds} ｜ 模型：
                    {report.deep_think_llm} / {report.quick_think_llm}
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
