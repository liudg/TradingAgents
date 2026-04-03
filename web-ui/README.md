# TradingAgents Web UI

中文投研分析前端控制台，基于 `React + TypeScript + Vite + Ant Design` 实现。

## 开发启动

先启动后端 API：

```bash
python -m tradingagents.web.app
```

再启动前端：

```bash
cd web-ui
npm install
npm run dev
```

前端默认运行在 `http://127.0.0.1:5173`，`/api` 请求会代理到 `http://127.0.0.1:8000`。

## 构建与测试

```bash
npm run build
npm run test
```
