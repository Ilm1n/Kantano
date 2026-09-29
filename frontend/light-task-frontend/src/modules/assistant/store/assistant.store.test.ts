import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { nextTick } from 'vue';
import { deleteConversation, getConversation, listConversations, streamAssistant } from '../api';
import type { AssistantRun, ChatDetail, StreamEvent } from '../api';
import { useAssistantStore } from './assistant.store';

vi.mock('@/modules/projects/store/projects.store', () => ({
  useProjectsStore: () => ({ projects: [{ id: 1, name: 'Project' }, { id: 2, name: 'Other project' }], fetchProjects: vi.fn() }),
}));
vi.mock('../api', () => ({
  createConversation: vi.fn(), deleteConversation: vi.fn(),
  getConversation: vi.fn(), listConversations: vi.fn(), streamAssistant: vi.fn(),
}));

const detail = (status: AssistantRun['status']): ChatDetail => ({
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

  it('ignores a chat response arriving after switching projects from the board', async () => {
    let resolveOld!: (value: ChatDetail) => void;
    vi.mocked(getConversation).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const next = detail('completed');
    next.conversation = { ...next.conversation, id: 'other-chat', projectId: 2 };
    vi.mocked(listConversations).mockResolvedValue([next.conversation]);
    vi.mocked(getConversation).mockResolvedValue(next);
    const store = useAssistantStore();
    store.projectId = 1;
    const oldSelection = store.selectConversation('old-chat');
    await store.openFromBoard(2);
    resolveOld(detail('pending'));
    await oldSelection;
    expect(store.projectId).toBe(2);
    expect(store.conversationId).toBe('other-chat');
    expect(store.latestRun?.status).toBe('completed');
    expect(store.isLoading).toBe(false);
    store.$dispose();
  });

  it('aborts on logout and ignores late stream events and completion', async () => {
    let finish!: () => void;
    let eventHandler!: (event: StreamEvent) => void;
    let signal!: AbortSignal;
    vi.mocked(getConversation).mockResolvedValue(detail('completed'));
    vi.mocked(streamAssistant).mockImplementation(async (_p, _c, _r, _b, onEvent, abortSignal) => {
      eventHandler = onEvent;
      signal = abortSignal!;
      await new Promise<void>((resolve) => { finish = resolve; });
    });
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'Old account question';
    const sending = store.send();
    const reads = vi.mocked(getConversation).mock.calls.length;
    store.reset();
    eventHandler({ type: 'delta', data: { text: 'Old account answer' } });
    finish();
    await sending;
    expect(signal.aborted).toBe(true);
    expect(store.isStreaming).toBe(false);
    expect(store.projectId).toBeNull();
    expect(store.messages).toEqual([]);
    expect(store.streamedText).toBe('');
    expect(store.draft).toBe('');
    expect(getConversation).toHaveBeenCalledTimes(reads);
    store.$dispose();
  });

  it('keeps the stream alive when the panel closes and blocks project switches', async () => {
    let finish!: () => void;
    let signal!: AbortSignal;
    vi.mocked(getConversation).mockResolvedValue(detail('completed'));
    vi.mocked(streamAssistant).mockImplementation(async (_p, _c, _r, _b, _event, abortSignal) => {
      signal = abortSignal!;
      await new Promise<void>((resolve) => { finish = resolve; });
    });
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'Question';
    const sending = store.send();
    store.isOpen = false;
    await store.openFromBoard(2);
    expect(store.projectId).toBe(1);
    expect(signal.aborted).toBe(false);
    finish();
    await sending;
    expect(store.isStreaming).toBe(false);
    store.$dispose();
  });

  it('allows switching away from pending and preserves separate drafts', async () => {
    vi.mocked(getConversation).mockImplementation(async (projectId, chatId) => {
      const next = detail('pending');
      next.conversation = { ...next.conversation, id: chatId, projectId };
      return next;
    });
    vi.mocked(listConversations).mockImplementation(async (projectId) => [{
      ...detail('pending').conversation, id: `chat-${projectId}`, projectId,
    }]);
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'First draft';
    await store.selectProject(2);
    expect(store.draft).toBe('');
    store.draft = 'Second draft';
    await store.selectProject(1);
    expect(store.draft).toBe('First draft');
    expect(store.latestRun?.status).toBe('pending');
    store.$dispose();
  });

  it('blocks sending until chat deletion finishes', async () => {
    let finish!: () => void;
    vi.mocked(getConversation).mockResolvedValue(detail('interrupted'));
    vi.mocked(deleteConversation).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'Next question';
    const deleting = store.removeChat('chat');
    expect(store.isLoading).toBe(true);
    await store.send();
    expect(streamAssistant).not.toHaveBeenCalled();
    finish();
    await deleting;
    expect(store.isLoading).toBe(false);
    expect(store.conversationId).toBeNull();
    expect(store.messages).toEqual([]);
    expect(store.draft).toBe('');
    store.$dispose();
  });

  it('handles a failed history refresh without an unhandled rejection', async () => {
    vi.mocked(getConversation).mockResolvedValueOnce(detail('completed')).mockRejectedValue(new Error('Unavailable'));
    vi.mocked(streamAssistant).mockResolvedValue();
    const store = useAssistantStore();
    await store.selectProject(1);
    store.draft = 'Question';
    await store.send();
    expect(store.isStreaming).toBe(false);
    expect(store.error).toBe('Unavailable');
    store.$dispose();
  });
});
