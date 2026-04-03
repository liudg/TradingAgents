import {
  Alert,
  App,
  Button,
  Card,
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

import { useCreateAnalysisJob, useMetadataOptions } from "../api/hooks";
import { AnalystType, AnalysisJobRequest } from "../api/types";
import { extractErrorMessage } from "../utils/format";

interface AnalysisJobFormValues extends Omit<AnalysisJobRequest, "trade_date"> {
  trade_date: Dayjs;
}

const analystNameMap: Record<AnalystType, string> = {
  market: "市场技术分析师",
  social: "社交情绪分析师",
  news: "新闻分析师",
  fundamentals: "基本面分析师",
};

const outputLanguageOptions = [
  { label: "中文", value: "zh-CN" },
  { label: "英文", value: "en-US" },
];

export function CreateJobPage() {
  const [form] = Form.useForm<AnalysisJobFormValues>();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const metadataQuery = useMetadataOptions();
  const createJobMutation = useCreateAnalysisJob();
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
      trade_date: dayjs(),
      selected_analysts: metadataQuery.data.analysts,
      llm_provider: initialProvider,
      deep_think_llm: defaults.deep_think_llm || modelGroup.deep?.[0]?.value,
      quick_think_llm: defaults.quick_think_llm || modelGroup.quick?.[0]?.value,
      backend_url: defaults.backend_url ?? "",
      google_thinking_level: defaults.google_thinking_level ?? "",
      openai_reasoning_effort: defaults.openai_reasoning_effort ?? "",
      anthropic_effort: defaults.anthropic_effort ?? "",
      output_language: defaults.output_language || "zh-CN",
      max_debate_rounds: defaults.max_debate_rounds || 1,
      max_risk_discuss_rounds: defaults.max_risk_discuss_rounds || 1,
      max_recur_limit: defaults.max_recur_limit || 100,
    });
  }, [form, metadataQuery.data]);

  const handleProviderChange = (nextProvider: string) => {
    const modelGroup = metadataQuery.data?.models[nextProvider] || {};
    form.setFieldsValue({
      deep_think_llm: modelGroup.deep?.[0]?.value,
      quick_think_llm: modelGroup.quick?.[0]?.value,
    });
  };

  const handleSubmit = async (values: AnalysisJobFormValues) => {
    try {
      const payload: AnalysisJobRequest = {
        ...values,
        ticker: values.ticker.trim().toUpperCase(),
        trade_date: values.trade_date.format("YYYY-MM-DD"),
        backend_url: values.backend_url?.trim() || null,
        google_thinking_level: values.google_thinking_level?.trim() || null,
        openai_reasoning_effort:
          values.openai_reasoning_effort?.trim() || null,
        anthropic_effort: values.anthropic_effort?.trim() || null,
      };
      const result = await createJobMutation.mutateAsync(payload);
      message.success(`任务已创建：${result.job_id}`);
      navigate(`/jobs/${result.job_id}`);
    } catch (error) {
      message.error(extractErrorMessage(error));
    }
  };

  if (metadataQuery.isLoading) {
    return (
      <Card className="page-card">
        <Skeleton active paragraph={{ rows: 14 }} />
      </Card>
    );
  }

  if (metadataQuery.isError || !metadataQuery.data) {
    return (
      <Alert
        type="error"
        showIcon
        message="元数据加载失败"
        description={extractErrorMessage(metadataQuery.error)}
      />
    );
  }

  return (
    <Row gutter={[24, 24]}>
      <Col xs={24}>
        <Card className="page-card" title="新建投研分析任务">
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            requiredMark={false}
          >
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item
                  label="股票代码"
                  name="ticker"
                  rules={[{ required: true, message: "请输入股票代码" }]}
                >
                  <Input placeholder="例如 AAPL / TSLA / 0700.HK" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item
                  label="分析日期"
                  name="trade_date"
                  rules={[{ required: true, message: "请选择分析日期" }]}
                >
                  <DatePicker
                    style={{ width: "100%" }}
                    disabledDate={(current) =>
                      current ? current > dayjs().endOf("day") : false
                    }
                  />
                </Form.Item>
              </Col>

              <Col span={24}>
                <Form.Item
                  label="启用分析师"
                  name="selected_analysts"
                  rules={[{ required: true, message: "至少选择一类分析师" }]}
                >
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
                <Form.Item label="模型供应商" name="llm_provider">
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
                <Form.Item
                  label="深度推理模型"
                  name="deep_think_llm"
                  rules={[{ required: true, message: "请选择深度推理模型" }]}
                >
                  <Select options={providerModelOptions.deep} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  label="快速推理模型"
                  name="quick_think_llm"
                  rules={[{ required: true, message: "请选择快速推理模型" }]}
                >
                  <Select options={providerModelOptions.quick} />
                </Form.Item>
              </Col>

              <Col xs={24} md={8}>
                <Form.Item label="报告输出语言" name="output_language">
                  <Select options={outputLanguageOptions} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  label="Google Thinking Level"
                  name="google_thinking_level"
                >
                  <Input placeholder="可选" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  label="OpenAI Reasoning Effort"
                  name="openai_reasoning_effort"
                >
                  <Input placeholder="可选，例如 low / medium / high" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="Anthropic Effort" name="anthropic_effort">
                  <Input placeholder="可选" />
                </Form.Item>
              </Col>

              <Col xs={24} md={8}>
                <Form.Item label="研究员辩论轮数" name="max_debate_rounds">
                  <InputNumber min={1} max={10} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  label="风控辩论轮数"
                  name="max_risk_discuss_rounds"
                >
                  <InputNumber min={1} max={10} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item label="图递归上限" name="max_recur_limit">
                  <InputNumber min={1} max={300} style={{ width: "100%" }} />
                </Form.Item>
              </Col>
            </Row>

            <Space>
              <Button
                type="primary"
                htmlType="submit"
                loading={createJobMutation.isPending}
              >
                创建分析任务
              </Button>
              <Button onClick={() => form.resetFields()}>重置表单</Button>
            </Space>
          </Form>
        </Card>
      </Col>
    </Row>
  );
}
