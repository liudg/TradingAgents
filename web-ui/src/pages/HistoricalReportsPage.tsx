import {
  Alert,
  Card,
  DatePicker,
  Input,
  List,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import { BarChartOutlined, RightOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import { useMemo, useState } from "react";
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

type SortOrder = "desc" | "asc";

export function HistoricalReportsPage() {
  const navigate = useNavigate();
  const reportsQuery = useHistoricalReports();
  const [tickerFilter, setTickerFilter] = useState("");
  const [dateFilter, setDateFilter] = useState<Dayjs | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  const filteredReports = useMemo(() => {
    const reports = reportsQuery.data ?? [];
    const normalizedTickerFilter = tickerFilter.trim().toUpperCase();
    const selectedDate = dateFilter?.format("YYYY-MM-DD");

    return [...reports]
      .filter((report) => {
        if (
          normalizedTickerFilter &&
          !report.ticker.toUpperCase().includes(normalizedTickerFilter)
        ) {
          return false;
        }
        if (selectedDate && report.trade_date !== selectedDate) {
          return false;
        }
        return true;
      })
      .sort((a, b) => {
        const left = dayjs(a.generated_at).valueOf();
        const right = dayjs(b.generated_at).valueOf();
        return sortOrder === "desc" ? right - left : left - right;
      });
  }, [reportsQuery.data, tickerFilter, dateFilter, sortOrder]);

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

  const emptyText =
    reportsQuery.data.length === 0
      ? "暂无历史分析报告"
      : "没有匹配的分析报告";

  return (
    <Card className="page-card" title="历史分析报告">
      <Space style={{ width: "100%", marginBottom: 16 }} size={12} wrap>
        <Input
          allowClear
          style={{ minWidth: 220 }}
          placeholder="按名称筛选（股票代码）"
          value={tickerFilter}
          onChange={(event) => setTickerFilter(event.target.value)}
        />
        <DatePicker
          allowClear
          style={{ minWidth: 180 }}
          placeholder="按日期筛选"
          value={dateFilter}
          onChange={(value) => setDateFilter(value)}
        />
        <Select<SortOrder>
          style={{ minWidth: 180 }}
          value={sortOrder}
          onChange={(value) => setSortOrder(value)}
          options={[
            { label: "时间排序：最新在前", value: "desc" },
            { label: "时间排序：最早在前", value: "asc" },
          ]}
        />
      </Space>

      <List
        className="history-report-list"
        dataSource={filteredReports}
        locale={{ emptyText }}
        renderItem={(report) => (
          <List.Item
            className="history-report-item"
            onClick={() => navigate(`/reports/${report.job_id}`)}
            actions={[<RightOutlined key="enter" className="meta-text" />]}
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
                    生成时间：{formatDateTime(report.generated_at)} · 深度参数：
                    {report.max_debate_rounds}/{report.max_risk_discuss_rounds} ·
                    模型：{report.deep_think_llm} / {report.quick_think_llm}
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
