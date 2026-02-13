"use client";

const colors: Record<string, string> = {
  queued: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/50",
  running: "bg-blue-500/20 text-blue-400 border border-blue-500/50",
  completed: "bg-green-500/20 text-green-400 border border-green-500/50",
  failed: "bg-red-500/20 text-red-400 border border-red-500/50",
  cancelled: "bg-orange-500/20 text-orange-400 border border-orange-500/50",
  passed: "bg-green-500/20 text-green-400 border border-green-500/50",
  error: "bg-red-500/20 text-red-400 border border-red-500/50",
  skipped: "bg-gray-500/20 text-gray-400 border border-gray-500/50",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status] || "bg-gray-500/20 text-gray-400 border border-gray-500/50"}`}
    >
      {status === "running" && (
        <span className="mr-1 h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
      )}
      {status}
    </span>
  );
}
