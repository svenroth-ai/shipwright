import { useState } from "react";
import type { CopyCommandForms } from "../../lib/externalApi";

interface Props {
  commands: CopyCommandForms;
  os?: "windows" | "posix";
}

/**
 * Three rows on Windows (PowerShell default, cmd.exe fallback, POSIX for
 * WSL/git-bash); one row on macOS/Linux (POSIX). Round-3 plan integration
 * flagged two Windows sub-buttons as a hard UX requirement.
 */
export function CopyCommandCard({ commands, os }: Props) {
  const detected = os ?? (typeof navigator !== "undefined" && /windows/i.test(navigator.userAgent) ? "windows" : "posix");
  return (
    <div className="flex flex-col gap-2 rounded border border-blue-200 bg-blue-50 p-3" data-testid="copy-command-card">
      <div className="text-sm font-semibold text-blue-900">
        Copy + paste into your terminal — Claude Code starts there, webui observes the JSONL.
      </div>
      {detected === "windows" ? (
        <>
          <Row label="PowerShell" value={commands.powershell} testId="copy-ps" />
          <Row label="cmd.exe"    value={commands.cmd}        testId="copy-cmd" />
          <Row label="POSIX"      value={commands.posix}      testId="copy-posix" />
        </>
      ) : (
        <Row label="POSIX" value={commands.posix} testId="copy-posix" />
      )}
    </div>
  );
}

function Row({ label, value, testId }: { label: string; value: string; testId: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="flex items-center gap-2" data-testid={testId}>
      <span className="w-24 shrink-0 text-xs font-semibold">{label}</span>
      <code className="flex-1 overflow-x-auto whitespace-nowrap rounded bg-white px-2 py-1 text-xs">{value}</code>
      <button
        type="button"
        onClick={copy}
        className="rounded border border-blue-300 bg-white px-2 py-1 text-xs text-blue-700 hover:bg-blue-100"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
