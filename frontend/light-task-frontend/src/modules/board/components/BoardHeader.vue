<script setup lang="ts">
import { useRouter } from "vue-router";
import { ref } from "vue";
import { useBoardStore } from "../store/board.store";
import Button from "primevue/button";
import Skeleton from "primevue/skeleton";
import InviteMemberDialog from "@/modules/invitations/components/InviteMemberDialog.vue";
import ProjectSettingsDialog from "./ProjectSettingsDialog.vue";
import { ProjectRole } from "@/api/client";
import BoardFilters from "./BoardFilters.vue";
import { useAssistantStore } from "@/modules/assistant/store/assistant.store";

const isSettingsVisible = ref(false);
const isInviteVisible = ref(false);

const store = useBoardStore();
const assistantStore = useAssistantStore();
const router = useRouter();

const goBack = () => {
  router.push("/projects");
};
</script>

<template>
  <div
    class="h-16 px-3 sm:px-6 border-b border-gray-200 dark:border-dark-border bg-white dark:bg-dark-surface flex items-center justify-between shrink-0 transition-colors duration-300"
  >
    <!-- LEFT: Back & Title -->
    <div class="flex items-center gap-2 sm:gap-4 min-w-0">
      <Button
        icon="pi pi-arrow-left"
        text
        rounded
        aria-label="Назад"
        class="!text-slate-500 hover:!bg-slate-100 dark:hover:!bg-slate-800 shrink-0"
        @click="goBack"
      />

      <div v-if="store.isLoading && !store.project" class="flex flex-col gap-1">
        <Skeleton width="6rem" height="1.5rem" />
      </div>

      <div v-else-if="store.project" class="min-w-0 flex flex-col">
        <h1
          class="text-lg sm:text-xl font-bold text-slate-800 dark:text-white leading-tight truncate max-w-[200px] sm:max-w-[400px]"
        >
          {{ store.project.name }}
        </h1>
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :style="{ backgroundColor: store.project.color }"
          ></span>
          <span
            class="truncate hidden sm:block max-w-[250px] italic opacity-80"
            :title="store.project.description || ''"
          >
            {{ store.project.description || "Без описания" }}
          </span>
        </div>
      </div>
    </div>

    <!-- RIGHT: Members & Actions -->
    <div class="flex items-center gap-2 sm:gap-4 shrink-0">
      <Button
        icon="pi pi-sparkles"
        text
        rounded
        aria-label="Открыть помощника для этого проекта"
        title="Помощник"
        class="!text-primary-600 !w-10 !h-10 !p-0"
        :disabled="!store.project"
        @click="store.project && assistantStore.openFromBoard(store.project.id)"
      />
      <BoardFilters />
      <div
        class="h-6 w-px bg-slate-200 dark:bg-slate-700 hidden sm:block"
      ></div>

      <!-- Board Presence -->
      <div
        v-if="store.project"
        class="hidden md:inline-flex h-8 items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 text-xs font-bold text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-300"
        :title="store.activeBoardPresenceLabel"
      >
        <span
          class="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(34,197,94,0.18)]"
          aria-hidden="true"
        ></span>
        <span>{{ store.activeBoardPresenceLabel }}</span>
      </div>

      <!-- Settings  -->
      <Button
        v-if="
          store.project?.currentUserRole === ProjectRole.OWNER ||
          store.project?.currentUserRole === ProjectRole.MANAGER
        "
        icon="pi pi-cog"
        text
        rounded
        class="!text-slate-400 !w-10 !h-10 !p-0"
        @click="isSettingsVisible = true"
      />

      <!-- Invite Button  -->
      <Button
        v-if="store.project?.currentUserRole !== ProjectRole.MEMBER"
        class="!bg-primary-600 dark:!text-white !border-none !text-sm !px-3 sm:!px-4 !rounded-lg"
        @click="isInviteVisible = true"
      >
        <i class="pi pi-user-plus sm:mr-2"></i>
        <span class="hidden sm:inline">Пригласить</span>
      </Button>
    </div>
    <InviteMemberDialog v-model:visible="isInviteVisible" />
    <ProjectSettingsDialog v-model:visible="isSettingsVisible" />
  </div>
</template>

