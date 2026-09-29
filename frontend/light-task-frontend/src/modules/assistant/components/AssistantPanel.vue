<script setup lang="ts">
import { computed } from 'vue';
import { useConfirm } from 'primevue/useconfirm';
import MarkdownIt from 'markdown-it';
import { useAssistantStore } from '../store/assistant.store';

const store = useAssistantStore();
const confirm = useConfirm();
const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true });
markdown.disable('image');
const renderMarkdown = (content: string) => markdown.render(content);
const actionNames: Record<string, string> = {
  CreateTask: 'Создать задачу',
  UpdateTask: 'Изменить задачу',
  MoveTask: 'Переместить задачу',
  CreateColumn: 'Создать колонку',
  RenameColumn: 'Переименовать колонку',
  MoveColumn: 'Переместить колонку',
  CreateTag: 'Создать тег',
  UpdateTag: 'Изменить тег',
  AddTagToTask: 'Добавить тег задаче',
  RemoveTagFromTask: 'Убрать тег с задачи',
};
const fieldNames: Record<string, string> = {
  title: 'Название', description: 'Описание', task_id: 'Задача #',
  column_id: 'Колонка #', new_column_id: 'Новая колонка #',
  priority: 'Приоритет', assignee_id: 'Исполнитель #',
  deadline_at: 'Срок', tag_ids: 'Метки',
  name: 'Название', new_name: 'Новое название',
  before_column_id: 'Перед колонкой #',
  tag_id: 'Тег #', color: 'Цвет',
};
const action = computed(() => store.latestRun?.proposedAction);
const priorityLabels: Record<string, string> = {
  LOW: 'Низкий', MEDIUM: 'Средний', HIGH: 'Высокий', CRITICAL: 'Критический',
};
const actionFields = computed(() => Object.entries(action.value?.args ?? {})
  .filter(([key]) => key !== 'tool_call_id')
  .map(([key, value]) => ({
    label: fieldNames[key] ?? key,
    value: key === 'priority' ? priorityLabels[String(value)] ?? String(value ?? '—')
      : Array.isArray(value) ? value.join(', ') : String(value ?? '—'),
  })));
const canSend = computed(() => Boolean(store.draft.trim()) && !store.isLoading && !store.isStreaming && !store.isPending && !store.isBusy);

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    if (canSend.value) void store.send();
  }
}

function confirmDeleteChat() {
  if (!store.conversationId) return;
  const chatId = store.conversationId;
  confirm.require({
    message: 'Удалить этот чат и его историю?',
    header: 'Удаление чата',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Удалить',
    rejectLabel: 'Отмена',
    accept: () => { void store.removeChat(chatId); },
  });
}
</script>

<template>
  <aside
    aria-label="Помощник Kantano"
    class="assistant-panel fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface sm:w-[420px] xl:static xl:z-auto xl:shrink-0 xl:shadow-none"
  >
    <header class="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-4 dark:border-dark-border">
      <div class="flex min-w-0 items-center gap-3">
        <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-500/10">
          <i class="pi pi-sparkles" aria-hidden="true"></i>
        </span>
        <div class="min-w-0">
          <h2 class="truncate text-sm font-bold text-slate-800 dark:text-white">Помощник</h2>
          <p class="text-xs text-slate-500">Вопросы и действия по проекту</p>
        </div>
      </div>
      <button type="button" aria-label="Закрыть помощника" class="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" @click="store.isOpen = false">
        <i class="pi pi-times" aria-hidden="true"></i>
      </button>
    </header>

    <div class="border-b border-slate-200 px-4 py-3 dark:border-dark-border">
      <label for="assistant-project" class="mb-1 block text-[11px] font-bold uppercase tracking-wide text-slate-500">Проект</label>
      <select
        id="assistant-project"
        :value="store.projectId ?? ''"
        :disabled="store.isStreaming || store.isLoading"
        class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700 outline-none focus:border-primary-500 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        @change="store.selectProject(Number(($event.target as HTMLSelectElement).value))"
      >
        <option v-if="!store.projects.length" value="">Нет проектов</option>
        <option v-for="project in store.projects" :key="project.id" :value="project.id">{{ project.name }}</option>
      </select>
    </div>

    <div v-if="store.projectId !== null" class="border-b border-slate-200 px-4 py-3 dark:border-dark-border">
      <div class="mb-2 flex items-center justify-between">
        <span class="text-xs font-bold text-slate-600 dark:text-slate-300">Чаты проекта</span>
        <div class="flex items-center gap-1">
          <button v-if="store.conversationId" type="button" title="Удалить текущий чат" aria-label="Удалить текущий чат" :disabled="store.isStreaming || store.isLoading" class="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50" @click="confirmDeleteChat">
            <i class="pi pi-trash" aria-hidden="true"></i>
          </button>
          <button type="button" :disabled="store.isStreaming || store.isLoading" class="rounded-lg px-2 py-1 text-xs font-bold text-primary-600 hover:bg-primary-50 disabled:opacity-50" @click="store.createChat()">
            <i class="pi pi-plus mr-1" aria-hidden="true"></i>Новый чат
          </button>
        </div>
      </div>
      <div class="flex gap-2 overflow-x-auto pb-1">
        <button
          v-for="chat in store.conversations"
          :key="chat.id"
          type="button"
          :disabled="store.isStreaming || store.isLoading"
          :aria-current="store.conversationId === chat.id ? 'true' : undefined"
          class="max-w-40 shrink-0 truncate rounded-full border px-3 py-1.5 text-xs font-medium disabled:opacity-60"
          :class="store.conversationId === chat.id ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-500/10 dark:text-primary-300' : 'border-slate-200 text-slate-600 hover:border-primary-300 dark:border-slate-700 dark:text-slate-300'"
          @click="store.selectConversation(chat.id)"
        >{{ chat.title }}</button>
      </div>
    </div>

    <div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5" aria-live="polite">
      <div v-if="!store.projectId" class="mx-auto max-w-xs pt-12 text-center text-sm text-slate-500">
        Выберите проект, чтобы задать вопрос помощнику.
      </div>
      <div v-else-if="!store.messages.length && !store.isStreaming" class="mx-auto max-w-xs pt-12 text-center">
        <i class="pi pi-sparkles text-3xl text-primary-400" aria-hidden="true"></i>
        <p class="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Что происходит в проекте?</p>
        <p class="mt-2 text-xs leading-5 text-slate-500">Спросите о задачах, участниках или попросите создать задачу. Любое изменение потребуется подтвердить.</p>
      </div>

      <div v-for="message in store.messages" :key="message.id" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
        <div class="max-w-[90%] rounded-2xl px-3.5 py-2.5 text-sm leading-6" :class="message.role === 'user' ? 'rounded-br-sm bg-primary-600 text-white' : 'rounded-bl-sm bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100'">
          <div v-if="message.role === 'assistant'" class="assistant-markdown break-words" v-html="renderMarkdown(message.content)"></div>
          <div v-else class="whitespace-pre-wrap break-words">{{ message.content }}</div>
          <div v-if="message.references?.length && store.projectId" class="mt-2 flex flex-wrap gap-1.5 border-t border-slate-200 pt-2 dark:border-slate-700">
            <router-link
              v-for="reference in message.references.filter((item) => item.type === 'task')"
              :key="reference.id"
              :to="{ name: 'project-board', params: { projectId: store.projectId }, query: { taskId: reference.id } }"
              class="rounded-md bg-white px-2 py-0.5 text-xs font-semibold text-primary-700 hover:underline dark:bg-slate-700 dark:text-primary-300"
            >#{{ reference.id }} {{ reference.title }}</router-link>
          </div>
        </div>
      </div>
      <div v-if="store.streamedText" class="assistant-markdown max-w-[90%] break-words rounded-2xl rounded-bl-sm bg-slate-100 px-3.5 py-2.5 text-sm leading-6 text-slate-800 dark:bg-slate-800 dark:text-slate-100" v-html="renderMarkdown(store.streamedText)">
      </div>
      <div v-if="store.isStreaming && !store.streamedText" class="flex items-center gap-2 text-xs text-slate-500">
        <i class="pi pi-spin pi-spinner" aria-hidden="true"></i>Помощник работает…
      </div>

      <div v-if="store.isPending && action" class="rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950/30">
        <p class="text-sm font-bold text-amber-900 dark:text-amber-200">Подтвердить действие</p>
        <p class="mt-1 text-sm text-amber-900 dark:text-amber-200">{{ actionNames[action.name] ?? action.name }}</p>
        <dl class="mt-3 space-y-1 text-xs text-amber-950 dark:text-amber-100">
          <div v-for="field in actionFields" :key="field.label" class="flex gap-2">
            <dt class="min-w-24 font-semibold">{{ field.label }}</dt><dd class="break-all">{{ field.value }}</dd>
          </div>
        </dl>
        <div class="mt-4 flex gap-2">
          <button type="button" :disabled="store.isStreaming" class="rounded-lg bg-primary-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50" @click="store.decide(true)">Подтвердить</button>
          <button type="button" :disabled="store.isStreaming" class="rounded-lg border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-900 disabled:opacity-50 dark:text-amber-200" @click="store.decide(false)">Отклонить</button>
        </div>
      </div>
      <p v-if="store.error" role="alert" class="rounded-lg bg-red-50 p-3 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">{{ store.error }}</p>
    </div>

    <footer class="shrink-0 border-t border-slate-200 p-4 dark:border-dark-border">
      <p v-if="store.isPending" class="mb-2 text-xs text-amber-700 dark:text-amber-300">Сначала подтвердите или отклоните действие.</p>
      <p v-if="store.isBusy && !store.isStreaming" class="mb-2 text-xs text-slate-500">Проверяем состояние запроса…</p>
      <p v-if="store.latestRun?.status === 'interrupted'" class="mb-2 text-xs text-slate-500">Запрос прерван. Можно отправить новое сообщение.</p>
      <p v-if="store.latestRun?.status === 'unknown'" class="mb-2 text-xs text-amber-700 dark:text-amber-300">Исход изменения неизвестен. Проверьте доску перед новой попыткой.</p>
      <div class="flex items-end gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2 focus-within:border-primary-500 dark:border-slate-700 dark:bg-slate-900">
        <textarea
          v-model="store.draft"
          aria-label="Сообщение помощнику"
          rows="2"
          :disabled="!store.projectId || store.isLoading || store.isPending || store.isBusy || store.isStreaming"
          placeholder="Спросите о проекте или задаче…"
          class="max-h-32 min-h-12 flex-1 resize-none bg-transparent px-1 py-1 text-sm text-slate-800 outline-none placeholder:text-slate-400 disabled:opacity-60 dark:text-white"
          @keydown="onComposerKeydown"
        ></textarea>
        <button type="button" aria-label="Отправить" :disabled="!canSend" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-white disabled:bg-slate-300 dark:disabled:bg-slate-700" @click="store.send()">
          <i class="pi pi-arrow-up" aria-hidden="true"></i>
        </button>
      </div>
      <p class="mt-2 text-[11px] text-slate-400">Enter — отправить · Shift+Enter — новая строка</p>
    </footer>
  </aside>
</template>

<style scoped>
.assistant-markdown :deep(p + p),
.assistant-markdown :deep(p + ul),
.assistant-markdown :deep(p + ol) { margin-top: 0.5rem; }
.assistant-markdown :deep(ul) { list-style: disc; padding-left: 1.25rem; }
.assistant-markdown :deep(ol) { list-style: decimal; padding-left: 1.25rem; }
.assistant-markdown :deep(pre) { overflow-x: auto; margin-top: 0.5rem; padding: 0.5rem; border-radius: 0.5rem; background: #0f172a; color: white; }
.assistant-markdown :deep(code) { font-size: 0.8em; }
.assistant-markdown :deep(a) { text-decoration: underline; }
</style>
