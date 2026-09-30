<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { useEventListener } from '@vueuse/core';
import Drawer from 'primevue/drawer';

const props = defineProps<{ visible: boolean; besideAssistant: boolean; assistantWidth: number }>();
const emit = defineEmits<{ 'update:visible': [value: boolean]; hide: [] }>();
const panel = ref<HTMLElement | null>(null);
const closeButton = ref<HTMLButtonElement | null>(null);

function close() {
  emit('update:visible', false);
  emit('hide');
}

watch(() => props.visible && props.besideAssistant, async (open) => {
  if (open) {
    await nextTick();
    closeButton.value?.focus();
  }
});

useEventListener(document, 'keydown', (event) => {
  if (event.key === 'Escape' && panel.value?.contains(event.target as Node)) close();
});
</script>

<template>
  <Teleport v-if="besideAssistant" to="body">
    <template v-if="visible">
      <!-- Keep the non-modal panel below PrimeVue dropdowns and calendars. -->
      <div :style="{ right: `${assistantWidth}px` }" class="fixed inset-y-0 left-0 z-[900] bg-black/15" aria-hidden="true" @mousedown.self="close"></div>
      <aside ref="panel" :style="{ right: `${assistantWidth}px` }" aria-label="Детали задачи" class="fixed inset-y-0 z-[901] flex w-[700px] flex-col border-l border-slate-200 bg-white shadow-xl dark:border-dark-border dark:bg-dark-surface">
        <header class="flex shrink-0 items-center justify-between border-b border-gray-200 p-5 dark:border-dark-border">
          <slot name="header"></slot>
          <button ref="closeButton" type="button" aria-label="Закрыть детали задачи" class="rounded-lg p-2 text-slate-500 hover:bg-gray-100 dark:hover:bg-slate-800" @click="close">
            <i class="pi pi-times" aria-hidden="true"></i>
          </button>
        </header>
        <div class="flex min-h-0 flex-1 flex-col overflow-hidden p-6"><slot></slot></div>
        <footer class="shrink-0 border-t border-gray-200 p-5 dark:border-dark-border"><slot name="footer"></slot></footer>
      </aside>
    </template>
  </Teleport>
  <Drawer v-else :visible="visible" position="right" class="!w-full md:!w-[700px] !bg-white dark:!bg-dark-surface !border-l dark:!border-dark-border !transition-colors !duration-100"
    :pt="{
      mask: { class: '!bg-black/15' },
      header: { class: '!bg-white dark:!bg-dark-surface !border-b !border-gray-200 dark:!border-dark-border !p-5' },
      content: { class: '!bg-white dark:!bg-dark-surface !p-6 !overflow-hidden flex flex-col' },
      closeButton: { class: 'hover:!bg-gray-100 dark:hover:!bg-slate-800 !text-slate-500' },
    }"
    @update:visible="emit('update:visible', $event)" @hide="emit('hide')">
    <template #header><slot name="header"></slot></template>
    <slot></slot>
    <template #footer><slot name="footer"></slot></template>
  </Drawer>
</template>
