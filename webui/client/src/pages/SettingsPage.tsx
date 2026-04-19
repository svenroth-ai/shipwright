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
    </div>
  );
}
