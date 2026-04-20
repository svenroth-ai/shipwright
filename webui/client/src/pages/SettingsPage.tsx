/*
 * Settings — minimal stub for Plan D'' variant-a.
 *
 * The pre-Plan-D'' SettingsPage managed chat-mode / autonomy / phase-mapping
 * / model selector config. All of those vanish in the external-launch
 * architecture (the user's own Claude client owns them).
 *
 * This stub is intentionally near-empty. A real "Launcher preferences" tab
 * (default launcher choice, VSCode executable override, claude executable
 * override, plugin dir list) belongs in a follow-up iterate when the
 * Terminal + VSCode launchers actually ship.
 */

import { Link } from "react-router-dom";

export default function SettingsPage() {
  return (
    <div className="flex h-full flex-col gap-4 p-4" data-testid="settings-page">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-neutral-500">
          The pre-Plan-D'' settings (chat model, permission mode, phase mapping) no longer apply
          to the external-launch architecture. See <Link to="/diagnostics" className="underline">Diagnostics</Link> for
          the CLI + launcher state, and configure your preferred settings in your own Claude client.
        </p>
      </header>

      <section className="rounded border border-neutral-200 bg-white p-4 text-sm">
        <h2 className="mb-1 font-semibold">Launcher preferences</h2>
        <p className="text-neutral-500">
          Terminal / VSCode / Desktop launcher overrides land in a future iterate. Today the
          "Copy command" launcher is the only available path.
        </p>
      </section>

      {/* Section 03 (iterate 3) — actions.json stub link. Read-only; the
          full in-app editor is deferred past iterate 3. */}
      <section
        className="rounded border border-neutral-200 bg-white p-4 text-sm"
        data-testid="settings-configure-actions"
      >
        <h2 className="mb-1 font-semibold">Configure actions</h2>
        <p className="text-neutral-500">
          Each project declares its `+ New ▾` dropdown entries, phase allowlist, and
          preview gate in{" "}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[12px]">
            &lt;project.path&gt;/.webui/actions.json
          </code>
          . The in-app editor is coming in a future iterate — for now, check the{" "}
          <a
            href="https://github.com/svenroth-ai/shipwright#actions-schema"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-primary)] underline"
          >
            actions schema docs
          </a>{" "}
          for the shape.
        </p>
      </section>
    </div>
  );
}
