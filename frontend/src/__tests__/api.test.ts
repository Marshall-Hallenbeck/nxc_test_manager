import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Import after mocking
import { api } from "@/lib/api";

beforeEach(() => {
  mockFetch.mockReset();
});

function mockOk(data: unknown) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => data,
  });
}

function mockError(status: number, detail: string) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    statusText: "Error",
    json: async () => ({ detail }),
  });
}

describe("api.createTestRun", () => {
  it("sends POST with pr_number", async () => {
    mockOk({ id: 1, pr_number: 123, status: "queued" });

    const result = await api.createTestRun({ pr_number: 123 });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ pr_number: 123 }),
      })
    );
    expect(result).toEqual({ id: 1, pr_number: 123, status: "queued" });
  });

  it("includes optional fields when provided", async () => {
    mockOk({ id: 2, status: "queued" });

    await api.createTestRun({
      pr_number: 456,
      target_hosts: "10.0.0.1",
      target_username: "admin",
      target_password: "pass",
    });

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.target_hosts).toBe("10.0.0.1");
    expect(body.target_username).toBe("admin");
    expect(body.target_password).toBe("pass");
  });

  it("throws on API error", async () => {
    mockError(400, "Invalid PR number");
    await expect(api.createTestRun({ pr_number: -1 })).rejects.toThrow("Invalid PR number");
  });
});

describe("api.listTestRuns", () => {
  it("sends GET with no params", async () => {
    mockOk({ items: [], total: 0, page: 1, per_page: 20 });

    await api.listTestRuns();

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/runs?",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  it("includes query params when provided", async () => {
    mockOk({ items: [], total: 0, page: 2, per_page: 20 });

    await api.listTestRuns({ page: 2, status: "running" });

    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toContain("page=2");
    expect(url).toContain("status=running");
  });
});

describe("api.cancelTestRun", () => {
  it("sends POST to cancel endpoint", async () => {
    mockOk({ status: "cancelled" });

    await api.cancelTestRun(5);

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/runs/5/cancel",
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("api.deleteTestRun", () => {
  it("sends DELETE request", async () => {
    mockOk({ status: "deleted" });

    await api.deleteTestRun(3);

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/runs/3",
      expect.objectContaining({ method: "DELETE" })
    );
  });
});

describe("api.compareTestRuns", () => {
  it("sends GET with run1 and run2 params", async () => {
    mockOk({ run1: {}, run2: {} });

    await api.compareTestRuns(1, 2);

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/runs/compare?run1=1&run2=2",
      expect.anything()
    );
  });
});
