import { Alert, Card, List, Skeleton, Space, Tag, Typography } from "antd";
import { RightOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";

import { useHistoricalBacktests } from "../api/hooks";
import { extractErrorMessage, formatDateTime } from "../utils/format";

function formatPercent(value?: number | null) {
  return value === null || value === undefined ? "-" : `${value.toFixed(2)}%`;
}

export function HistoricalBacktestsPage() {
  const navigate = useNavigate();
  const backtestsQuery = useHistoricalBacktests();

  if (backtestsQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 10 }} />
      </Card>
    );
  }

  if (backtestsQuery.isError || !backtestsQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="历史回测加载失败"
        description={extractErrorMessage(backtestsQuery.error)}
      />
    );
  }

  return (
    <Card className="page-card" title="历史回测实验">
      <List
        dataSource={backtestsQuery.data}
        locale={{ emptyText: "暂无历史回测实验" }}
        renderItem={(item) => (
          <List.Item
            className="history-report-item"
            onClick={() => navigate(`/backtests/${item.job_id}`)}
            actions={[<RightOutlined key="enter" className="meta-text" />]}
          >
            <List.Item.Meta
              title={
                <Space wrap>
                  <Typography.Text strong>{item.ticker}</Typography.Text>
                  <Typography.Text>
                    {item.start_date} ~ {item.end_date}
                  </Typography.Text>
                  <Tag color="blue">{item.llm_provider}</Tag>
                  <Tag>持有 {item.holding_period} 天</Tag>
                </Space>
              }
              description={
                <Space direction="vertical" size={6}>
                  <Typography.Text type="secondary">
                    生成时间：{formatDateTime(item.generated_at)}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    样本 {item.sample_count} / 已评估 {item.evaluated_count} / 胜率 {formatPercent(item.win_rate)} / 平均收益 {formatPercent(item.avg_return_pct)} / 平均超额 {formatPercent(item.excess_return_pct)}
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
