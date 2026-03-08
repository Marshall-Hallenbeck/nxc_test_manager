import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/react";
import StatusBadge from "@/components/StatusBadge";

describe("StatusBadge", () => {
  // Ensure cleanup between tests
  afterEach(() => cleanup());

  it("renders the status text", () => {
    const { getByText } = render(<StatusBadge status="completed" />);
    expect(getByText("completed")).toBeInTheDocument();
  });

  it("applies green styling for completed status", () => {
    const { getByText } = render(<StatusBadge status="completed" />);
    const badge = getByText("completed");
    expect(badge.className).toContain("bg-green-500/20");
    expect(badge.className).toContain("text-green-400");
  });

  it("applies red styling for failed status", () => {
    const { getByText } = render(<StatusBadge status="failed" />);
    expect(getByText("failed").className).toContain("bg-red-500/20");
  });

  it("applies blue styling for running status", () => {
    const { getByText } = render(<StatusBadge status="running" />);
    expect(getByText("running").className).toContain("bg-blue-500/20");
  });

  it("shows animated pulse for running status", () => {
    const { container } = render(<StatusBadge status="running" />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("does not show pulse for non-running status", () => {
    const { container } = render(<StatusBadge status="completed" />);
    expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
  });

  it("applies yellow styling for queued status", () => {
    const { getByText } = render(<StatusBadge status="queued" />);
    expect(getByText("queued").className).toContain("bg-yellow-500/20");
  });

  it("applies orange styling for cancelled status", () => {
    const { getByText } = render(<StatusBadge status="cancelled" />);
    expect(getByText("cancelled").className).toContain("bg-orange-500/20");
  });

  it("applies default gray styling for unknown status", () => {
    const { getByText } = render(<StatusBadge status="unknown" />);
    expect(getByText("unknown").className).toContain("bg-gray-500/20");
  });
});
