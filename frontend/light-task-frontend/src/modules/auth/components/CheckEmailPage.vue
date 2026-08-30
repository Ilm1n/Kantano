<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue';
import { useHead } from '@unhead/vue';
import Button from 'primevue/button';
import InputText from 'primevue/inputtext';

import { useTheme } from '@/composables/useTheme';
import { useAuthStore } from '@/modules/auth/store/auth.store';

const authStore = useAuthStore();
const { isDark, toggleTheme } = useTheme();
const email = ref(sessionStorage.getItem('registrationEmail') ?? '');
const resendAllowedAt = ref(Number(sessionStorage.getItem('registrationResendAllowedAt') ?? 0));
const now = ref(Date.now());
const message = ref('');
const messageIsError = ref(false);
const timer = window.setInterval(() => {
  now.value = Date.now();
}, 1000);

const secondsRemaining = computed(() =>
  Math.max(0, Math.ceil((resendAllowedAt.value - now.value) / 1000)),
);
const canResend = computed(
  () => Boolean(email.value) && secondsRemaining.value === 0 && !authStore.isLoading,
);

async function resend(): Promise<void> {
  if (!canResend.value) return;

  try {
    await authStore.resendVerification(email.value);
    resendAllowedAt.value = Number(sessionStorage.getItem('registrationResendAllowedAt'));
    message.value = 'Если регистрация возможна, мы отправили новую ссылку.';
    messageIsError.value = false;
  } catch {
    message.value = 'Не удалось отправить письмо. Попробуйте позже.';
    messageIsError.value = true;
  }
}

onUnmounted(() => window.clearInterval(timer));

useHead({
  title: 'Проверьте почту — Kantano',
  meta: [{ name: 'robots', content: 'noindex, nofollow' }],
});
</script>

<template>
  <div class="relative flex min-h-screen items-center justify-center overflow-hidden p-4 transition-colors duration-300">
    <div class="pointer-events-none absolute left-[-5%] top-[-5%] h-48 w-48 rounded-full bg-primary-500/20 blur-3xl sm:h-64 sm:w-64 md:h-80 md:w-80 lg:h-96 lg:w-96" />
    <div class="pointer-events-none absolute bottom-[-5%] right-[-5%] h-48 w-48 rounded-full bg-purple-500/20 blur-3xl sm:h-64 sm:w-64 md:h-80 md:w-80 lg:h-96 lg:w-96" />

    <button
      type="button"
      class="absolute right-6 top-6 z-20 rounded-full p-2 transition-colors hover:bg-gray-200 dark:hover:bg-dark-surface"
      aria-label="Сменить тему"
      @click="toggleTheme"
    >
      <i :class="isDark ? 'pi pi-sun text-yellow-400' : 'pi pi-moon text-slate-600'" style="font-size: 1.5rem" />
    </button>

    <RouterLink
      to="/register"
      class="absolute left-6 top-6 z-20 flex items-center gap-2 rounded-full bg-white/70 px-3 py-2 text-sm font-medium text-slate-700 shadow-md backdrop-blur transition-colors hover:bg-white dark:bg-dark-surface/70 dark:text-white dark:hover:bg-dark-surface"
    >
      <i class="pi pi-arrow-left" />
      К регистрации
    </RouterLink>

    <section class="z-10 w-full max-w-md rounded-2xl border border-gray-100 bg-white p-8 shadow-xl transition-colors duration-300 dark:border-dark-border dark:bg-dark-surface">
      <header class="mb-8 text-center">
        <RouterLink to="/" class="inline-block">
          <h1 class="mb-6 text-3xl font-bold tracking-tight text-slate-800 dark:text-white">Kantano</h1>
        </RouterLink>
        <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-primary-100 text-primary-600 dark:bg-primary-500/20 dark:text-primary-300">
          <i class="pi pi-envelope" style="font-size: 1.5rem" />
        </div>
        <h2 class="text-2xl font-bold text-slate-800 dark:text-white">Проверьте почту</h2>
        <p class="mt-2 text-slate-500 dark:text-slate-400">
          Перейдите по ссылке из письма, чтобы задать пароль и завершить регистрацию.
        </p>
      </header>

      <div class="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-dark-border dark:bg-dark-bg">
        <label for="resend-email" class="mb-2 block text-sm font-medium text-slate-700 dark:text-gray-200">Email</label>
        <InputText
          id="resend-email"
          v-model="email"
          type="email"
          autocomplete="email"
          class="w-full !p-3"
          placeholder="example@mail.com"
        />
        <p class="mt-3 text-sm leading-5 text-slate-500 dark:text-slate-400">
          Не нашли письмо? Проверьте папку «Спам» или запросите новую ссылку.
        </p>
      </div>

      <Button
        type="button"
        :label="secondsRemaining > 0 ? `Отправить повторно через ${secondsRemaining} сек.` : 'Отправить ссылку повторно'"
        :disabled="!canResend"
        :loading="authStore.isLoading"
        class="mt-5 w-full !rounded-xl !border-none !bg-primary-600 !py-3.5 !text-base !font-semibold !text-white shadow-md shadow-primary-500/30 hover:!bg-primary-700 disabled:!bg-slate-300 dark:disabled:!bg-slate-700"
        @click="resend"
      />

      <p
        v-if="message"
        class="mt-4 rounded-lg px-3 py-2 text-sm"
        :class="messageIsError ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300' : 'bg-primary-50 text-primary-700 dark:bg-primary-500/10 dark:text-primary-300'"
      >
        {{ message }}
      </p>

      <p class="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
        Уже подтвердили почту?
        <RouterLink to="/login" class="font-medium text-primary-600 hover:underline dark:text-primary-400">Войти</RouterLink>
      </p>
    </section>
  </div>
</template>
