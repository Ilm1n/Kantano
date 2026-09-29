import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { nextTick } from 'vue';
import { getConversation, listConversations, streamAssistant } from '../api';
import type { ChatDetail } from '../api';
import { useAssistantStore } from './assistant.store';

vi.mock('@/modules/projects/store/projects.store', () => ({
  useProjectsStore: () => ({ projects: [{ id: 1, name: 'Project' }], fetchProjects: vi.fn() }),
}));
vi.mock('../api', () => ({
  createConversation: vi.fn(), deleteConversation: vi.fn(),
  getConversation: vi.fn(), listConversations: vi.fn(), streamAssistant: vi.fn(),
}));

const detail = (status: string): ChatDetail => ({
  conversation: { id: 'chat', projectId: 1, title: 'Chat', mode: 'local', createdAt: '', updatedAt: '' },
  messages: [],
  latestRun: {
    id: 'run', status, provider: null, model: null, stepCount: 0,
    fallbackUsed: false, proposedAction: null, result: null,
  },
});

describe('assistant stream recovery', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.useFakeTimers();
    vi.resetAllMocks();
    vi.mocked(listConversations).mockResolvedValue([detail('running').conversation]);
  });
  afterEach(() => { vi.useRealTimers(); });

  it('refreshes a restored active run and unlocks the chat after interruption', async () => {
    vi.mocked(getConversation).mockResolvedValueOnce(detail('running')).mockResolvedValue(detail('interrupted'));
    const store = useAssistantStore();
    store.isOpen = true;
    await store.selectProject(1);
    await nextTick();
    expect(store.isBusy).toBe(true);
    await vi.advanceTimersByTimeAsync(1500);
    expect(store.latestRun?.status).toBe('interrupted');
    expect(store.isBusy).toBe(false);
    await vi.advanceTimersByTimeAsync(5000);
    expect(getConversation).toHaveBeenCalledTimes(2);
    store.$dispose();
  });

  it('reloads server state after a failed stream instead of retaining running locally', async () => {
    vi.mocked(getConversation).mockResolvedValueOnce(detail('completed')).mockResolvedValue(detail('interrupted'));
    vi.mocked(streamAssistant).mockImplementation(async (_project, _chat, _route, _body, onEvent) => {
      onEvent({ type: 'run', data: { run_id: 'run', status: 'running' } });
      throw new Error('Connection closed');
    });
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'Question';
    await store.send();
    expect(store.isStreaming).toBe(false);
    expect(store.isBusy).toBe(false);
    expect(store.draft).toBe('Question');
    expect(store.error).toBe('Connection closed');
    store.$dispose();
  });
});
