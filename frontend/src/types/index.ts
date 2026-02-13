export interface TestRun {
  id: number;
  pr_number: number;
  pr_title: string | null;
  commit_sha: string | null;
  target_hosts: string;
  target_username: string | null;
  target_password: string | null;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  protocols: string | null;
  kerberos: boolean;
  verbose: boolean;
  show_errors: boolean;
  ai_review_enabled: boolean;
  line_nums: string | null;
  not_tested: boolean;
  dns_server: string | null;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  ai_review_status: string | null;
  ai_summary: string | null;
}

export interface TestResult {
  id: number;
  test_name: string;
  target_host: string | null;
  status: "passed" | "failed" | "skipped" | "error";
  duration: number | null;
  output: string | null;
  error_message: string | null;
}

export interface TestRunDetail extends TestRun {
  results: TestResult[];
}

export interface TestRunList {
  items: TestRun[];
  total: number;
  page: number;
  per_page: number;
}

export interface LogEntry {
  id: number;
  timestamp: string;
  log_line: string;
  level: string;
}
