import "antd/dist/reset.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntdApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";

import { RootApp } from "./RootApp";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#1677ff",
          borderRadius: 10,
        },
      }}
    >
      <AntdApp>
        <RootApp />
      </AntdApp>
    </ConfigProvider>
  </React.StrictMode>,
);
