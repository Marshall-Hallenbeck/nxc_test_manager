"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import type { TestRun, TestRunList } from "@/types";

export default function RunsPage() {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadRuns() {
    setLoading(true);
    try {
      const data = (await api.listTestRuns({
        page,
        status: statusFilter || undefined,
      })) as TestRunList;
      setRuns(data.items);
      setTotal(data.total);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRuns();
    const interval = setInterval(loadRuns, 5000);
    return () => clearInterval(interval);
  }, [page, statusFilter]);

  async function handleCancel(id: number) {
    if (!confirm("Cancel this test run?")) return;
    try {
      await api.cancelTestRun(id);
      loadRuns();
    } catch {
      /* ignore */
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Test Runs</h1>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
        >
          <option value="">All statuses</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      {loading && runs.length === 0 ? (
        <div className="text-[var(--muted)]">Loading...</div>
      ) : runs.length === 0 ? (
        <div className="text-[var(--muted)]">No test runs found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-[var(--card-border)] text-left text-sm text-[var(--muted)]">
                <th className="py-3 pr-4">PR</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Targets</th>
                <th className="py-3 pr-4">Results</th>
                <th className="py-3 pr-4">Created</th>
                <th className="py-3"></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-[var(--card-border)] hover:bg-[var(--card-bg)]">
                  <td className="py-3 pr-4">
                    <Link
                      href={`/runs/${run.id}`}
                      className="text-blue-500 hover:underline font-medium"
                    >
                      #{run.pr_number}
                    </Link>
                    {run.pr_title && (
                      <div className="text-sm text-[var(--muted)] truncate max-w-xs">
                        {run.pr_title}
                      </div>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="py-3 pr-4 text-sm text-[var(--muted)]">
                    {run.target_hosts}
                  </td>
                  <td className="py-3 pr-4 text-sm">
                    {run.total_tests > 0 ? (
                      <span>
                        <span className="text-green-500">{run.passed_tests}</span>
                        /{run.total_tests}
                        {run.failed_tests > 0 && (
                          <span className="text-red-500 ml-1">
                            ({run.failed_tests} failed)
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-[var(--muted)]">-</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-sm text-[var(--muted)]">
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                  <td className="py-3">
                    {(run.status === "queued" || run.status === "running") && (
                      <button
                        onClick={() => handleCancel(run.id)}
                        className="text-orange-500 hover:text-orange-400 text-sm"
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > 20 && (
        <div className="flex gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 border border-[var(--card-border)] rounded disabled:opacity-50 bg-[var(--card-bg)]"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-sm text-[var(--muted)]">
            Page {page} of {Math.ceil(total / 20)}
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page * 20 >= total}
            className="px-3 py-1 border border-[var(--card-border)] rounded disabled:opacity-50 bg-[var(--card-bg)]"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
