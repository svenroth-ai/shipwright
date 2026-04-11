export interface ChatCommand {
  command: string;
  description: string;
}

export const CHAT_COMMANDS: ChatCommand[] = [
  { command: '/shipwright-project', description: 'Decompose requirements' },
  { command: '/shipwright-design', description: 'Generate UI mockups' },
  { command: '/shipwright-plan', description: 'Create implementation plan' },
  { command: '/shipwright-build', description: 'Implement from plan' },
  { command: '/shipwright-test', description: 'Run tests' },
  { command: '/shipwright-deploy', description: 'Deploy application' },
  { command: '/shipwright-iterate', description: 'Iterate on changes' },
  { command: '/shipwright-changelog', description: 'Generate changelog' },
];
