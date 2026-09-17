<script setup lang="ts">
import { useRouter } from 'vue-router';
import Button from 'primevue/button';
import {useTheme} from "@/composables/useTheme.ts";

const router = useRouter();

const {isDark, toggleTheme} = useTheme();

const goHome = () => window.location.assign('/');

const goBack = () => {
  if (window.history.length > 1) {
    router.back();
  } else {
    goHome();
  }
};
</script>

<template>
  <div class="min-h-screen flex items-center relative overflow-hidden justify-center bg-gray-50 dark:bg-dark-bg p-6 transition-colors duration-300">
    <div class="absolute top-[-5%] left-[-5%] w-48 h-48 sm:w-64 sm:h-64 md:w-80 md:h-80 lg:w-96 lg:h-96 bg-primary-500/20 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute bottom-[-5%] right-[-5%] w-48 h-48 sm:w-64 sm:h-64 md:w-80 md:h-80 lg:w-96 lg:h-96 bg-purple-500/20 rounded-full blur-3xl pointer-events-none"></div>
    <div class="max-w-md w-full text-center">

      <div class="flex justify-end mb-8">
        <button
            @click="toggleTheme"
            class="absolute top-6 right-6 p-2 rounded-full hover:bg-gray-200 dark:hover:bg-dark-surface transition-colors z-20"
        >
          <i :class="isDark ? 'pi pi-sun text-yellow-400' : 'pi pi-moon text-slate-600'" style="font-size: 1.5rem"></i>
        </button>
      </div>

      <h1 class="text-9xl font-black text-primary-500/20 dark:text-primary-500/10 select-none">404</h1>

      <h2 class="text-3xl font-bold text-slate-800 dark:text-white mb-4 tracking-tight">
        Страница не найдена
      </h2>
      <p class="text-slate-500 dark:text-slate-400 mb-10 leading-relaxed">
        Похоже, вы забрели туда, где еще ничего нет. Проверьте адрес или вернитесь назад.
      </p>

      <div class="flex flex-col sm:flex-row gap-4 justify-center">
        <Button
            label="Вернуться назад"
            icon="pi pi-arrow-left"
            outlined
            class="!rounded-xl !px-6"
            @click="goBack"
        />
        <Button
            label="На главную"
            icon="pi pi-home"
            class="!bg-primary-600 !border-none !rounded-xl !px-6 !text-white"
            @click="goHome()"
        />
      </div>

    </div>
  </div>
</template>

<style scoped>
.max-w-md {
  animation: fadeInUp 0.5s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>