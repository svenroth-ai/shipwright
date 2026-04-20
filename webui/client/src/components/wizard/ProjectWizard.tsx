import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { StepIndicator } from './StepIndicator';
import { ProjectInfoStep } from './ProjectInfoStep';
import { StackProfileStep } from './StackProfileStep';
import { EnvVarsStep } from './EnvVarsStep';
import { ConfirmationStep } from './ConfirmationStep';
import { useCreateProject } from '../../hooks/useCreateProject';
import { useSaveActionsStub } from '../../hooks/useProjectActions';
import { useSettings } from '../../hooks/useSettings';

interface ProjectWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DOCS_ACTIONS_URL = 'https://github.com/svenroth-ai/shipwright#actions-schema';

/** Section 03 (iterate 3) — "Which workflow plugin?" radio options. */
type WorkflowChoice = 'shipwright' | 'custom';

export function ProjectWizard({ open, onOpenChange }: ProjectWizardProps) {
  const { data: settings } = useSettings();
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [profile, setProfile] = useState(settings?.defaultProfile ?? 'custom');
  // Section 03 — workflow choice lives in the wizard's Confirmation step
  // behind a "Show advanced options" accordion. Default is "shipwright" so
  // the overwhelming majority never sees the toggle. "custom" writes an
  // empty .webui/actions.json stub + opens the docs page.
  const [workflowChoice, setWorkflowChoice] = useState<WorkflowChoice>('shipwright');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const createProject = useCreateProject();
  const saveStub = useSaveActionsStub();

  function handleNext() {
    if (step < 3) setStep(step + 1);
  }

  function handleBack() {
    if (step > 0) setStep(step - 1);
  }

  function handleCreate() {
    createProject.mutate(
      { name, path, profile },
      {
        onSuccess: async (created) => {
          // Section 03 — Custom branch writes the .webui/actions.json stub
          // on the just-created project and pops the docs page. Shipwright
          // branch is a no-op (bundled default applies at load time).
          if (workflowChoice === 'custom') {
            try {
              await saveStub.mutateAsync({ projectId: created.id });
              if (typeof window !== 'undefined') {
                window.open(DOCS_ACTIONS_URL, '_blank', 'noopener,noreferrer');
              }
            } catch (err) {
              // Non-fatal — the project is created; the user can re-trigger
              // the stub later via Settings. Log and continue closing.
              console.error('saveActionsStub failed', err);
            }
          }
          onOpenChange(false);
          resetForm();
        },
      },
    );
  }

  function resetForm() {
    setStep(0);
    setName('');
    setPath('');
    setProfile('custom');
    setWorkflowChoice('shipwright');
    setShowAdvanced(false);
  }

  const canProceed = step === 0 ? name.trim() && path.trim() : true;
  const isLastStep = step === 3;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl p-6 w-full max-w-[560px] z-50">
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900">
              New Project
            </Dialog.Title>
            <Dialog.Description className="sr-only">Create a new Shipwright project</Dialog.Description>
            <Dialog.Close asChild>
              <button className="p-1 rounded hover:bg-gray-100" aria-label="Close">
                <X size={18} className="text-gray-400" />
              </button>
            </Dialog.Close>
          </div>

          <StepIndicator currentStep={step} />

          <div className="min-h-[200px]">
            {step === 0 && <ProjectInfoStep name={name} path={path} onNameChange={setName} onPathChange={setPath} />}
            {step === 1 && <StackProfileStep profile={profile} onProfileChange={setProfile} />}
            {step === 2 && <EnvVarsStep profile={profile} />}
            {step === 3 && (
              <>
                <ConfirmationStep name={name} path={path} profile={profile} />
                {/* Section 03 — Workflow plugin selection, behind an
                    accordion so the defaults-first path is frictionless (G2). */}
                <details
                  className="mt-4 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm"
                  open={showAdvanced}
                  onToggle={(e) =>
                    setShowAdvanced((e.target as HTMLDetailsElement).open)
                  }
                  data-testid="wizard-advanced-accordion"
                >
                  <summary className="cursor-pointer select-none text-gray-600 hover:text-gray-900">
                    Show advanced options
                  </summary>
                  <div className="mt-3 space-y-3" data-testid="wizard-workflow-choice">
                    <p className="text-xs text-gray-500">Which workflow plugin?</p>
                    <label className="flex items-start gap-2 rounded border border-gray-200 bg-white p-2 text-xs">
                      <input
                        type="radio"
                        name="workflow-choice"
                        checked={workflowChoice === 'shipwright'}
                        onChange={() => setWorkflowChoice('shipwright')}
                        data-testid="wizard-workflow-shipwright"
                        className="mt-0.5"
                      />
                      <span>
                        <strong className="font-semibold">Shipwright (recommended)</strong>
                        <br />
                        <span className="text-gray-500">
                          Use the bundled actions preset — 3 actions, 9 phases, preview gate.
                        </span>
                      </span>
                    </label>
                    <label className="flex items-start gap-2 rounded border border-gray-200 bg-white p-2 text-xs">
                      <input
                        type="radio"
                        name="workflow-choice"
                        checked={workflowChoice === 'custom'}
                        onChange={() => setWorkflowChoice('custom')}
                        data-testid="wizard-workflow-custom"
                        className="mt-0.5"
                      />
                      <span>
                        <strong className="font-semibold">Custom</strong>
                        <br />
                        <span className="text-gray-500">
                          Write your own <code className="rounded bg-gray-100 px-1 font-mono">.webui/actions.json</code>.
                          An empty structured stub is created on project creation; docs open in a new tab.
                        </span>
                      </span>
                    </label>
                  </div>
                </details>
              </>
            )}
          </div>

          <div className="flex justify-between mt-6">
            <button
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
              onClick={step === 0 ? () => onOpenChange(false) : handleBack}
            >
              {step === 0 ? 'Cancel' : 'Back'}
            </button>
            <button
              disabled={!canProceed || createProject.isPending}
              className="px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50"
              onClick={isLastStep ? handleCreate : handleNext}
            >
              {isLastStep ? (createProject.isPending ? 'Creating...' : 'Create Project') : 'Next'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
