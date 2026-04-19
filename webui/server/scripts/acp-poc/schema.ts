import { z } from 'zod';

export const contentBlockSchema: z.ZodTypeAny = z.lazy(() =>
  z.discriminatedUnion('type', [
    z.object({ type: z.literal('text'), text: z.string() }).passthrough(),
    z
      .object({
        type: z.literal('image'),
        data: z.string(),
        mimeType: z.string(),
      })
      .passthrough(),
    z
      .object({
        type: z.literal('audio'),
        data: z.string(),
        mimeType: z.string(),
      })
      .passthrough(),
    z
      .object({
        type: z.literal('resource_link'),
        uri: z.string(),
      })
      .passthrough(),
    z
      .object({
        type: z.literal('resource'),
        resource: z.any(),
      })
      .passthrough(),
  ])
);

const messageChunkUpdate = z
  .object({
    sessionUpdate: z.union([
      z.literal('user_message_chunk'),
      z.literal('agent_message_chunk'),
      z.literal('agent_thought_chunk'),
    ]),
    content: contentBlockSchema,
  })
  .passthrough();

const toolCallLocation = z.object({ path: z.string() }).passthrough();

const toolCallUpdate = z
  .object({
    sessionUpdate: z.literal('tool_call'),
    toolCallId: z.string(),
    title: z.string(),
    kind: z.string().optional(),
    status: z
      .enum(['pending', 'in_progress', 'completed', 'failed'])
      .optional(),
    content: z.array(z.any()).optional(),
    locations: z.array(toolCallLocation).optional(),
    rawInput: z.record(z.any()).optional(),
    rawOutput: z.record(z.any()).optional(),
  })
  .passthrough();

const toolCallUpdateUpdate = z
  .object({
    sessionUpdate: z.literal('tool_call_update'),
    toolCallId: z.string(),
    title: z.string().nullable().optional(),
    kind: z.string().nullable().optional(),
    status: z
      .enum(['pending', 'in_progress', 'completed', 'failed'])
      .nullable()
      .optional(),
    content: z.array(z.any()).nullable().optional(),
    locations: z.array(toolCallLocation).nullable().optional(),
    rawInput: z.record(z.any()).optional(),
    rawOutput: z.record(z.any()).optional(),
  })
  .passthrough();

const planUpdate = z
  .object({
    sessionUpdate: z.literal('plan'),
    entries: z.array(
      z
        .object({
          content: z.string(),
          priority: z.enum(['high', 'medium', 'low']),
          status: z.enum(['pending', 'in_progress', 'completed']),
        })
        .passthrough()
    ),
  })
  .passthrough();

const availableCommandsUpdate = z
  .object({
    sessionUpdate: z.literal('available_commands_update'),
    availableCommands: z.array(
      z.object({ name: z.string(), description: z.string() }).passthrough()
    ),
  })
  .passthrough();

const currentModeUpdate = z
  .object({
    sessionUpdate: z.literal('current_mode_update'),
    currentModeId: z.string(),
  })
  .passthrough();

export const sessionUpdateSchema = z.union([
  messageChunkUpdate,
  toolCallUpdate,
  toolCallUpdateUpdate,
  planUpdate,
  availableCommandsUpdate,
  currentModeUpdate,
]);

export const sessionNotificationSchema = z
  .object({
    sessionId: z.string(),
    update: sessionUpdateSchema,
  })
  .passthrough();

export type SessionNotificationValidated = z.infer<
  typeof sessionNotificationSchema
>;

export function validateSessionNotification(payload: unknown):
  | { ok: true; value: SessionNotificationValidated }
  | { ok: false; error: z.ZodError } {
  const parsed = sessionNotificationSchema.safeParse(payload);
  if (parsed.success) return { ok: true, value: parsed.data };
  return { ok: false, error: parsed.error };
}
