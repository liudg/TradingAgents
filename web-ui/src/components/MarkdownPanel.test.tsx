import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownPanel } from "./MarkdownPanel";

describe("MarkdownPanel", () => {
  it("renders markdown content", () => {
    render(
      <MarkdownPanel
        content={`# 结论

- 建议关注`}
      />,
    );
    expect(screen.getByRole("heading", { name: "结论" })).toBeInTheDocument();
    expect(screen.getByText("建议关注")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<MarkdownPanel content="" emptyText="暂无报告" />);
    expect(screen.getByText("暂无报告")).toBeInTheDocument();
  });
});
