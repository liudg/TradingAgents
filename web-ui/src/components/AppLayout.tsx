import { Layout } from "antd";
import { PropsWithChildren } from "react";
import { Link, useLocation } from "react-router-dom";

const { Header, Content } = Layout;

const moduleTabs = [
  {
    key: "monitor",
    label: "市场监控",
    to: "/monitor",
    match: (pathname: string) => pathname.startsWith("/monitor"),
  },
  {
    key: "analysis",
    label: "个股分析",
    to: "/analysis",
    match: (pathname: string) =>
      pathname === "/analysis" ||
      pathname.startsWith("/jobs/") ||
      pathname.startsWith("/reports"),
  },
  {
    key: "backtest",
    label: "回测复盘",
    to: "/backtests",
    match: (pathname: string) => pathname.startsWith("/backtests"),
  },
];

export function AppLayout({ children }: PropsWithChildren) {
  const location = useLocation();

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <div className="app-header-inner">
          <Link to="/monitor" className="brand-link">
            <span className="brand-title">TradingAgents 投研分析控制台</span>
          </Link>

          <nav className="module-tabs" aria-label="主导航">
            {moduleTabs.map((tab) => {
              const isActive = tab.match(location.pathname);

              return (
                <Link
                  key={tab.key}
                  to={tab.to}
                  className={`module-tab${isActive ? " is-active" : ""}`}
                  aria-current={isActive ? "page" : undefined}
                >
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </Header>

      <Content className="content-wrap">{children}</Content>
    </Layout>
  );
}
