import { computed, ref, watch } from 'vue';
import { defineStore } from 'pinia';
import { useWindowSize } from '@vueuse/core';
import { getErrorMessage } from '@/utils/error';
import { useProjectsStore } from '@/modules/projects/store/projects.store';
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  stopRun,
  streamAssistant,
  type AssistantMessage,
  type AssistantRun,
  type Conversation,
  type StreamEvent,
} from '../api';

export const DEFAULT_PANEL_WIDTH = 420;
export const MIN_PANEL_WIDTH = 360;
const MAX_PANEL_WIDTH = 700;

export const useAssistantStore = defineStore('assistant', () => {
  const projectsStore = useProjectsStore();
  const { width: windowWidth } = useWindowSize();
  const preferredPanelWidth = ref(DEFAULT_PANEL_WIDTH);
  const isPanelResizable = computed(() => windowWidth.value >= 1280);
  const maxPanelWidth = computed(() => Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, Math.floor(windowWidth.value / 2))));
  const panelWidth = computed(() => Math.min(preferredPanelWidth.value, maxPanelWidth.value));
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
  const isStopping = ref(false);
  const isLoading = ref(false);
  const error = ref('');
  let contextVersion = 0;
  let streamController: AbortController | null = null;

  const project = computed(() => projectsStore.projects.find((item) => item.id === projectId.value));
  const conversation = computed(() => conversations.value.find((item) => item.id === conversationId.value));
  const draftKey = computed(() => conversationId.value ?? `new:${projectId.value ?? 'none'}`);
  const draft = computed({
    get: () => drafts.value[draftKey.value] ?? '',
    set: (value: string) => { drafts.value[draftKey.value] = value; },
  });
  const isPending = computed(() => latestRun.value?.status === 'pending');
  const isBusy = computed(() => ['running', 'executing'].includes(latestRun.value?.status ?? ''));
  const canStop = computed(() => isBusy.value && !!conversationId.value);

  watch([latestRun, isBusy], () => {
    isStopping.value = isBusy.value && !!latestRun.value?.stopRequested;
  }, { deep: true });

  watch([isOpen, projectId, conversationId, isBusy, isStreaming], (_, __, onCleanup) => {
    if (!isOpen.value || !isBusy.value || isStreaming.value
      || projectId.value === null || !conversationId.value) return;
    const currentProjectId = projectId.value;
    const currentChatId = conversationId.value;
    const version = contextVersion;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    onCleanup(() => { cancelled = true; clearTimeout(timer); });
    async function refreshRun() {
      try {
        const detail = await getConversation(currentProjectId, currentChatId);
        if (cancelled || version !== contextVersion) return;
        messages.value = detail.messages;
        latestRun.value = detail.latestRun;
      } catch (cause) {
        if (!cancelled && version === contextVersion) error.value = getErrorMessage(cause);
      }
      if (!cancelled && isBusy.value) timer = setTimeout(refreshRun, 1500);
    }
    timer = setTimeout(refreshRun, 1500);
  });

  function setPanelWidth(width: number) {
    preferredPanelWidth.value = Math.round(Math.min(maxPanelWidth.value, Math.max(MIN_PANEL_WIDTH, width)));
  }

  function resetPanelWidth() {
    preferredPanelWidth.value = DEFAULT_PANEL_WIDTH;
  }

  async function ensureProjects() {
    if (!projectsStore.projects.length) await projectsStore.fetchProjects();
  }

  async function openFromMenu() {
    isOpen.value = true;
    const version = contextVersion;
    try {
      await ensureProjects();
      if (version !== contextVersion) return;
      if (projectId.value === null && projectsStore.projects.length) {
        await selectProject(projectsStore.projects[0]!.id);
      }
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
    }
  }

  async function openFromBoard(boardProjectId: number) {
    isOpen.value = true;
    if (isStreaming.value) return;
    const version = contextVersion;
    try {
      await ensureProjects();
      if (version !== contextVersion) return;
      if (projectId.value !== boardProjectId) await selectProject(boardProjectId);
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
    }
  }

  async function selectProject(nextProjectId: number) {
    if (isStreaming.value || projectId.value === nextProjectId) return;
    const version = ++contextVersion;
    projectId.value = nextProjectId;
    conversationId.value = null;
    messages.value = [];
    latestRun.value = null;
    error.value = '';
    isLoading.value = true;
    try {
      const chats = await listConversations(nextProjectId);
      if (version !== contextVersion) return;
      conversations.value = chats;
      const previousChat = chatByProject.value[nextProjectId];
      const nextChat = conversations.value.find((item) => item.id === previousChat)
        ?? conversations.value[0];
      if (nextChat) await loadConversation(nextProjectId, nextChat.id, version);
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
      conversations.value = [];
    } finally {
      if (version === contextVersion) isLoading.value = false;
    }
  }

  async function selectConversation(nextChatId: string) {
    if (isStreaming.value || projectId.value === null) return;
    await loadConversation(projectId.value, nextChatId, ++contextVersion);
  }

  async function loadConversation(currentProjectId: number, nextChatId: string, version: number) {
    isLoading.value = true;
    try {
      const detail = await getConversation(currentProjectId, nextChatId);
      if (version !== contextVersion) return;
      conversationId.value = nextChatId;
      chatByProject.value[currentProjectId] = nextChatId;
      messages.value = detail.messages;
      latestRun.value = detail.latestRun;
      streamedText.value = '';
      error.value = '';
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
    } finally {
      if (version === contextVersion) isLoading.value = false;
    }
  }

  async function createChat(): Promise<string | null> {
    if (projectId.value === null || isStreaming.value || isLoading.value) return null;
    const currentProjectId = projectId.value;
    const version = ++contextVersion;
    isLoading.value = true;
    try {
      const chat = await createConversation(currentProjectId);
      if (version !== contextVersion) return null;
      conversations.value = [chat, ...conversations.value];
      await loadConversation(currentProjectId, chat.id, version);
      return conversationId.value === chat.id ? chat.id : null;
    } catch (cause) {
      if (version !== contextVersion) return null;
      error.value = getErrorMessage(cause);
      return null;
    } finally {
      if (version === contextVersion) isLoading.value = false;
    }
  }

  async function removeChat(chatId: string) {
    if (projectId.value === null || isStreaming.value || isLoading.value) return;
    const currentProjectId = projectId.value;
    const version = ++contextVersion;
    isLoading.value = true;
    try {
      await deleteConversation(currentProjectId, chatId);
      if (version !== contextVersion) return;
      delete drafts.value[chatId];
      if (chatByProject.value[currentProjectId] === chatId) delete chatByProject.value[currentProjectId];
      conversations.value = conversations.value.filter((item) => item.id !== chatId);
      if (conversationId.value === chatId) {
        conversationId.value = null;
        messages.value = [];
        latestRun.value = null;
        const next = conversations.value[0];
        if (next) await loadConversation(currentProjectId, next.id, version);
      }
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
    } finally {
      if (version === contextVersion) isLoading.value = false;
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
        if (event.data.provider !== undefined) latestRun.value.provider = event.data.provider;
        if (event.data.model !== undefined) latestRun.value.model = event.data.model;
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
    const currentProjectId = projectId.value!;
    const version = contextVersion;
    const controller = new AbortController();
    streamController = controller;
    drafts.value[originalDraftKey] = '';
    draft.value = '';
    messages.value.push({
      id: `local-${Date.now()}`, role: 'user', content, references: [],
      createdAt: new Date().toISOString(),
    });
    isStreaming.value = true;
    latestRun.value = null;
    streamedText.value = '';
    error.value = '';
    try {
      await streamAssistant(currentProjectId, chatId, '/runs', { content }, (event) => {
        if (version === contextVersion) handleEvent(event);
      }, controller.signal);
      if (version === contextVersion) await selectConversationAfterStream(currentProjectId, chatId, version);
    } catch (cause) {
      if (version !== contextVersion) return;
      draft.value = content;
      error.value = getErrorMessage(cause);
      await selectConversationAfterStream(currentProjectId, chatId, version);
    } finally {
      if (version === contextVersion) {
        isStreaming.value = false;
        streamController = null;
      }
    }
  }

  async function stop() {
    if (!canStop.value || isStopping.value || projectId.value === null || !conversationId.value || !latestRun.value) return;
    const currentProjectId = projectId.value;
    const currentChatId = conversationId.value;
    const runId = latestRun.value.id;
    const version = contextVersion;
    isStopping.value = true;
    try {
      await stopRun(currentProjectId, currentChatId, runId);
      if (version !== contextVersion) return;
      if (latestRun.value?.id === runId && isBusy.value) latestRun.value.stopRequested = true;
      // Keep SSE open until the server finishes an already started mutation.
      if (!isStreaming.value || isPending.value) {
        await selectConversationAfterStream(currentProjectId, currentChatId, version);
      }
    } catch (cause) {
      if (version !== contextVersion) return;
      isStopping.value = false;
      error.value = getErrorMessage(cause);
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
    const version = contextVersion;
    const controller = new AbortController();
    streamController = controller;
    isStreaming.value = true;
    streamedText.value = '';
    error.value = '';
    try {
      await streamAssistant(
        currentProjectId, currentChatId, `/runs/${runId}/decision`,
        { approve, action_id: actionId }, (event) => {
          if (version === contextVersion) handleEvent(event);
        }, controller.signal,
      );
      if (version === contextVersion) await selectConversationAfterStream(currentProjectId, currentChatId, version);
    } catch (cause) {
      if (version !== contextVersion) return;
      error.value = getErrorMessage(cause);
      await selectConversationAfterStream(currentProjectId, currentChatId, version);
    } finally {
      if (version === contextVersion) {
        isStreaming.value = false;
        streamController = null;
      }
    }
  }

  async function selectConversationAfterStream(currentProjectId: number, currentChatId: string, version: number) {
    try {
      const detail = await getConversation(currentProjectId, currentChatId);
      if (version !== contextVersion) return;
      messages.value = detail.messages;
      latestRun.value = detail.latestRun;
      streamedText.value = '';
      const chats = await listConversations(currentProjectId);
      if (version === contextVersion) conversations.value = chats;
    } catch (cause) {
      if (version === contextVersion) error.value = getErrorMessage(cause);
    }
  }

  function reset() {
    contextVersion++;
    streamController?.abort();
    streamController = null;
    isStreaming.value = false;
    isStopping.value = false;
    isLoading.value = false;
    isOpen.value = false;
    resetPanelWidth();
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
    panelWidth, maxPanelWidth, isPanelResizable, setPanelWidth, resetPanelWidth,
    isOpen, projectId, conversationId, projects: computed(() => projectsStore.projects),
    project, conversation, conversations, messages, latestRun, streamedText,
    isStreaming, isStopping, canStop, isLoading, isPending, isBusy, error, draft,
    openFromMenu, openFromBoard, selectProject, selectConversation,
    createChat, removeChat, send, stop, decide, reset,
  };
});
