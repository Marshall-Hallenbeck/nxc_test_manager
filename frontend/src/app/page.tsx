"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useClaudeAvailability } from "@/lib/claude";

const PROTOCOLS = ["smb", "wmi", "ldap", "winrm", "mssql", "rdp", "ssh", "ftp", "nfs"];

type SourceMode = "pr" | "branch";

interface PROption {
  number: number;
  title: string;
  user: string;
  state: string;
}

export default function Home() {
  return (
    <Suspense fallback={<div className="text-[var(--muted)]">Loading...</div>}>
      <SubmitForm />
    </Suspense>
  );
}

function SubmitForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sourceMode, setSourceMode] = useState<SourceMode>("pr");
  const [prNumber, setPrNumber] = useState("");
  const [prQuery, setPrQuery] = useState("");
  const [prOptions, setPrOptions] = useState<PROption[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [prLoading, setPrLoading] = useState(false);
  const [branch, setBranch] = useState("");
  const [repo, setRepo] = useState("");
  const [targetHosts, setTargetHosts] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [selectedProtocols, setSelectedProtocols] = useState<string[]>([]);
  const [kerberos, setKerberos] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const [aiReview, setAiReview] = useState(false);
  const { claudeAvailable, claudeUnavailableReason } = useClaudeAvailability();
  const [lineNums, setLineNums] = useState("");
  const [notTested, setNotTested] = useState(false);
  const [dnsServer, setDnsServer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  const justSelected = useRef(false);

  // Pre-fill form from query params (used by Re-run)
  useEffect(() => {
    const pr = searchParams.get("pr_number");
    const branchParam = searchParams.get("branch");
    const repoParam = searchParams.get("repo");

    if (branchParam) {
      setSourceMode("branch");
      setBranch(branchParam);
    } else if (pr) {
      setSourceMode("pr");
      setPrNumber(pr);
      setPrQuery(`#${pr}`);
      api.searchPRs(pr).then((results) => {
        const match = results.find((r) => r.number === Number(pr));
        if (match) setPrQuery(`#${match.number} - ${match.title}`);
      }).catch(() => {});
    }

    if (repoParam) setRepo(repoParam);

    const hosts = searchParams.get("target_hosts");
    if (hosts) setTargetHosts(hosts);

    const user = searchParams.get("target_username");
    if (user) setUsername(user);

    const pass = searchParams.get("target_password");
    if (pass) setPassword(pass);

    const protocols = searchParams.get("protocols");
    if (protocols) setSelectedProtocols(protocols.split(",").filter(Boolean));

    if (searchParams.get("kerberos") === "true") setKerberos(true);
    if (searchParams.get("verbose") === "true") setVerbose(true);
    if (searchParams.get("show_errors") === "true") setShowErrors(true);
    if (searchParams.get("ai_review") === "true") setAiReview(true);

    const lineNumsParam = searchParams.get("line_nums");
    if (lineNumsParam) setLineNums(lineNumsParam);

    if (searchParams.get("not_tested") === "true") setNotTested(true);

    const dnsServerParam = searchParams.get("dns_server");
    if (dnsServerParam) setDnsServer(dnsServerParam);
  }, []);

  function toggleProtocol(proto: string) {
    setSelectedProtocols((prev) =>
      prev.includes(proto) ? prev.filter((p) => p !== proto) : [...prev, proto]
    );
  }

  // Debounced PR search
  useEffect(() => {
    if (!prQuery) {
      setPrOptions([]);
      return;
    }
    if (justSelected.current) {
      justSelected.current = false;
      return;
    }
    const timer = setTimeout(async () => {
      setPrLoading(true);
      try {
        const results = await api.searchPRs(prQuery);
        setPrOptions(results);
        setHighlightedIndex(-1);
        setShowDropdown(true);
      } catch {
        setPrOptions([]);
      } finally {
        setPrLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [prQuery]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function selectPR(pr: PROption) {
    justSelected.current = true;
    setPrNumber(String(pr.number));
    setPrQuery(`#${pr.number} - ${pr.title}`);
    setShowDropdown(false);
    setPrOptions([]);
  }

  const canSubmit =
    sourceMode === "pr" ? !!prNumber : !!branch;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      const data: Record<string, unknown> = {};

      if (sourceMode === "pr") {
        data.pr_number = parseInt(prNumber);
      } else {
        data.branch = branch;
      }

      if (repo) data.repo = repo;
      if (targetHosts) data.target_hosts = targetHosts;
      if (username) data.target_username = username;
      if (password) data.target_password = password;
      if (selectedProtocols.length > 0) data.protocols = selectedProtocols;
      if (kerberos) data.kerberos = true;
      if (verbose) data.verbose = true;
      if (showErrors) data.show_errors = true;
      if (aiReview && claudeAvailable) data.ai_review = true;
      if (lineNums) data.line_nums = lineNums;
      if (notTested) data.not_tested = true;
      if (dnsServer) data.dns_server = dnsServer;

      const result = (await api.createTestRun(data as Parameters<typeof api.createTestRun>[0])) as { id: number };
      setPassword("");
      router.push(`/runs/${result.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit test");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Submit Test Run</h1>

      <form onSubmit={handleSubmit} className="max-w-lg space-y-4">
        {/* Source mode toggle */}
        <div>
          <label className="block text-sm font-medium mb-2">Test Source *</label>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="sourceMode"
                checked={sourceMode === "pr"}
                onChange={() => setSourceMode("pr")}
                className="accent-blue-500"
              />
              PR Number
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="sourceMode"
                checked={sourceMode === "branch"}
                onChange={() => setSourceMode("branch")}
                className="accent-blue-500"
              />
              Branch
            </label>
          </div>
        </div>

        {/* PR number input (shown in PR mode) */}
        {sourceMode === "pr" && (
          <div ref={dropdownRef} className="relative">
            <label className="block text-sm font-medium mb-1">Pull Request</label>
            <input
              type="text"
              value={prQuery}
              onChange={(e) => {
                const val = e.target.value;
                setPrQuery(val);
                const num = val.replace(/^#/, "").trim();
                if (/^\d+$/.test(num)) {
                  setPrNumber(num);
                } else {
                  setPrNumber("");
                }
              }}
              onKeyDown={(e) => {
                if (!showDropdown || prOptions.length === 0) return;
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setHighlightedIndex((prev) =>
                    prev < prOptions.length - 1 ? prev + 1 : 0
                  );
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setHighlightedIndex((prev) =>
                    prev > 0 ? prev - 1 : prOptions.length - 1
                  );
                } else if (e.key === "Enter" && highlightedIndex >= 0) {
                  e.preventDefault();
                  selectPR(prOptions[highlightedIndex]);
                } else if (e.key === "Escape") {
                  setShowDropdown(false);
                }
              }}
              onFocus={() => {
                if (prOptions.length > 0) setShowDropdown(true);
                else if (!prQuery) {
                  setPrQuery(" ");
                  setTimeout(() => setPrQuery(""), 0);
                  setPrLoading(true);
                  api.searchPRs("").then((results) => {
                    setPrOptions(results);
                    setShowDropdown(true);
                  }).catch(() => {}).finally(() => setPrLoading(false));
                }
              }}
              placeholder="Type PR # or search by title..."
              className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
              autoComplete="off"
            />
            {prNumber && (
              <div className="absolute right-3 top-[2.1rem] text-xs text-[var(--muted)]">
                PR #{prNumber}
              </div>
            )}
            {prLoading && (
              <div className="absolute right-3 top-[2.1rem] text-xs text-[var(--muted)]">
                Searching...
              </div>
            )}
            {showDropdown && prOptions.length > 0 && (
              <div className="absolute z-50 mt-1 w-full max-h-64 overflow-y-auto bg-[var(--card-bg)] border border-[var(--card-border)] rounded-lg shadow-xl">
                {prOptions.map((pr, idx) => (
                  <button
                    key={pr.number}
                    type="button"
                    ref={idx === highlightedIndex ? (el) => el?.scrollIntoView({ block: "nearest" }) : undefined}
                    onClick={() => selectPR(pr)}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={`w-full text-left px-3 py-2 transition-colors border-b border-[var(--card-border)] last:border-b-0 ${
                      idx === highlightedIndex ? "bg-white/15" : "hover:bg-white/10"
                    }`}
                  >
                    <span className="text-[var(--accent)] font-medium">#{pr.number}</span>
                    <span className="ml-2">{pr.title}</span>
                    <span className="ml-2 text-xs text-[var(--muted)]">by {pr.user}</span>
                  </button>
                ))}
              </div>
            )}
            {showDropdown && !prLoading && prQuery && prOptions.length === 0 && (
              <div className="absolute z-50 mt-1 w-full bg-[var(--card-bg)] border border-[var(--card-border)] rounded-lg shadow-xl px-3 py-2 text-sm text-[var(--muted)]">
                No open PRs found. You can still enter a PR number directly.
              </div>
            )}
          </div>
        )}

        {/* Branch input (shown in branch mode) */}
        {sourceMode === "branch" && (
          <div>
            <label className="block text-sm font-medium mb-1">Branch Name</label>
            <input
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              placeholder="e.g. main, feature/my-branch"
              className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
            />
          </div>
        )}

        {/* Repository (optional, both modes) */}
        <div>
          <label className="block text-sm font-medium mb-1">Repository</label>
          <input
            type="text"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="Pennyw0rth/NetExec"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
          <p className="text-xs text-[var(--muted)] mt-1">
            Optional. Use owner/name format to test a fork. Leave empty for default repo.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Target Host(s)</label>
          <input
            type="text"
            value={targetHosts}
            onChange={(e) => setTargetHosts(e.target.value)}
            placeholder="Leave empty for default"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
          <p className="text-xs text-[var(--muted)] mt-1">
            Single IP, comma-separated IPs, CIDR subnet, or mixed. Empty = use server default.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">DNS Server</label>
          <input
            type="text"
            value={dnsServer}
            onChange={(e) => setDnsServer(e.target.value)}
            placeholder="e.g. 192.168.33.1"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
          <p className="text-xs text-[var(--muted)] mt-1">
            Required for Kerberos/domain environments. Leave empty to use system default.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Leave empty for default"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="text"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Leave empty for default"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Test Line Numbers</label>
          <input
            type="text"
            value={lineNums}
            onChange={(e) => setLineNums(e.target.value)}
            placeholder="e.g. 5,10-15,20"
            className="w-full border rounded-lg px-3 py-2 bg-[var(--input-bg)] border-[var(--input-border)]"
          />
          <p className="text-xs text-[var(--muted)] mt-1">
            Run only specific test lines or ranges from e2e_tests.py. Leave empty to run all tests.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Protocols</label>
          <div className="flex flex-wrap gap-2">
            {PROTOCOLS.map((proto) => (
              <button
                key={proto}
                type="button"
                onClick={() => toggleProtocol(proto)}
                className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                  selectedProtocols.includes(proto)
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-[var(--card-bg)] border-[var(--card-border)] hover:border-blue-400"
                }`}
              >
                {proto.toUpperCase()}
              </button>
            ))}
          </div>
          <p className="text-xs text-[var(--muted)] mt-1">
            Select specific protocols to test, or leave all unselected to run all tests.
          </p>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium mb-1">Options</label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={kerberos}
              onChange={(e) => setKerberos(e.target.checked)}
              className="rounded"
            />
            Use Kerberos authentication
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={verbose}
              onChange={(e) => setVerbose(e.target.checked)}
              className="rounded"
            />
            Verbose output (show full command output)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showErrors}
              onChange={(e) => setShowErrors(e.target.checked)}
              className="rounded"
            />
            Show errors from commands
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={notTested}
              onChange={(e) => setNotTested(e.target.checked)}
              className="rounded"
            />
            Show not-tested commands
          </label>
          <label className="flex items-center gap-2 text-sm" title={!claudeAvailable ? claudeUnavailableReason : undefined}>
            <input
              type="checkbox"
              checked={aiReview}
              disabled={!claudeAvailable || sourceMode === "branch"}
              onChange={(e) => {
                const checked = e.target.checked;
                setAiReview(checked);
                if (checked) {
                  setVerbose(true);
                  setShowErrors(true);
                }
              }}
              className="rounded"
            />
            <span className={!claudeAvailable || sourceMode === "branch" ? "text-[var(--muted)]" : ""}>
              AI review (Claude analyzes PR diff + test results on completion)
              {!claudeAvailable && <span className="ml-1 text-yellow-400/70">(unavailable)</span>}
              {sourceMode === "branch" && claudeAvailable && <span className="ml-1 text-yellow-400/70">(PR only)</span>}
            </span>
          </label>
          {aiReview && (!verbose || !showErrors) && (
            <p className="text-xs text-yellow-400 ml-6">
              Verbose output and show errors are recommended for AI review to provide enough context.
            </p>
          )}
        </div>

        {error && (
          <div className="bg-red-900/50 text-red-200 px-4 py-2 rounded-lg text-sm border border-red-800">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || !canSubmit}
          className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Submitting..." : "Run Tests"}
        </button>
      </form>
    </div>
  );
}
