import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

import { useDiagnostics } from "../../hooks/useDiagnostics";

/**
 * Persistent banner when the installed Claude CLI is below MIN_SUPPORTED_CLI
 * or can't be found on PATH. Replaces the pre-Plan D'' `CliMissingBanner`
 * which read from the old `capability-probe` endpoint.
 */
export function DiagnosticsBanner() {
  const { data } = useDiagnostics();
  if (!data) return null;
  const { claudeCli } = data;
  if (claudeCli.supported) return null;

  return (
    <div
      className="flex items-center gap-2 border-b border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-900"
      data-testid="diagnostics-banner"
    >
      <AlertTriangle size={14} />
      <span className="font-semibold">Claude Code CLI {claudeCli.raw ? "outdated" : "not found"}.</span>
      <span>
        {claudeCli.raw
          ? `Detected ${claudeCli.raw}; need ≥ ${claudeCli.minSupported}.`
          : "Shipwright needs the `claude` CLI on your PATH to observe external sessions."}
      </span>
      <Link to="/diagnostics" className="ml-auto underline">
        Diagnostics →
      </Link>
    </div>
  );
}
