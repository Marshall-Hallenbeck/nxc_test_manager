"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useClaudeAvailability } from "@/lib/claude";
import Markdown from "react-markdown";
import StatusBadge from "@/components/StatusBadge";
import LogViewer from "@/components/LogViewer";
import type { TestRunDetail } from "@/types";

type StatusFilter = "all" | "passed" | "failed" | "skipped" | "error";

export default function TestRunDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);
  const [run, setRun] = useState<TestRunDetail | null>(null);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [reviewRequesting, setReviewRequesting] = useState(false);
  const { claudeAvailable, claudeUnavailableReason } = useClaudeAvailability();
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [resultsPage, setResultsPage] = useState(1);
  const RESULTS_PER_PAGE = 10;

  function toggleSection(section: string) {
    setCollapsedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  }

  // Handle hash navigation on load and hash change
  useEffect(() => {
    function scrollToHash() {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      // Ensure the target section is expanded
      setCollapsedSections((prev) => ({ ...prev, [hash]: false }));
      // Allow DOM to update before scrolling
      setTimeout(() => {
        document.getElementById(hash)?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    }
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

  const [reviewTriggered, setReviewTriggered] = useState(false);

  const loadRun = useCallback(async () => {
    try {
      const data = (await api.getTestRun(id)) as TestRunDetail;
      setRun(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }, [id]);

  useEffect(() => {
    loadRun();
    const interval = setInterval(loadRun, 5000);
    return () => clearInterval(interval);
  }, [loadRun]);

  // Auto-trigger AI review when run completes with ai_review_enabled
  // Only if there are actual test results to review (skip infrastructure failures)
  // Skip if Claude CLI is unavailable
  const runStatus = run?.status;
  const aiEnabled = run?.ai_review_enabled;
  const aiStatus = run?.ai_review_status;
  const totalTests = run?.total_tests ?? 0;

  useEffect(() => {
    if (
      claudeAvailable &&
      aiEnabled &&
      !reviewTriggered &&
      !aiStatus &&
      (runStatus === "completed" || runStatus === "failed") &&
      totalTests > 0
    ) {
      setReviewTriggered(true);
      api.reviewTestRun(id);
    }
  }, [id, runStatus, aiEnabled, aiStatus, totalTests, reviewTriggered, claudeAvailable]);

  async function handleCancel() {
    if (!confirm("Cancel this test run?")) return;
    try {
      await api.cancelTestRun(id);
      loadRun();
    } catch {
      /* ignore */
    }
  }

  function extractCommand(testName: string): string {
    // Strip timestamp prefix like "[15:07:31] " and any leading whitespace
    return testName.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, "").trim();
  }

  function handleCopy(e: React.MouseEvent, resultId: number, testName: string) {
    e.stopPropagation(); // Don't toggle expand
    const cmd = extractCommand(testName);
    navigator.clipboard.writeText(cmd);
    setCopiedId(resultId);
    setTimeout(() => setCopiedId(null), 1500);
  }

  async function handleReview() {
    setReviewRequesting(true);
    try {
      await api.reviewTestRun(id);
      loadRun();
    } catch {
      /* loadRun will pick up the error state */
    } finally {
      setReviewRequesting(false);
    }
  }

  function handleRerun() {
    if (!run) return;
    const params = new URLSearchParams();
    if (run.pr_number) params.set("pr_number", String(run.pr_number));
    if (run.branch) params.set("branch", run.branch);
    if (run.repo) params.set("repo", run.repo);
    if (run.target_hosts) params.set("target_hosts", run.target_hosts);
    if (run.target_username) params.set("target_username", run.target_username);
    if (run.target_password) params.set("target_password", run.target_password);
    if (run.protocols) params.set("protocols", run.protocols);
    if (run.kerberos) params.set("kerberos", "true");
    if (run.verbose) params.set("verbose", "true");
    if (run.show_errors) params.set("show_errors", "true");
    if (run.ai_review_enabled) params.set("ai_review", "true");
    if (run.line_nums) params.set("line_nums", run.line_nums);
    if (run.not_tested) params.set("not_tested", "true");
    if (run.dns_server) params.set("dns_server", run.dns_server);
    router.push(`/?${params.toString()}`);
  }

  if (error) return <div className="text-red-500">{error}</div>;
  if (!run) return <div className="text-muted">Loading...</div>;

  const isActive = run.status === "queued" || run.status === "running";

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">
            {run.pr_number ? `PR #${run.pr_number}` : run.branch || "Test Run"}
            {run.pr_title && (
              <span className="text-muted text-xl ml-3">{run.pr_title}</span>
            )}
          </h1>
          <div className="flex items-center gap-3 mt-2 text-sm text-muted">
            <StatusBadge status={run.status} subStatus={run.sub_status || (run.ai_review_status === "running" ? "AI reviewing" : null)} />
            {run.commit_sha && <span>SHA: {run.commit_sha.slice(0, 7)}</span>}
            {run.repo && run.repo !== "Pennyw0rth/NetExec" && <span>Repo: {run.repo}</span>}
            <span>Targets: {run.target_hosts}</span>
          </div>
        </div>
        <div className="flex gap-2">
          {isActive && (
            <button
              onClick={handleCancel}
              className="bg-orange-500 text-white px-4 py-2 rounded-lg hover:bg-orange-600"
            >
              Cancel Test
            </button>
          )}
          {!isActive && (
            <>
              <button
                onClick={handleReview}
                disabled={!claudeAvailable || reviewRequesting || run.ai_review_status === "running"}
                title={!claudeAvailable ? claudeUnavailableReason : undefined}
                className="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 disabled:opacity-50"
              >
                {!claudeAvailable ? "Review Unavailable" : run.ai_review_status === "running" ? "Reviewing..." : "Review with Claude"}
              </button>
              <button
                onClick={handleRerun}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
              >
                Re-run
              </button>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-card border border-card-border rounded-lg p-4">
          <div className="text-sm text-muted">Created</div>
          <div>{new Date(run.created_at).toLocaleString()}</div>
        </div>
        <div className="bg-card border border-card-border rounded-lg p-4">
          <div className="text-sm text-muted">Started</div>
          <div>{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</div>
        </div>
        <div className="bg-card border border-card-border rounded-lg p-4">
          <div className="text-sm text-muted">Completed</div>
          <div>{run.completed_at ? new Date(run.completed_at).toLocaleString() : "-"}</div>
        </div>
      </div>

      {run.total_tests > 0 && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-green-900/30 border border-green-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{run.passed_tests}</div>
            <div className="text-sm text-green-500">Passed</div>
          </div>
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-red-400">{run.failed_tests}</div>
            <div className="text-sm text-red-500">Failed</div>
          </div>
          <div className="bg-blue-900/30 border border-blue-800 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{run.total_tests}</div>
            <div className="text-sm text-blue-500">Total</div>
          </div>
        </div>
      )}

      {run.results.length > 0 && (
        <div className="mb-6" id="results">
          <div className="flex items-center justify-between mb-3 group">
            <h2
              onClick={() => toggleSection("results")}
              className="text-xl font-semibold flex items-center gap-2 cursor-pointer select-none"
            >
              <span className={`text-sm text-muted transition-transform ${collapsedSections.results ? "-rotate-90" : ""}`}>▾</span>
              Test Results
              <a href="#results" onClick={(e) => e.stopPropagation()} className="text-muted opacity-0 group-hover:opacity-100 text-sm transition-opacity">#</a>
            </h2>
            {!collapsedSections.results && (
              <div className="flex gap-1">
                {(["all", "passed", "failed", "skipped", "error"] as StatusFilter[]).map((f) => {
                  const count = f === "all"
                    ? run.results.length
                    : run.results.filter((r) => r.status === f).length;
                  if (f !== "all" && count === 0) return null;
                  return (
                    <button
                      key={f}
                      onClick={() => { setStatusFilter(f); setResultsPage(1); }}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                        statusFilter === f
                          ? f === "passed" ? "bg-green-500/30 text-green-300 border border-green-500/50"
                            : f === "failed" ? "bg-red-500/30 text-red-300 border border-red-500/50"
                            : f === "error" ? "bg-red-500/30 text-red-300 border border-red-500/50"
                            : f === "skipped" ? "bg-gray-500/30 text-gray-300 border border-gray-500/50"
                            : "bg-accent/20 text-accent border border-accent/50"
                          : "bg-card text-muted border border-card-border hover:text-foreground"
                      }`}
                    >
                      {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)} ({count})
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          {!collapsedSections.results && (() => {
            const filtered = run.results.filter((r) => statusFilter === "all" || r.status === statusFilter);
            const totalPages = Math.ceil(filtered.length / RESULTS_PER_PAGE);
            const paged = filtered.slice((resultsPage - 1) * RESULTS_PER_PAGE, resultsPage * RESULTS_PER_PAGE);
            return (<>
            <div className="space-y-2">
              {paged.map((result) => (
                <div key={result.id} className="border border-card-border bg-card rounded-lg overflow-hidden">
                  <button
                    onClick={() => setExpandedId(expandedId === result.id ? null : result.id)}
                    className="w-full p-3 flex items-center justify-between text-left hover:bg-white/5 transition-colors"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={`text-lg flex-shrink-0 ${result.status === "passed" ? "text-green-400" : result.status === "failed" ? "text-red-400" : "text-gray-400"}`}>
                        {result.status === "passed" ? "✔" : result.status === "failed" ? "✘" : "○"}
                      </span>
                      <div className="min-w-0">
                        <div className="font-medium truncate">{result.test_name}</div>
                        <div className="text-xs text-muted flex gap-3">
                          {result.target_host && <span>Target: {result.target_host}</span>}
                          {result.duration != null && <span>{result.duration.toFixed(1)}s</span>}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={(e) => handleCopy(e, result.id, result.test_name)}
                        className="px-2 py-1 rounded text-xs text-muted hover:text-foreground hover:bg-white/10 transition-colors"
                        title="Copy command"
                      >
                        {copiedId === result.id ? "Copied!" : "Copy"}
                      </button>
                      <StatusBadge status={result.status} />
                      <span className={`text-muted text-sm transition-transform ${expandedId === result.id ? "rotate-180" : ""}`}>
                        ▾
                      </span>
                    </div>
                  </button>
                  {expandedId === result.id && (
                    <div className="border-t border-card-border p-3">
                      {result.error_message && (
                        <div className="mb-3 p-2 bg-red-900/20 border border-red-800 rounded text-sm text-red-300">
                          {result.error_message}
                        </div>
                      )}
                      {result.output ? (
                        <pre className="text-xs text-muted bg-black/40 rounded p-3 overflow-x-auto max-h-80 overflow-y-auto whitespace-pre-wrap break-words">
                          {result.output}
                        </pre>
                      ) : (
                        <div className="text-sm text-muted">No output captured.</div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-3">
                <button
                  onClick={() => setResultsPage((p) => Math.max(1, p - 1))}
                  disabled={resultsPage === 1}
                  className="px-3 py-1 border border-card-border rounded disabled:opacity-50 bg-card text-sm"
                >
                  Previous
                </button>
                <span className="text-sm text-muted">
                  Page {resultsPage} of {totalPages} ({filtered.length} results)
                </span>
                <button
                  onClick={() => setResultsPage((p) => Math.min(totalPages, p + 1))}
                  disabled={resultsPage === totalPages}
                  className="px-3 py-1 border border-card-border rounded disabled:opacity-50 bg-card text-sm"
                >
                  Next
                </button>
              </div>
            )}
            </>);
          })()}
        </div>
      )}

      {(run.ai_review_status === "running" || run.ai_summary) && (
        <div className="mb-6" id="ai-review">
          <div className="flex items-center mb-3 group">
            <h2
              onClick={() => toggleSection("ai-review")}
              className="text-xl font-semibold flex items-center gap-2 cursor-pointer select-none"
            >
              <span className={`text-sm text-muted transition-transform ${collapsedSections["ai-review"] ? "-rotate-90" : ""}`}>▾</span>
              AI Review
              <a href="#ai-review" onClick={(e) => e.stopPropagation()} className="text-muted opacity-0 group-hover:opacity-100 text-sm transition-opacity">#</a>
            </h2>
          </div>
          {!collapsedSections["ai-review"] && (
            <div className="bg-card border border-purple-800/50 rounded-lg p-4">
              {run.ai_review_status === "running" && !run.ai_summary && (
                <div className="flex items-center gap-3 text-muted">
                  <div className="animate-spin h-4 w-4 border-2 border-purple-400 border-t-transparent rounded-full" />
                  Claude is reviewing this PR and test results...
                </div>
              )}
              {run.ai_summary && (
                <div className={`prose dark:prose-invert prose-sm max-w-none ${run.ai_review_status === "failed" ? "text-red-300" : ""}`}>
                  <Markdown>{run.ai_summary}</Markdown>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div id="logs">
        <div className="flex items-center mb-3 group">
          <h2
            onClick={() => toggleSection("logs")}
            className="text-xl font-semibold flex items-center gap-2 cursor-pointer select-none"
          >
            <span className={`text-sm text-muted transition-transform ${collapsedSections.logs ? "-rotate-90" : ""}`}>▾</span>
            {isActive ? "Live Logs" : "Logs"}
            <a href="#logs" onClick={(e) => e.stopPropagation()} className="text-muted opacity-0 group-hover:opacity-100 text-sm transition-opacity">#</a>
          </h2>
        </div>
        {!collapsedSections.logs && <LogViewer testRunId={id} />}
      </div>
    </div>
  );
}
