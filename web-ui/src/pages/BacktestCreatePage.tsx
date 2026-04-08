import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Skeleton,
  Space,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateBacktestJob, useMetadataOptions } from "../api/hooks";
import { AnalystType, BacktestJobRequest } from "../api/types";
import { extractErrorMessage } from "../utils/format";

interface BacktestFormValues extends Omit<BacktestJobRequest, "start_date" | "end_date"> {
  start_date: Dayjs;
  end_date: Dayjs;
}

const analystNameMap: Record<AnalystType, string> = {
  market: "市场技术分析师",
  social: "社交情绪分析师",
  news: "新闻分析师",
  fundamentals: "基本面分析师",
};

export function BacktestCreatePage() {
  const [form] = Form.useForm<BacktestFormValues>();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const metadataQuery = useMetadataOptions();
  const createBacktestMutation = useCreateBacktestJob();
  const provider = Form.useWatch("llm_provider", form);

  const providerModelOptions = useMemo(() => {
    if (!metadataQuery.data || !provider) {
      return { deep: [], quick: [] };
    }
    const selected = metadataQuery.data.models[provider] || {};
    return {
      deep: selected.deep || [],
      quick: selected.quick || [],
    };
  }, [metadataQuery.data, provider]);

  useEffect(() => {
    if (!metadataQuery.data) {
      return;
    }
    const defaults = metadataQuery.data.default_config;
    const initialProvider =
      defaults.llm_provider || metadataQuery.data.llm_providers[0];
    const modelGroup = metadataQuery.data.models[initialProvider] || {};
    form.setFieldsValue({
      ticker: "AAPL",
      start_date: dayjs().subtract(30, "day"),
      end_date: dayjs().subtract(1, "day"),
      selected_analysts: metadataQuery.data.analysts,
      llm_provider: initialProvider,
      deep_think_llm: defaults.deep_think_llm || modelGroup.deep?.[0]?.value,
      quick_think_llm: defaults.quick_think_llm || modelGroup.quick?.[0]?.value,
      backend_url: defaults.backend_url,
      output_language: defaults.output_language,
      max_debate_rounds: defaults.max_debate_rounds || 1,
      max_risk_discuss_rounds: defaults.max_risk_discuss_rounds || 1,
      holding_period: 5,
      reflection_enabled: true,
      writeback_enabled: true,
      google_thinking_level: defaults.google_thinking_level,
      openai_reasoning_effort: defaults.openai_reasoning_effort,
      codex_reasoning_effort: defaults.codex_reasoning_effort,
      anthropic_effort: defaults.anthropic_effort,
    });
  }, [form, metadataQuery.data]);

  const handleProviderChange = (nextProvider: string) => {
    const modelGroup = metadataQuery.data?.models[nextProvider] || {};
    form.setFieldsValue({
      llm_provider: nextProvider,
      deep_think_llm: modelGroup.deep?.[0]?.value,
      quick_think_llm: modelGroup.quick?.[0]?.value,
    });
  };

  const handleSubmit = async (values: BacktestFormValues) => {
    try {
      const payload: BacktestJobRequest = {
        ticker: values.ticker.trim().toUpperCase(),
        start_date: values.start_date.format("YYYY-MM-DD"),
        end_date: values.end_date.format("YYYY-MM-DD"),
        selected_analysts: values.selected_analysts,
        llm_provider: values.llm_provider,
        deep_think_llm: values.deep_think_llm,
        quick_think_llm: values.quick_think_llm,
        backend_url: values.backend_url?.trim() || null,
        google_thinking_level:
          values.llm_provider === "google"
            ? values.google_thinking_level?.trim() || null
            : null,
        openai_reasoning_effort:
          values.llm_provider === "openai"
            ? values.openai_reasoning_effort?.trim() || null
            : null,
        codex_reasoning_effort:
          values.llm_provider === "codex"
            ? values.codex_reasoning_effort?.trim() || null
            : null,
        anthropic_effort:
          values.llm_provider === "anthropic"
            ? values.anthropic_effort?.trim() || null
            : null,
        output_language: values.output_language,
        max_debate_rounds: values.max_debate_rounds,
        max_risk_discuss_rounds: values.max_risk_discuss_rounds,
        holding_period: values.holding_period,
        reflection_enabled: values.reflection_enabled,
        writeback_enabled: values.writeback_enabled,
      };
      const result = await createBacktestMutation.mutateAsync(payload);
      message.success(`回测任务已创建：${result.job_id}`);
      navigate(`/backtests/${result.job_id}`);
    } catch (error) {
      message.error(extractErrorMessage(error));
    }
  };

  if (metadataQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 12 }} />
      </Card>
    );
  }

  if (metadataQuery.isError || !metadataQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="回测配置加载失败"
        description={extractErrorMessage(metadataQuery.error)}
      />
    );
  }

  return (
    <Card className="page-card" title="新建回测复盘任务">
      <Form form={form} layout="vertical" onFinish={handleSubmit} requiredMark={false}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="股票代码" name="ticker" rules={[{ required: true }]}>
              <Input placeholder="例如 AAPL / NVDA / TSLA" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="开始日期" name="start_date" rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="结束日期" name="end_date" rules={[{ required: true }]}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Col>

          <Col xs={24}>
            <Form.Item label="启用分析师" name="selected_analysts" rules={[{ required: true }]}>
              <Select
                mode="multiple"
                options={metadataQuery.data.analysts.map((item) => ({
                  label: analystNameMap[item] || item,
                  value: item,
                }))}
              />
            </Form.Item>
          </Col>

          <Col xs={24} md={8}>
            <Form.Item label="LLM Provider" name="llm_provider" rules={[{ required: true }]}>
              <Select
                options={metadataQuery.data.llm_providers.map((item) => ({
                  label: item,
                  value: item,
                }))}
                onChange={handleProviderChange}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="Deep Model" name="deep_think_llm" rules={[{ required: true }]}>
              <Select options={providerModelOptions.deep} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="Quick Model" name="quick_think_llm" rules={[{ required: true }]}>
              <Select options={providerModelOptions.quick} />
            </Form.Item>
          </Col>

          <Col xs={24} md={8}>
            <Form.Item label="持有期（交易日）" name="holding_period" rules={[{ required: true }]}>
              <InputNumber min={1} max={60} style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="研究辩论轮数" name="max_debate_rounds" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} style={{ width: "100%" }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="风控辩论轮数" name="max_risk_discuss_rounds" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} style={{ width: "100%" }} />
            </Form.Item>
          </Col>

          <Col xs={24} md={12}>
            <Form.Item label="Backend URL" name="backend_url">
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item label="输出语言" name="output_language" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>

          <Col xs={24}>
            <Space size="large">
              <Form.Item name="reflection_enabled" valuePropName="checked" noStyle>
                <Checkbox>启用 LLM 结构化复盘</Checkbox>
              </Form.Item>
              <Form.Item name="writeback_enabled" valuePropName="checked" noStyle>
                <Checkbox>将高价值复盘写回 memory</Checkbox>
              </Form.Item>
            </Space>
          </Col>
        </Row>

        <Form.Item style={{ marginTop: 24, marginBottom: 0 }}>
          <Space>
            <Button type="primary" htmlType="submit" loading={createBacktestMutation.isPending}>
              启动回测
            </Button>
            <Button onClick={() => navigate("/backtests/history")}>查看历史回测</Button>
          </Space>
        </Form.Item>
      </Form>
    </Card>
  );
}
