import { Empty } from "antd";
import ReactMarkdown from "react-markdown";

interface MarkdownPanelProps {
  content?: string | null;
  emptyText?: string;
}

export function MarkdownPanel({
  content,
  emptyText = "暂无内容",
}: MarkdownPanelProps) {
  if (!content || !content.trim()) {
    return <Empty description={emptyText} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div className="markdown-body">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
