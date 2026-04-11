import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { StepIndicator } from './StepIndicator';
import { ProjectInfoStep } from './ProjectInfoStep';
import { StackProfileStep } from './StackProfileStep';
import { EnvVarsStep } from './EnvVarsStep';
import { ConfirmationStep } from './ConfirmationStep';
import { useCreateProject } from '../../hooks/useCreateProject';

interface ProjectWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProjectWizard({ open, onOpenChange }: ProjectWizardProps) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [profile, setProfile] = useState('custom');
  const createProject = useCreateProject();

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
        onSuccess: () => {
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
            {step === 3 && <ConfirmationStep name={name} path={path} profile={profile} />}
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
