export type InboxStatus = "pending" | "answered";

export interface InboxItem {
  id: string;
  projectId: string;
  taskId: string;
  question: string;
  context?: string;
  options?: string[];
  answer?: string;
  status: InboxStatus;
  createdAt: string;
  answeredAt?: string;
}
