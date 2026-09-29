import { computed, ref, watch } from 'vue';
import { defineStore } from 'pinia';
import { useProjectsStore } from '@/modules/projects/store/projects.store';
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  streamAssistant,
  type AssistantMessage,
  type AssistantRun,
  type Conversation,
  type StreamEvent,
} from '../api';

export const useAssistantStore = defineStore('assistant', () => {
  const projectsStore = useProjectsStore();
  const isOpen = ref(false);
  const projectId = ref<number | null>(null);
  const conversationId = ref<string | null>(null);
  const chatByProject = ref<Record<number, string>>({});
  const drafts = ref<Record<string, string>>({});
  const conversations = ref<Conversation[]>([]);
  const messages = ref<AssistantMessage[]>([]);
  const latestRun = ref<AssistantRun | null>(null);
  const streamedText = ref('');
  const isStreaming = ref(false);
  const isLoading = ref(false);
  const error = ref('');

  const project = computed(() => projectsStore.projects.find((item) => item.id === projectId.value));
  const conversation = computed(() => conversations.value.find((item) => item.id === conversationId.value));
  const draftKey = computed(() => conversationId.value ?? `new:${projectId.value ?? 'none'}`);
  const draft = computed({
    get: () => drafts.value[draftKey.value] ?? '',
    set: (value: string) => { drafts.value[draftKey.value] = value; },
  });
  const isPending = computed(() => latestRun.value?.status === 'pending');
  const isBusy = computed(() => ['running', 'executing'].includes(latestRun.value?.status ?? ''));

  watch([isOpen, projectId, conversationId, isBusy, isStreaming], (_, __, onCleanup) => {
    if (!isOpen.value || !isBusy.value || isStreaming.value
      || projectId.value === null || !conversationId.value) return;
    const currentProjectId = projectId.value;
    const currentChatId = conversationId.value;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    onCleanup(() => { cancelled = true; clearTimeout(timer); });
    async function refreshRun() {
      try {
        const detail = await getConversation(currentProjectId, currentChatId);
        if (cancelled) return;
        messages.value = detail.messages;
        latestRun.value = detail.latestRun;
      } catch (cause) {
        if (!cancelled) error.value = cause instanceof Error ? cause.message : 'Не удалось обновить чат';
      }
      if (!cancelled && isBusy.value) timer = setTimeout(refreshRun, 1500);
    }
    timer = setTimeout(refreshRun, 1500);
  });

  async function ensureProjects() {
    if (!projectsStore.projects.length) await projectsStore.fetchProjects();
  }

  async function openFromMenu() {
    isOpen.value = true;
    try {
      await ensureProjects();
      if (projectId.value === null && projectsStore.projects.length) {
        await selectProject(projectsStore.projects[0]!.id);
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить проекты';
    }
  }

  async function openFromBoard(boardProjectId: number) {
    isOpen.value = true;
    if (isStreaming.value) return;
    try {
      await ensureProjects();
      if (projectId.value !== boardProjectId) await selectProject(boardProjectId);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить проекты';
    }
  }

  async function selectProject(nextProjectId: number) {
    if (isStreaming.value || projectId.value === nextProjectId) return;
    projectId.value = nextProjectId;
    conversationId.value = null;
    messages.value = [];
    latestRun.value = null;
    error.value = '';
    isLoading.value = true;
    try {
      conversations.value = await listConversations(nextProjectId);
      const previousChat = chatByProject.value[nextProjectId];
      const nextChat = conversations.value.find((item) => item.id === previousChat)
        ?? conversations.value[0];
      if (nextChat) await selectConversation(nextChat.id);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось загрузить чаты';
      conversations.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function selectConversation(nextChatId: string) {
    if (isStreaming.value || projectId.value === null) return;
    isLoading.value = true;
    try {
      const detail = await getConversation(projectId.value, nextChatId);
      conversationId.value = nextChatId;
      chatByProject.value[projectId.value] = nextChatId;
      messages.value = detail.messages;
      latestRun.value = detail.latestRun;
      streamedText.value = '';
      error.value = '';
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось открыть чат';
    } finally {
      isLoading.value = false;
    }
  }

  async function createChat(): Promise<string | null> {
    if (projectId.value === null || isStreaming.value || isLoading.value) return null;
    isLoading.value = true;
    try {
      const chat = await createConversation(projectId.value);
      conversations.value = [chat, ...conversations.value];
      await selectConversation(chat.id);
      return conversationId.value === chat.id ? chat.id : null;
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось создать чат';
      return null;
    } finally {
      isLoading.value = false;
    }
  }

  async function removeChat(chatId: string) {
    if (projectId.value === null || isStreaming.value) return;
    try {
      await deleteConversation(projectId.value, chatId);
      delete drafts.value[chatId];
      conversations.value = conversations.value.filter((item) => item.id !== chatId);
      if (conversationId.value === chatId) {
        conversationId.value = null;
        messages.value = [];
        latestRun.value = null;
        const next = conversations.value[0];
        if (next) await selectConversation(next.id);
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось удалить чат';
    }
  }

  function handleEvent(event: StreamEvent) {
    if (event.type === 'run') {
      latestRun.value = {
        id: event.data.run_id, status: event.data.status,
        provider: null, model: null, stepCount: 0, fallbackUsed: false,
        proposedAction: null, result: null,
      };
    } else if (event.type === 'delta') {
      streamedText.value += event.data.text;
    } else if (event.type === 'reset') {
      streamedText.value = '';
    } else if (event.type === 'approval_required') {
      if (latestRun.value) {
        latestRun.value.status = 'pending';
        latestRun.value.proposedAction = event.data.action;
        latestRun.value.provider = event.data.provider;
        latestRun.value.model = event.data.model;
      }
    } else if (event.type === 'done') {
      if (latestRun.value) {
        latestRun.value.status = event.data.status;
        latestRun.value.provider = event.data.provider;
        latestRun.value.model = event.data.model;
      }
    } else if (event.type === 'error') {
      error.value = event.data.message;
    }
  }

  async function send() {
    const content = draft.value.trim();
    if (!content || isLoading.value || isStreaming.value || isPending.value || isBusy.value || projectId.value === null) return;
    const originalDraftKey = draftKey.value;
    let chatId = conversationId.value;
    if (!chatId) chatId = await createChat();
    if (!chatId) return;
    drafts.value[originalDraftKey] = '';
    draft.value = '';
    messages.value.push({
      id: `local-${Date.now()}`, role: 'user', content, references: [],
      createdAt: new Date().toISOString(),
    });
    isStreaming.value = true;
    streamedText.value = '';
    error.value = '';
    try {
      await streamAssistant(projectId.value, chatId, '/runs', { content }, handleEvent);
      await selectConversationAfterStream(projectId.value, chatId);
    } catch (cause) {
      draft.value = content;
      error.value = cause instanceof Error ? cause.message : 'Не удалось отправить сообщение';
      await selectConversationAfterStream(projectId.value, chatId);
    } finally {
      isStreaming.value = false;
    }
  }

  async function decide(approve: boolean) {
    if (isStreaming.value || projectId.value === null || !conversationId.value
      || !latestRun.value || latestRun.value.status !== 'pending') return;
    const currentProjectId = projectId.value;
    const currentChatId = conversationId.value;
    const runId = latestRun.value.id;
    const actionId = latestRun.value.proposedAction?.action_id
      ?? latestRun.value.proposedAction?.tool_call_id;
    if (!actionId) return;
    isStreaming.value = true;
    streamedText.value = '';
    error.value = '';
    try {
      await streamAssistant(
        currentProjectId, currentChatId, `/runs/${runId}/decision`,
        { approve, action_id: actionId }, handleEvent,
      );
      await selectConversationAfterStream(currentProjectId, currentChatId);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Не удалось подтвердить действие';
      await selectConversationAfterStream(currentProjectId, currentChatId);
    } finally {
      isStreaming.value = false;
    }
  }

  async function selectConversationAfterStream(currentProjectId: number, currentChatId: string) {
    const detail = await getConversation(currentProjectId, currentChatId);
    messages.value = detail.messages;
    latestRun.value = detail.latestRun;
    streamedText.value = '';
    conversations.value = await listConversations(currentProjectId);
  }

  function reset() {
    isOpen.value = false;
    projectId.value = null;
    conversationId.value = null;
    chatByProject.value = {};
    drafts.value = {};
    conversations.value = [];
    messages.value = [];
    latestRun.value = null;
    streamedText.value = '';
    error.value = '';
  }

  return {
    isOpen, projectId, conversationId, projects: computed(() => projectsStore.projects),
    project, conversation, conversations, messages, latestRun, streamedText,
    isStreaming, isLoading, isPending, isBusy, error, draft,
    openFromMenu, openFromBoard, selectProject, selectConversation,
    createChat, removeChat, send, decide, reset,
  };
});
