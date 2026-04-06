import {
  ExperimentOutlined,
  FileTextOutlined,
  PlusCircleOutlined,
} from "@ant-design/icons";
import { Button, Layout, Space } from "antd";
import { PropsWithChildren } from "react";
import { Link, useLocation } from "react-router-dom";

const { Header, Content } = Layout;

export function AppLayout({ children }: PropsWithChildren) {
  const location = useLocation();

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <div>
          <Link to="/">
            <span className="brand-title">TradingAgents 投研分析控制台</span>
          </Link>
        </div>

        <Space>
          {!location.pathname.startsWith("/backtests") ? (
            <Link to="/backtests">
              <Button icon={<ExperimentOutlined />}>回测复盘</Button>
            </Link>
          ) : null}

          {location.pathname !== "/backtests/history" ? (
            <Link to="/backtests/history">
              <Button icon={<ExperimentOutlined />}>历史回测</Button>
            </Link>
          ) : null}

          {location.pathname !== "/reports" ? (
            <Link to="/reports">
              <Button icon={<FileTextOutlined />}>历史分析报告</Button>
            </Link>
          ) : null}

          {location.pathname !== "/" ? (
            <Link to="/">
              <Button type="primary" icon={<PlusCircleOutlined />}>
                新建分析任务
              </Button>
            </Link>
          ) : null}
        </Space>
      </Header>

      <Content className="content-wrap">{children}</Content>
    </Layout>
  );
}
