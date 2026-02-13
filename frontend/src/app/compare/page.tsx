"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import type { TestRunDetail } from "@/types";

interface CompareData {
  run1: TestRunDetail;
  run2: TestRunDetail;
}

export default function ComparePage() {
  const [id1, setId1] = useState("");
  const [id2, setId2] = useState("");
  const [data, setData] = useState<CompareData | null>(null);
  const [error, setError] = useState("");

  async function handleCompare(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const result = (await api.compareTestRuns(parseInt(id1), parseInt(id2))) as CompareData;
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to compare");
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Compare Test Runs</h1>

      <form onSubmit={handleCompare} className="flex gap-4 mb-8">
        <input
          type="number"
          value={id1}
          onChange={(e) => setId1(e.target.value)}
          placeholder="Run ID 1"
          required
          className="border rounded-lg px-3 py-2 w-32 bg-[var(--input-bg)] border-[var(--input-border)]"
        />
        <span className="self-center text-[var(--muted)]">vs</span>
        <input
          type="number"
          value={id2}
          onChange={(e) => setId2(e.target.value)}
          placeholder="Run ID 2"
          required
          className="border rounded-lg px-3 py-2 w-32 bg-[var(--input-bg)] border-[var(--input-border)]"
        />
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          Compare
        </button>
      </form>

      {error && <div className="text-red-500 mb-4">{error}</div>}

      {data && (
        <div className="grid grid-cols-2 gap-8">
          {[data.run1, data.run2].map((run) => (
            <div key={run.id} className="border border-[var(--card-border)] bg-[var(--card-bg)] rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">Run #{run.id} - PR #{run.pr_number}</h2>
                <StatusBadge status={run.status} />
              </div>
              <div className="text-sm text-[var(--muted)] mb-4">{run.pr_title || "No title"}</div>
              <div className="grid grid-cols-3 gap-2 mb-4 text-center text-sm">
                <div className="bg-green-900/30 border border-green-800 rounded p-2">
                  <div className="font-bold text-green-400">{run.passed_tests}</div>
                  <div className="text-green-500">Passed</div>
                </div>
                <div className="bg-red-900/30 border border-red-800 rounded p-2">
                  <div className="font-bold text-red-400">{run.failed_tests}</div>
                  <div className="text-red-500">Failed</div>
                </div>
                <div className="bg-blue-900/30 border border-blue-800 rounded p-2">
                  <div className="font-bold text-blue-400">{run.total_tests}</div>
                  <div className="text-blue-500">Total</div>
                </div>
              </div>
              <div className="space-y-1">
                {run.results.map((r) => (
                  <div key={r.id} className="flex items-center justify-between text-sm border-b border-[var(--card-border)] py-1">
                    <span className="truncate mr-2">{r.test_name}</span>
                    <StatusBadge status={r.status} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
