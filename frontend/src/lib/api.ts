const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  createTestRun(data: {
    pr_number: number;
    target_hosts?: string;
    target_username?: string;
    target_password?: string;
    protocols?: string[];
    kerberos?: boolean;
    verbose?: boolean;
    show_errors?: boolean;
    ai_review?: boolean;
    line_nums?: string;
    not_tested?: boolean;
    dns_server?: string;
  }) {
    return fetchAPI("/api/runs", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  listTestRuns(params?: { page?: number; status?: string; pr_number?: number }) {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.status) query.set("status", params.status);
    if (params?.pr_number) query.set("pr_number", String(params.pr_number));
    return fetchAPI(`/api/runs?${query}`);
  },

  getTestRun(id: number) {
    return fetchAPI(`/api/runs/${id}`);
  },

  cancelTestRun(id: number) {
    return fetchAPI(`/api/runs/${id}/cancel`, { method: "POST" });
  },

  deleteTestRun(id: number) {
    return fetchAPI(`/api/runs/${id}`, { method: "DELETE" });
  },

  getTestRunLogs(id: number) {
    return fetchAPI(`/api/runs/${id}/logs`);
  },

  compareTestRuns(run1: number, run2: number) {
    return fetchAPI(`/api/runs/compare?run1=${run1}&run2=${run2}`);
  },

  reviewTestRun(id: number) {
    return fetchAPI<{ status: string }>(`/api/runs/${id}/review`, { method: "POST" });
  },

  searchPRs(query: string) {
    return fetchAPI<{ number: number; title: string; user: string; state: string }[]>(
      `/api/runs/prs?q=${encodeURIComponent(query)}`
    );
  },
};
