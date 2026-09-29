<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useBoardStore } from "../../store/board.store";
import { useBreakpoints, watchDebounced } from "@vueuse/core";
import { useToast } from "primevue/usetoast";
import { getErrorMessage } from "@/utils/error";
import { useConfirm } from "primevue/useconfirm";
import type { TaskPriority, TaskRead, TaskUpdate } from "@/api/client";
import { useAuthStore } from "@/modules/auth/store/auth.store";
import { useRealtimeStore } from "@/modules/realtime/store/realtime.store";
import { useAssistantStore } from "@/modules/assistant/store/assistant.store";

// UI Components
import TaskDetailsPanel from "./TaskDetailsPanel.vue";
import InputText from "primevue/inputtext";
import Textarea from "primevue/textarea";
import Skeleton from "primevue/skeleton";
import Button from "primevue/button";
import TaskSidebar from "./TaskSidebar.vue";

const route = useRoute();
const router = useRouter();
const store = useBoardStore();
const authStore = useAuthStore();
const realtimeStore = useRealtimeStore();
const assistantStore = useAssistantStore();
const isWideScreen = useBreakpoints({ wide: 1536 }).greaterOrEqual("wide");
const besideAssistant = computed(() => assistantStore.isOpen && isWideScreen.value);
const toast = useToast();
const confirm = useConfirm();

const isVisible = ref(false);
const isHydrating = ref(false);
const editingPresenceActive = ref(false);
let viewingHeartbeatTimer: number | null = null;
let editingHeartbeatTimer: number | null = null;

// --- Локальное состояние (Single Source of Truth для формы) ---
const localTitle = ref("");
const localDescription = ref("");
const localAssigneeId = ref<number | null>(null);
const localPriority = ref<TaskPriority | null>(null);
const localDeadlineAt = ref<Date | null>(null);
const localTagIds = ref<number[]>([]);

// Состояния сохранения
const isSaving = ref(false);
const lastSavedAt = ref<Date | null>(null);

// Форматирование времени сохранения
const lastSavedTime = computed(() => {
  if (!lastSavedAt.value) return "";
  return lastSavedAt.value.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
});

const toSortedTagIds = (task: TaskRead | null): number[] =>
  [...(task?.tags?.map((tag) => tag.id) ?? [])].sort((a, b) => a - b);

const parseDeadline = (deadlineAt?: string | null): Date | null => {
  if (!deadlineAt) return null;
  const date = new Date(deadlineAt);
  return Number.isNaN(date.getTime()) ? null : date;
};

const toDeadlinePayload = (deadlineAt: Date | null): string | null => {
  if (!deadlineAt) return null;
  return deadlineAt.toISOString();
};

const isSameDeadline = (first: Date | null, second?: string | null): boolean => {
  const secondDate = parseDeadline(second);
  if (!first && !secondDate) return true;
  if (!first || !secondDate) return false;
  return first.getTime() === secondDate.getTime();
};

const setLocalFromTask = (task: TaskRead) => {
  isHydrating.value = true;
  localTitle.value = task.title;
  localDescription.value = task.description || "";
  localAssigneeId.value = task.assigneeId || null;
  localPriority.value = task.priority || null;
  localDeadlineAt.value = parseDeadline(task.deadlineAt);
  localTagIds.value = task.tags?.map((tag) => tag.id) || [];
  isHydrating.value = false;
};

const hasUnsavedLocalChanges = (task: TaskRead): boolean => {
  if (localTitle.value !== task.title) return true;
  if (localDescription.value !== (task.description || "")) return true;
  if ((localAssigneeId.value || null) !== (task.assigneeId || null)) return true;
  if ((localPriority.value || null) !== (task.priority || null)) return true;
  if (!isSameDeadline(localDeadlineAt.value, task.deadlineAt)) return true;

  const localTags = [...localTagIds.value].sort((a, b) => a - b);
  const taskTags = toSortedTagIds(task);
  if (localTags.length !== taskTags.length) return true;
  return localTags.some((id, index) => id !== taskTags[index]);
};

const editingUsersCount = computed(() => {
  if (!store.selectedTask) return 0;
  const currentUserId = authStore.user?.id;
  return store
    .getEditingUsers(store.selectedTask.id)
    .filter((id) => id !== currentUserId).length;
});

// Форматирование дат создания/обновления
const formatDate = (dateStr?: string) => {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// --- Инициализация при открытии ---
watch(
  [() => route.query.taskId, () => store.project?.id, () => store.isLoading],
  async ([newId, boardProjectId, isBoardLoading], [oldId]) => {
    if (oldId && oldId !== newId) {
      const oldTaskId = Number(oldId);
      if (!Number.isNaN(oldTaskId)) {
        stopPresence(oldTaskId);
      }
    }

    if (newId) {
      // A link from another project must wait until fetchBoard finishes resetting task state.
      if (isBoardLoading || boardProjectId !== Number(route.params.projectId)) return;
      const id = Number(newId);
      if (!isNaN(id)) {
        isVisible.value = true;
        startViewingPresence(id);

        const detailsPromise = store.fetchTaskDetails(id);
        if (store.selectedTask) {
          setLocalFromTask(store.selectedTask);
          lastSavedAt.value = null;
        }

        await detailsPromise;
        if (Number(route.query.taskId) === id && store.selectedTask?.id === id) {
          setLocalFromTask(store.selectedTask);
          lastSavedAt.value = null;
        }
      }
    } else {
      isVisible.value = false;
    }
  },
  { immediate: true },
);

watch(
  () => store.selectedTask,
  (task, previousTask) => {
    if (!task || !previousTask) return;
    if (!isVisible.value) return;
    if (task.id !== previousTask.id) return;
    if (task.updatedAt === previousTask.updatedAt) return;
    if (isSaving.value || isHydrating.value) return;

    if (hasUnsavedLocalChanges(previousTask)) {
      toast.add({
        severity: "warn",
        summary: "Есть новые изменения",
        detail: "Задача обновилась у другого участника. Сохрани или закрой текущие правки, чтобы применить их.",
        life: 3500,
      });
      return;
    }

    setLocalFromTask(task);
    toast.add({
      severity: "info",
      summary: "Обновлено",
      detail: "Изменения в задаче применены в реальном времени",
      life: 2000,
    });
  },
);

const onClose = () => {
  if (store.selectedTask) {
    stopPresence(store.selectedTask.id);
  }
  isVisible.value = false;
  const query = { ...route.query };
  delete query.taskId;
  router.push({ query });
};

watch(
  [localTitle, localDescription, localAssigneeId, localPriority, localDeadlineAt, localTagIds],
  () => {
    if (!store.selectedTask || isHydrating.value) return;
    if (!editingPresenceActive.value) {
      startEditingPresence(store.selectedTask.id);
    }
  },
  { deep: true },
);

// --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ СОХРАНЕНИЯ ---
const performSave = async (payload: TaskUpdate) => {
  if (!store.selectedTask) return;

  isSaving.value = true;
  try {
    await store.updateTask(store.selectedTask.id, payload);
    lastSavedAt.value = new Date();
  } catch (e) {
    toast.add({
      severity: "error",
      summary: "Ошибка",
      detail: getErrorMessage(e),
      life: 3000,
    });
  } finally {
    isSaving.value = false;
  }
};

// 1. Auto-save Title (Blur)
const saveTitle = () => {
  if (!store.selectedTask) return;
  if (!localTitle.value.trim()) {
    localTitle.value = store.selectedTask.title;
    return;
  }
  if (localTitle.value.trim() === store.selectedTask.title) return;
  performSave({ title: localTitle.value });
};

// 2. Auto-save Description (Debounce)
watchDebounced(
  localDescription,
  async (newVal) => {
    if (!store.selectedTask) return;
    if (newVal === (store.selectedTask.description || "")) return;
    await performSave({ description: newVal });
  },
  { debounce: 1000 },
);

// 3. Auto-save Sidebar Fields (Watchers)
// Важно проверять на равенство, чтобы не триггерить сохранение при инициализации
watch(localAssigneeId, (newVal) => {
  if (store.selectedTask && newVal !== store.selectedTask.assigneeId) {
    performSave({ assigneeId: newVal });
  }
});

watch(localPriority, (newVal) => {
  if (store.selectedTask && newVal !== store.selectedTask.priority) {
    performSave({ priority: newVal });
  }
});

watch(localDeadlineAt, (newVal) => {
  if (!store.selectedTask || isHydrating.value) return;
  if (isSameDeadline(newVal, store.selectedTask.deadlineAt)) return;
  performSave({ deadlineAt: toDeadlinePayload(newVal) });
});

watch(localTagIds, (newVal) => {
  // Сравниваем массивы (грубо, но для ID пойдет)
  const currentIds = store.selectedTask?.tags?.map((t) => t.id) || [];
  const isSame =
    newVal.length === currentIds.length &&
    newVal.every((id) => currentIds.includes(id));

  if (store.selectedTask && !isSame) {
    performSave({ tagIds: newVal });
  }
});

// 4. Ручное сохранение (Кнопка внизу - атомарное)
const saveAllAndClose = async () => {
  if (!localTitle.value.trim()) {
    toast.add({
      severity: "error",
      summary: "Ошибка",
      detail: "Название задачи не может быть пустым",
      life: 3000,
    });
    return;
  }

  await performSave({
    title: localTitle.value,
    description: localDescription.value,
    assigneeId: localAssigneeId.value,
    priority: localPriority.value,
    deadlineAt: toDeadlinePayload(localDeadlineAt.value),
    tagIds: localTagIds.value,
  });
  onClose();
};

const deleteTask = () => {
  const taskId = store.selectedTask?.id;
  if (!taskId) return;

  confirm.require({
    message:
      "Вы уверены, что хотите удалить эту задачу? Это действие необратимо.",
    header: "Удаление задачи",
    icon: "pi pi-exclamation-triangle",
    rejectLabel: "Отмена",
    acceptLabel: "Удалить",
    rejectClass: "p-button-secondary p-button-outlined",
    acceptClass: "p-button-danger !text-white",
    accept: async () => {
      try {
        await store.deleteTask(taskId);
        toast.add({
          severity: "success",
          summary: "Удалено",
          detail: "Задача удалена",
          life: 3000,
        });
        onClose();
      } catch (e) {
        toast.add({
          severity: "error",
          summary: "Ошибка",
          detail: getErrorMessage(e),
          life: 3000,
        });
      }
    },
  });
};

function startViewingPresence(taskId: number) {
  realtimeStore.sendProjectMessage({
    type: "task.viewing.started",
    taskId,
  });

  if (viewingHeartbeatTimer) {
    window.clearInterval(viewingHeartbeatTimer);
  }
  viewingHeartbeatTimer = window.setInterval(() => {
    realtimeStore.sendProjectMessage({
      type: "task.presence.heartbeat",
      taskId,
      mode: "viewing",
    });
  }, 1000);
}

function startEditingPresence(taskId: number) {
  editingPresenceActive.value = true;
  realtimeStore.sendProjectMessage({
    type: "task.editing.started",
    taskId,
  });

  if (editingHeartbeatTimer) {
    window.clearInterval(editingHeartbeatTimer);
  }
  editingHeartbeatTimer = window.setInterval(() => {
    realtimeStore.sendProjectMessage({
      type: "task.presence.heartbeat",
      taskId,
      mode: "editing",
    });
  }, 1000);
}

function stopPresence(taskId: number) {
  realtimeStore.sendProjectMessage({
    type: "task.viewing.stopped",
    taskId,
  });

  if (editingPresenceActive.value) {
    realtimeStore.sendProjectMessage({
      type: "task.editing.stopped",
      taskId,
    });
  }

  editingPresenceActive.value = false;

  if (viewingHeartbeatTimer) {
    window.clearInterval(viewingHeartbeatTimer);
    viewingHeartbeatTimer = null;
  }
  if (editingHeartbeatTimer) {
    window.clearInterval(editingHeartbeatTimer);
    editingHeartbeatTimer = null;
  }
}

onUnmounted(() => {
  if (store.selectedTask) {
    stopPresence(store.selectedTask.id);
  }
});
</script>

<template>
  <TaskDetailsPanel
    v-model:visible="isVisible"
    :beside-assistant="besideAssistant"
    @hide="onClose"
  >
    <template #header>
      <div class="flex items-center gap-3">
        <div class="p-2 rounded-lg bg-primary-50 dark:!bg-dark-surface">
          <i class="pi pi-check-square text-primary-600"></i>
        </div>
        <span class="font-bold text-slate-800 dark:text-white text-base">
          Детали задачи
        </span>
      </div>
    </template>

    <!-- BODY (Scrollable) -->
    <div class="flex-1 overflow-y-auto custom-scrollbar pr-2">
      <!-- LOADING STATE -->
      <div v-if="!store.selectedTask" class="space-y-6">
        <Skeleton height="2.5rem" class="!bg-gray-100 dark:!bg-slate-800" />
        <div class="space-y-2">
          <Skeleton
            width="40%"
            height="1.2rem"
            class="!bg-gray-100 dark:!bg-slate-800"
          />
          <Skeleton height="8rem" class="!bg-gray-100 dark:!bg-slate-800" />
        </div>
      </div>

      <!-- CONTENT -->
      <div v-else class="flex flex-col gap-8 pb-20">
        <div
          v-if="editingUsersCount > 0"
          class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300"
        >
          Эту задачу сейчас редактируют другие участники ({{ editingUsersCount }}).
        </div>

        <!-- Task Title Section -->
        <div class="group flex flex-col gap-1">
          <label
            class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 ml-1"
            >Название</label
          >
          <InputText
            v-model="localTitle"
            class="!text-xl !font-bold !bg-transparent !border-transparent hover:!bg-gray-50 dark:hover:!bg-slate-800/50 focus:!border-primary-500 !px-2 !transition-all dark:!text-white"
            placeholder="Введите название задачи..."
            @blur="saveTitle"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          />
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <!-- Left Column -->
          <div class="lg:col-span-2 flex flex-col gap-6">
            <div class="flex flex-col gap-3">
              <div
                class="flex items-center gap-2 text-slate-800 dark:text-slate-200 font-bold text-sm"
              >
                <i class="pi pi-align-left text-slate-400"></i>
                Описание
              </div>
              <Textarea
                v-model="localDescription"
                rows="6"
                placeholder="Добавьте описание задачи (Markdown...)"
                class="w-full min-h-60 !bg-gray-50 dark:!bg-dark-bg/40 !border-gray-200 dark:!border-dark-border focus:!bg-white dark:focus:!bg-dark-bg focus:!ring-1 focus:!ring-primary-500 !text-slate-700 dark:!text-slate-300 !transition-colors !rounded-lg !p-3 !text-sm !leading-relaxed"
              />
              <div
                class="flex justify-between items-center text-[11px] text-slate-400"
              >
                <span class="flex items-center gap-1"
                  ><i class="pi pi-info-circle"></i> Markdown</span
                >
              </div>
            </div>
            <!-- Даты -->
            <div
              class="flex flex-col gap-1 mb-4 p-3 bg-gray-50 dark:bg-dark-bg/30 rounded-lg border border-gray-100 dark:border-dark-border"
            >
              <div class="flex justify-between text-[10px] text-slate-500">
                <span>Создано:</span>
                <span class="font-medium text-slate-700 dark:text-slate-300">{{
                  formatDate(store.selectedTask?.createdAt)
                }}</span>
              </div>
              <div class="flex justify-between text-[10px] text-slate-500">
                <span>Обновлено:</span>
                <span class="font-medium text-slate-700 dark:text-slate-300">{{
                  formatDate(store.selectedTask?.updatedAt)
                }}</span>
              </div>
            </div>
          </div>

          <!-- Sidebar Right -->
          <div class="lg:col-span-1 flex flex-col gap-6">
            <TaskSidebar
              v-model:assigneeId="localAssigneeId"
              v-model:priority="localPriority"
              v-model:deadlineAt="localDeadlineAt"
              v-model:tagIds="localTagIds"
            >
            </TaskSidebar>

            <div class="pt-4 border-t border-gray-100 dark:border-dark-border">
              <Button
                label="Удалить задачу"
                icon="pi pi-trash"
                severity="danger"
                text
                class="!w-full !justify-start !text-xs !font-bold !py-2 hover:!bg-red-50 dark:hover:!bg-red-900/10"
                @click="deleteTask"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- FOOTER (Fixed) -->
    <template #footer>
      <div class="flex items-center justify-between w-full pt-2">
        <!-- Status Indicator -->
        <div
          class="flex items-center gap-2 text-xs transition-all duration-300 h-8"
        >
          <template v-if="isSaving">
            <i class="pi pi-spin pi-spinner text-primary-500"></i>
            <span class="text-slate-500 dark:text-slate-400"
              >Сохранение...</span
            >
          </template>
          <template v-else-if="lastSavedAt">
            <i class="pi pi-check text-green-500"></i>
            <span class="text-slate-500 dark:text-slate-400">
              Изменения сохранены
              <span class="text-slate-400 text-[10px]"
                >({{ lastSavedTime }})</span
              >
            </span>
          </template>
        </div>

        <!-- Actions -->
        <div class="flex gap-2">
          <Button
            label="Закрыть"
            text
            severity="secondary"
            size="small"
            @click="onClose"
          />
          <Button
            label="Сохранить"
            icon="pi pi-check"
            size="small"
            class="!bg-primary-600 !border-none !text-white !font-bold"
            :loading="isSaving"
            @click="saveAllAndClose"
          />
        </div>
      </div>
    </template>
  </TaskDetailsPanel>
</template>

<style scoped>
/* Скроллбар в стиле дашборда */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  @apply bg-transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  @apply bg-gray-200 dark:bg-slate-700 rounded-full;
}

:deep(.p-inputtext:focus) {
  box-shadow: none !important;
}

</style>
