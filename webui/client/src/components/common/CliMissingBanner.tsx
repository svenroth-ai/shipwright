import { useCliCapability } from '../../hooks/useCliCapability';

export function CliMissingBanner() {
  const { cli, isLoading, refresh, isRefreshing } = useCliCapability();

  if (isLoading || !cli || cli.available) return null;

  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900"
    >
      <div className="min-w-0">
        <strong className="font-semibold">Claude Code CLI not found.</strong>{' '}
        Shipwright needs the <code className="rounded bg-amber-100 px-1">claude</code> CLI on your PATH to run tasks.{' '}
        <a
          href="https://docs.anthropic.com/en/docs/claude-code"
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2 hover:text-amber-950"
        >
          Install it →
        </a>
        {cli.error && (
          <span className="ml-2 text-xs text-amber-700">({cli.error})</span>
        )}
      </div>
      <button
        type="button"
        onClick={refresh}
        disabled={isRefreshing}
        className="shrink-0 rounded border border-amber-400 px-3 py-1 text-amber-900 hover:bg-amber-100 disabled:opacity-50"
      >
        {isRefreshing ? 'Retrying…' : 'Retry'}
      </button>
    </div>
  );
}
