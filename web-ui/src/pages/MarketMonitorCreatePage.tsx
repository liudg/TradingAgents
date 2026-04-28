import {
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
  Space,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { useNavigate } from "react-router-dom";

import { useCreateMarketMonitorRun } from "../api/hooks";
import type { MarketMonitorRunRequest } from "../api/types";
import { extractErrorMessage } from "../utils/format";

interface MarketMonitorCreateFormValues {
  trigger_endpoint: "snapshot" | "history" | "data_status";
  as_of_date?: Dayjs;
  days?: number;
  force_refresh: boolean;
  provider?: string;
  model?: string;
  reasoning_effort?: string;
}

const runTypeOptions = [
  { label: "快照", value: "snapshot" },
  { label: "历史", value: "history" },
  { label: "数据状态", value: "data_status" },
] as const;

export function MarketMonitorCreatePage() {
  const [form] = Form.useForm<MarketMonitorCreateFormValues>();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const createRunMutation = useCreateMarketMonitorRun();
  const triggerEndpoint = Form.useWatch("trigger_endpoint", form);

  const handleSubmit = async (values: MarketMonitorCreateFormValues) => {
    try {
      const payload: MarketMonitorRunRequest = {
        trigger_endpoint: values.trigger_endpoint,
        as_of_date: values.as_of_date?.format("YYYY-MM-DD") || null,
        days: values.trigger_endpoint === "history" ? values.days || 20 : null,
        force_refresh: values.force_refresh,
        mode: values.trigger_endpoint,
        llm_config:
          values.provider || values.model || values.reasoning_effort
            ? {
                provider: values.provider?.trim() || null,
                model: values.model?.trim() || null,
                reasoning_effort: values.reasoning_effort?.trim() || null,
              }
            : null,
      };
      const result = await createRunMutation.mutateAsync(payload);
      message?.success?.(`运行已创建：${result.run_id}`);
      navigate(`/monitor/runs/${result.run_id}`);
    } catch (error) {
      message?.error?.(extractErrorMessage(error));
    }
  };

  return (
    <Card className="page-card" title="新建市场监控运行">
      <Form
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{ trigger_endpoint: "snapshot", days: 20, force_refresh: false }}
        onFinish={handleSubmit}
      >
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="运行类型" name="trigger_endpoint" rules={[{ required: true, message: "请选择运行类型" }]}>
              <Select options={runTypeOptions as never} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="交易日" name="as_of_date">
              <DatePicker style={{ width: "100%" }} disabledDate={(current) => (current ? current > dayjs().endOf("day") : false)} />
            </Form.Item>
          </Col>
          {triggerEndpoint === "history" ? (
            <Col xs={24} md={8}>
              <Form.Item label="历史天数" name="days" rules={[{ required: true, message: "请输入历史天数" }]}>
                <InputNumber min={1} max={60} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          ) : null}
          <Col xs={24}>
            <Form.Item name="force_refresh" valuePropName="checked" noStyle>
              <Checkbox>强制刷新数据</Checkbox>
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="LLM Provider" name="provider">
              <Input placeholder="例如 anthropic / openai / codex" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="模型" name="model">
              <Input placeholder="例如 claude-sonnet-4-6" />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item label="推理强度" name="reasoning_effort">
              <Input placeholder="例如 low / medium / high" />
            </Form.Item>
          </Col>
        </Row>
        <Space>
          <Button type="primary" htmlType="submit" loading={createRunMutation.isPending}>
            创建运行
          </Button>
          <Button onClick={() => navigate("/monitor")}>返回市场监控</Button>
        </Space>
      </Form>
    </Card>
  );
}
