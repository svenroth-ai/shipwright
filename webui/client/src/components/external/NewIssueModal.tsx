/*
 * Single modal; three render configurations keyed off the chosen action
 * (new-task / new-pipeline / new-iterate — all external_launch per AD-03.13).
 *
 * Iterate 3 section 03:
 *   - Consumes `useProjectFilter` to pick read-only context vs project dropdown.
 *   - Dual Save / Launch submit — Save goes to the Backlog (draft state), Launch
 *     creates + launches + copies to clipboard (FR-03.90/91).
 *   - Task mode: debounced classifyPhase on the title (250 ms) with null-fallback
 *     to phases[0] (O23).
 *   - Pipeline + Iterate modes: AutonomyToggle; Task mode omits it (FR-03.72).
 *   - Helper-box body distinguishes Save vs Launch semantics.
 *   - Footer is the single-line `<kbd>Esc</kbd> to cancel` hint (FR-03.92).
 *   - NO priority field anywhere (FR-03.21 regression).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import {
  createTask,
  launchExternalTask,
  type ActionDefinition,
  type PhaseDefinition,
  type ResolvedProjectActions,
} from "../../lib/externalApi";
import { useProjectFilter } from "../../hooks/useProjectFilter";
import { useProjects } from "../../hooks/useProjects";
import { classifyPhase } from "../../lib/classifyPhase";
import { UNASSIGNED_PROJECT_ID } from "../../lib/projectIds";
import { AutonomyToggle, type AutonomyValue } from "./AutonomyToggle";
import { ProjectContextStrip } from "./ProjectContextStrip";
import type { Project } from "../../types";

export interface NewIssueModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The action the user picked (primary button or dropdown). Drives mode. */
  action: ActionDefinition | null;
  /** Resolved actions for the ACTIVE project (or the fallback when "All"). */
  projectActions: ResolvedProjectActions | undefined;
  /** Callback the page uses to invalidate the task list after Save/Launch. */
  onTaskCreated?: () => void;
  /** Injected for tests — default uses navigator.clipboard.writeText. */
  writeToClipboard?: (text: string) => Promise<void>;
  /** Injected for tests. Default is a no-op — Save-to-Backlog success is
   *  already visible to the user via the task appearing in the Draft
   *  column (onTaskCreated invalidates the query). The previous
   *  `window.alert` default was an iterate-3 regression (see
   *  `~/.claude/plans/iterate-3-remediation.md` BUG 1 / Phase A3). */
  onToast?: (msg: string, sev: "info" | "error") => void;
}

type SubmitAction = "save" | "launch";

// 250 ms matches the mockup + O23 default in the section spec.
const PHASE_DEBOUNCE_MS = 250;

export function NewIssueModal({
  open,
  onOpenChange,
  action,
  projectActions,
  onTaskCreated,
  writeToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
  },
  onToast = () => {
    // No-op default. Tests inject a spy; the host page should pass a
    // real toaster when one exists. See `~/.claude/plans/iterate-3-remediation.md`
    // BUG 1 — the prior `window.alert` default blocked automation and was
    // hostile UX.
  },
}: NewIssueModalProps) {
  const navigate = useNavigate();
  const { activeProjectId } = useProjectFilter();
  const { data: projects = [] } = useProjects();

  const mode: "new-task" | "new-pipeline" | "new-iterate" =
    action?.id === "new-pipeline"
      ? "new-pipeline"
      : action?.id === "new-iterate"
        ? "new-iterate"
        : "new-task";

  const realProjects = useMemo(
    () => projects.filter((p) => !p.synthesized && p.id !== UNASSIGNED_PROJECT_ID),
    [projects],
  );
  const scopedProject: Project | undefined = useMemo(() => {
    if (!activeProjectId || activeProjectId === UNASSIGNED_PROJECT_ID) return undefined;
    return realProjects.find((p) => p.id === activeProjectId);
  }, [activeProjectId, realProjects]);

  // Controlled form state, reset on modal open.
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    scopedProject?.id ?? realProjects[0]?.id ?? "",
  );
  const [autonomy, setAutonomy] = useState<AutonomyValue>(
    projectActions?.defaults.autonomy ?? "guided",
  );
  const phases: PhaseDefinition[] = useMemo(
    () => projectActions?.phases ?? [],
    [projectActions],
  );
  const [phaseId, setPhaseId] = useState<string>(phases[0]?.id ?? "");
  const [phaseOverridden, setPhaseOverridden] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form every time the modal opens.
  useEffect(() => {
    if (!open) return;
    setTitle("");
    setDescription("");
    setError(null);
    setPhaseOverridden(false);
    setAutonomy(projectActions?.defaults.autonomy ?? "guided");
    setPhaseId(phases[0]?.id ?? "");
    setSelectedProjectId(scopedProject?.id ?? realProjects[0]?.id ?? "");
  }, [open, projectActions, phases, scopedProject, realProjects]);

  // Debounced phase classification — only when Task mode and user hasn't overridden.
  useEffect(() => {
    if (mode !== "new-task" || phaseOverridden || phases.length === 0) return;
    const handle = setTimeout(() => {
      const phaseIds = phases.map((p) => p.id);
      const guess = classifyPhase(title, phaseIds) ?? phaseIds[0] ?? "";
      setPhaseId(guess);
    }, PHASE_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [title, phases, phaseOverridden, mode]);

  const effectiveProjectId =
    scopedProject?.id ?? selectedProjectId ?? realProjects[0]?.id ?? "";
  const canSubmit =
    !submitting && title.trim().length > 0 && Boolean(effectiveProjectId);

  const selectedProject = useMemo<Project | undefined>(
    () => realProjects.find((p) => p.id === effectiveProjectId),
    [realProjects, effectiveProjectId],
  );

  const onSubmit = useCallback(
    async (ev: FormEvent, submitAction: SubmitAction) => {
      ev.preventDefault();
      if (!canSubmit || !selectedProject) return;
      setSubmitting(true);
      setError(null);
      try {
        const task = await createTask({
          title: title.trim(),
          cwd: selectedProject.path,
          pluginDirs: [],
          projectId: selectedProject.id,
        });

        if (submitAction === "save") {
          onTaskCreated?.();
          onOpenChange(false);
          onToast("Saved to Backlog", "info");
          return;
        }

        // Launch path — server transitions state first, then clipboard.
        const body: { description?: string; autonomy?: AutonomyValue } = {};
        if (description.trim()) body.description = description.trim();
        if (mode !== "new-task") body.autonomy = autonomy;
        const { commands } = await launchExternalTask(task.taskId, body);
        onTaskCreated?.();

        // Platform-default clipboard choice: PowerShell on Windows, POSIX elsewhere.
        const isWin =
          typeof navigator !== "undefined" &&
          /win/i.test(navigator.userAgent || "");
        const copyText = isWin ? commands.powershell : commands.posix;
        try {
          await writeToClipboard(copyText);
        } catch {
          onToast(
            "Copy failed — open TaskDetail to copy manually.",
            "error",
          );
          // Do NOT unwind the task — server already committed.
        }
        onOpenChange(false);
        navigate(`/tasks/${task.taskId}`);
      } catch (err) {
        setError(String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [
      canSubmit,
      selectedProject,
      title,
      description,
      autonomy,
      mode,
      navigate,
      onOpenChange,
      onTaskCreated,
      onToast,
      writeToClipboard,
    ],
  );

  if (!action) return null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]" />
        <Dialog.Content
          className="fixed left-1/2 top-[10%] z-50 w-[540px] max-w-[95vw] -translate-x-1/2 overflow-hidden rounded-[var(--radius-card,12px)] bg-white shadow-[var(--shadow-modal,0_20px_60px_rgba(0,0,0,0.28))]"
          data-testid={`new-issue-modal-${mode}`}
        >
          <div className="flex items-center gap-3 border-b border-[var(--color-border,#e0dbd4)] px-5 py-4">
            <div className="flex-1 min-w-0">
              <Dialog.Title className="text-[16px] font-bold text-neutral-900">
                {modeHeading(mode)}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-[12px] leading-[1.4] text-neutral-500">
                {modeSubheading(mode)}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                data-testid="new-issue-modal-close"
                className="rounded p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800"
              >
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>

          <form
            onSubmit={(e) => void onSubmit(e, "launch")}
            data-testid="new-issue-modal-form"
          >
            <div className="flex max-h-[calc(100vh-280px)] flex-col gap-4 overflow-y-auto px-5 py-4">
              {/* Project context or selector */}
              {scopedProject ? (
                <ProjectContextStrip
                  name={scopedProject.name}
                  color={scopedProject.settings?.color}
                  path={scopedProject.path}
                />
              ) : (
                <FieldLabel label="Project" required>
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    data-testid="new-issue-project-select"
                    className="w-full rounded-[var(--radius-button,8px)] border-[1.5px] border-[var(--color-border,#e0dbd4)] bg-white px-3 py-2 text-[13px]"
                    required
                  >
                    <option value="">Select project…</option>
                    {realProjects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </FieldLabel>
              )}

              {/* Title */}
              <FieldLabel
                label="Title"
                required
                hint={mode === "new-task" ? "auto-detects phase" : undefined}
              >
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  data-testid="new-issue-title-input"
                  placeholder="e.g. Fix login redirect bug"
                  className="w-full rounded-[var(--radius-button,8px)] border-[1.5px] border-[var(--color-border,#e0dbd4)] px-3 py-2 text-[13px] outline-none focus:border-[var(--color-primary,#6b5e56)]"
                  autoFocus
                  required
                />
              </FieldLabel>

              {/* Phase — Task mode only */}
              {mode === "new-task" && phases.length > 0 && (
                <FieldLabel
                  label="Phase"
                  hint="from this project's actions.json"
                >
                  <select
                    value={phaseId}
                    onChange={(e) => {
                      setPhaseId(e.target.value);
                      setPhaseOverridden(true);
                    }}
                    data-testid="new-issue-phase-select"
                    className="w-full rounded-[var(--radius-button,8px)] border-[1.5px] border-[var(--color-border,#e0dbd4)] bg-white px-3 py-2 text-[13px]"
                  >
                    {phases.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </FieldLabel>
              )}

              {/* Autonomy — Pipeline + Iterate only (FR-03.72) */}
              {mode !== "new-task" && (
                <FieldLabel label="Autonomy">
                  <AutonomyToggle value={autonomy} onChange={setAutonomy} />
                </FieldLabel>
              )}

              {/* Description */}
              <FieldLabel
                label="Description"
                hint="optional — becomes the first prompt Claude sees"
              >
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  data-testid="new-issue-description-input"
                  placeholder="What needs to be done? Link files, paste errors, reference FRs…"
                  className="min-h-[108px] w-full resize-y rounded-[var(--radius-button,8px)] border-[1.5px] border-[var(--color-border,#e0dbd4)] px-3 py-2 text-[13px] outline-none focus:border-[var(--color-primary,#6b5e56)]"
                />
              </FieldLabel>

              {/* Helper-box */}
              <div className="flex items-start gap-2 rounded-[var(--radius-button,8px)] border-l-[3px] border-[#F59E0B] bg-[#FEF3C7] px-3 py-2.5 text-[12px] leading-[1.55] text-[#92400E]">
                <div>
                  <strong className="font-semibold text-[#78350F]">
                    Save to Backlog:
                  </strong>{" "}
                  command is <em>not</em> copied — task parks in the Backlog
                  column until you start it.
                  <br />
                  <strong className="font-semibold text-[#78350F]">
                    Launch:
                  </strong>{" "}
                  command is copied to your clipboard + task moves to In
                  Progress + TaskDetail opens. Paste in your terminal; webui
                  follows the JSONL from there.
                </div>
              </div>

              {error && (
                <div
                  data-testid="new-issue-error"
                  className="text-[12px] text-[var(--color-error,#DC2626)]"
                >
                  {error}
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 border-t border-[var(--color-border,#e0dbd4)] bg-[var(--color-bg,#f5f0eb)] px-5 py-3">
              <div
                className="flex-1 text-[11px] text-neutral-500"
                data-testid="new-issue-footer-hint"
              >
                <kbd className="rounded border border-neutral-300 bg-white px-1.5 py-0.5 font-mono text-[10px]">
                  Esc
                </kbd>{" "}
                to cancel
              </div>
              <button
                type="button"
                data-testid="new-issue-save-btn"
                onClick={(e) => void onSubmit(e, "save")}
                disabled={!canSubmit}
                className="inline-flex items-center gap-1.5 rounded border-[1.5px] border-[var(--color-border,#e0dbd4)] bg-[var(--color-muted-bg,#ede8e1)] px-4 py-1.5 text-[13px] font-medium text-neutral-900 hover:bg-[var(--color-border,#e0dbd4)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Save to Backlog
              </button>
              <button
                type="submit"
                data-testid="new-issue-launch-btn"
                disabled={!canSubmit}
                className="inline-flex items-center gap-1.5 rounded bg-[var(--color-primary,#6b5e56)] px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-[var(--color-primary-hover,#5a4f48)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                Launch
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FieldLabel({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
        <span>{label}</span>
        {required && <span className="text-[var(--color-error,#DC2626)]">*</span>}
        {hint && (
          <span className="ml-auto text-[10px] font-medium normal-case tracking-normal opacity-80">
            {hint}
          </span>
        )}
      </label>
      {children}
    </div>
  );
}

function modeHeading(mode: "new-task" | "new-pipeline" | "new-iterate"): string {
  if (mode === "new-pipeline") return "New Pipeline";
  if (mode === "new-iterate") return "New Iterate";
  return "New Task";
}

function modeSubheading(
  mode: "new-task" | "new-pipeline" | "new-iterate",
): string {
  if (mode === "new-pipeline")
    return "Full Shipwright pipeline — project → design → plan → build → test → deploy → changelog. Save it to the Backlog, or Launch now.";
  if (mode === "new-iterate")
    return "Complexity-adaptive iterate skill against an existing project. Save or Launch.";
  return "Plain Claude — no Shipwright pipeline. Save it to the Backlog, or Launch now.";
}
