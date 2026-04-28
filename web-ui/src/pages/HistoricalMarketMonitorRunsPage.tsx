import {
  Alert,
  Card,
  DatePicker,
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

import { useMarketMonitorRuns } from "../api/hooks";
import { extractErrorMessage, formatDateTime, getStatusColor, getStatusText } from "../utils/format";

type EndpointFilter = "snapshot" | "history" | "data_status" | "all";
type SortOrder = "desc" | "asc";

export function HistoricalMarketMonitorRunsPage() {
  const navigate = useNavigate();
  const runsQuery = useMarketMonitorRuns();
  const [endpointFilter, setEndpointFilter] = useState<EndpointFilter>("snapshot");
  const [dateFilter, setDateFilter] = useState<Dayjs | null>(null);
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");

  const filteredRuns = useMemo(() => {
    const runs = runsQuery.data ?? [];
    const selectedDate = dateFilter?.format("YYYY-MM-DD");
    return [...runs]
      .filter((run) => {
        if (endpointFilter !== "all" && run.trigger_endpoint !== endpointFilter) {
          return false;
        }
        if (selectedDate && run.as_of_date !== selectedDate) {
          return false;
        }
        return true;
      })
      .sort((a, b) => {
        const left = dayjs(a.generated_at).valueOf();
        const right = dayjs(b.generated_at).valueOf();
        return sortOrder === "desc" ? right - left : left - right;
      });
  }, [runsQuery.data, endpointFilter, dateFilter, sortOrder]);

  if (runsQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (runsQuery.isError || !runsQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="市场监控历史加载失败"
        description={extractErrorMessage(runsQuery.error)}
      />
    );
  }

  const emptyText = runsQuery.data.length === 0 ? "暂无市场监控历史" : "没有匹配的运行记录";

  return (
    <Card className="page-card" title="市场监控历史">
      <Space style={{ width: "100%", marginBottom: 16 }} size={12} wrap>
        <Select<EndpointFilter>
          style={{ minWidth: 200 }}
          value={endpointFilter}
          onChange={(value) => setEndpointFilter(value)}
          options={[
            { label: "只看 snapshot", value: "snapshot" },
            { label: "查看全部", value: "all" },
            { label: "只看 history", value: "history" },
            { label: "只看 data_status", value: "data_status" },
          ]}
        />
        <DatePicker
          allowClear
          style={{ minWidth: 180 }}
          placeholder="按交易日筛选"
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
        dataSource={filteredRuns}
        locale={{ emptyText }}
        renderItem={(run) => (
          <List.Item
            className="history-report-item"
            onClick={() => navigate(`/monitor/runs/${run.run_id}`)}
            actions={[<RightOutlined key="enter" className="meta-text" />]}
          >
            <List.Item.Meta
              avatar={<BarChartOutlined className="history-report-icon" />}
              title={
                <Space size="middle" wrap>
                  <Typography.Text strong>{run.as_of_date}</Typography.Text>
                  <Tag color="blue">{run.trigger_endpoint}</Tag>
                  {run.regime_label ? <Tag>{run.regime_label}</Tag> : null}
                  <Tag color={getStatusColor(run.status)}>{getStatusText(run.status)}</Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={8}>
                  <Space wrap>
                    {run.data_freshness ? <Tag>新鲜度 {run.data_freshness}</Tag> : null}
                    <Tag color={run.degraded ? "warning" : "success"}>{run.degraded ? "存在缺失数据" : "数据状态正常"}</Tag>
                    {run.days ? <Tag>历史 {run.days} 天</Tag> : null}
                  </Space>
                  <Typography.Text type="secondary">
                    生成时间：{formatDateTime(run.generated_at)}
                  </Typography.Text>
                  {run.error_message ? (
                    <Typography.Text type="danger">{run.error_message}</Typography.Text>
                  ) : null}
                </Space>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
