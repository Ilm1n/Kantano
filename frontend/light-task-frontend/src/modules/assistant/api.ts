import { API_BASE_URL } from '@/api/config/axios-instance';
import { apiClient } from '@/api/config';
import { getAccessToken, setAccessTokenValue } from '@/modules/auth/lib/access-token';

import type {
  ActionStep, ChatDetail as ApiChatDetail, ConversationRead, MessageRead, RunRead,
} from '@/api/client';
import { ApiError } from '@/api/client';
import { getErrorMessage } from '@/utils/error';

export type { ActionStep };
export type Conversation = Omit<ConversationRead, 'mode'> & { mode: `${ConversationRead.mode}` };
export type AssistantMessage = Omit<MessageRead, 'role'> & { role: `${MessageRead.role}` };
export type AssistantRun = Omit<RunRead, 'status' | 'createdAt' | 'updatedAt'> & {
  status: `${RunRead.status}`;
};
export type ChatDetail = Omit<ApiChatDetail, 'conversation' | 'messages' | 'latestRun'> & {
  conversation: Conversation;
  messages: AssistantMessage[];
  latestRun: AssistantRun | null;
};

export type StreamEvent =
  | { type: 'run'; data: { run_id: string; status: AssistantRun['status'] } }
  | { type: 'delta'; data: { text: string } }
  | { type: 'reset'; data: Record<string, never> }
  | { type: 'approval_required'; data: { action: AssistantRun['proposedAction']; provider: string; model: string } }
  | { type: 'done'; data: { status: AssistantRun['status']; message: string; provider?: string; model?: string } }
  | { type: 'error'; data: { message: string; run_id: string } };

const path = (projectId: number, chatId?: string) =>
  `/projects/${projectId}/assistant/conversations${chatId ? `/${chatId}` : ''}`;

export async function listConversations(projectId: number): Promise<Conversation[]> {
  return apiClient.assistant.listConversationsApiProjectsProjectIdAssistantConversationsGet(projectId);
}

export async function createConversation(projectId: number): Promise<Conversation> {
  return apiClient.assistant.createConversationApiProjectsProjectIdAssistantConversationsPost(
    projectId, { title: 'Новый чат' },
  );
}

export async function getConversation(projectId: number, chatId: string): Promise<ChatDetail> {
  return apiClient.assistant.getConversationApiProjectsProjectIdAssistantConversationsConversationIdGet(
    projectId, chatId,
  );
}

export async function deleteConversation(projectId: number, chatId: string): Promise<void> {
  await apiClient.assistant.deleteConversationApiProjectsProjectIdAssistantConversationsConversationIdDelete(
    projectId, chatId,
  );
}

export async function stopRun(projectId: number, chatId: string, runId: string): Promise<void> {
  await apiClient.assistant.stopRunApiProjectsProjectIdAssistantConversationsConversationIdRunsRunIdStopPost(
    projectId, chatId, runId,
  );
}

export async function streamAssistant(
  projectId: number,
  chatId: string,
  route: string,
  body: Record<string, unknown>,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_BASE_URL}/api${path(projectId, chatId)}${route}`;
  const open = () => fetch(url, {
    method: 'POST',
    credentials: 'include',
    signal,
    headers: {
      'Content-Type': 'application/json',
      ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });
  let response = await open();
  if (response.status === 401) {
    const refreshed = await apiClient.auth.refreshJwtApiAuthRefreshPost();
    signal?.throwIfAborted();
    setAccessTokenValue(refreshed.accessToken);
    response = await open();
  }
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new Error(getErrorMessage(new ApiError({ method: 'POST', url }, {
      url, ok: response.ok, status: response.status, statusText: response.statusText, body,
    }, `Запрос помощника не выполнен (${response.status})`)));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const name = block.split('\n').find((line) => line.startsWith('event: '))?.slice(7);
      const payload = block.split('\n').find((line) => line.startsWith('data: '))?.slice(6);
      if (name && payload) onEvent({ type: name, data: JSON.parse(payload) } as StreamEvent);
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }
}
