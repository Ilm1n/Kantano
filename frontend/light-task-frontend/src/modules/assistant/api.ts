import { apiInstance, API_BASE_URL } from '@/api/config/axios-instance';
import { apiClient } from '@/api/config';
import { getAccessToken, setAccessTokenValue } from '@/modules/auth/lib/access-token';

export type Conversation = {
  id: string;
  projectId: number;
  title: string;
  mode: 'local' | 'cloud';
  createdAt: string;
  updatedAt: string;
};

export type AssistantMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  references: Array<{ type: string; id: number; title?: string }>;
  createdAt: string;
};

export type ActionStep = {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  display?: Record<string, unknown>;
};

export type AssistantRun = {
  id: string;
  status: string;
  provider: string | null;
  model: string | null;
  stepCount: number;
  fallbackUsed: boolean;
  proposedAction: { name: string; args: Record<string, unknown>; display?: Record<string, unknown> & { steps?: ActionStep[] }; action_id?: string; tool_call_id?: string } | null;
  result: Record<string, unknown> | null;
};

export type ChatDetail = {
  conversation: Conversation;
  messages: AssistantMessage[];
  latestRun: AssistantRun | null;
};

export type StreamEvent =
  | { type: 'run'; data: { run_id: string; status: string } }
  | { type: 'delta'; data: { text: string } }
  | { type: 'reset'; data: Record<string, never> }
  | { type: 'approval_required'; data: { action: AssistantRun['proposedAction']; provider: string; model: string } }
  | { type: 'done'; data: { status: string; message: string; provider: string; model: string } }
  | { type: 'error'; data: { message: string; run_id: string } };

const path = (projectId: number, chatId?: string) =>
  `/projects/${projectId}/assistant/conversations${chatId ? `/${chatId}` : ''}`;

export async function listConversations(projectId: number): Promise<Conversation[]> {
  const response = await apiInstance.get<Conversation[]>(path(projectId));
  return response.data;
}

export async function createConversation(projectId: number): Promise<Conversation> {
  const response = await apiInstance.post<Conversation>(path(projectId), { title: 'Новый чат' });
  return response.data;
}

export async function getConversation(projectId: number, chatId: string): Promise<ChatDetail> {
  const response = await apiInstance.get<ChatDetail>(path(projectId, chatId));
  return response.data;
}

export async function deleteConversation(projectId: number, chatId: string): Promise<void> {
  await apiInstance.delete(path(projectId, chatId));
}

export async function streamAssistant(
  projectId: number,
  chatId: string,
  route: string,
  body: Record<string, unknown>,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const url = `${API_BASE_URL}/api${path(projectId, chatId)}${route}`;
  const open = () => fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
    },
    body: JSON.stringify(body),
  });
  let response = await open();
  if (response.status === 401) {
    const refreshed = await apiClient.auth.refreshJwtApiAuthRefreshPost();
    setAccessTokenValue(refreshed.accessToken);
    response = await open();
  }
  if (!response.ok || !response.body) {
    throw new Error(`Запрос помощника не выполнен (${response.status})`);
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
