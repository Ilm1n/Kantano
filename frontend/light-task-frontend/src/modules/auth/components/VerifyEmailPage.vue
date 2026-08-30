<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useHead } from '@unhead/vue';
import { useForm } from 'vee-validate';
import { toTypedSchema } from '@vee-validate/zod';
import * as z from 'zod';
import Button from 'primevue/button';
import Password from 'primevue/password';

import { apiClient } from '@/api/config';
import { useTheme } from '@/composables/useTheme';

const route = useRoute();
const router = useRouter();
const { isDark, toggleTheme } = useTheme();
const token = ref('');
const status = ref<'loading' | 'ready' | 'invalid' | 'confirmed'>('loading');
const validationSchema = toTypedSchema(
  z.object({
    password: z.string({ required_error: 'Обязательное поле' }).min(8, 'Минимум 8 символов'),
    confirmPassword: z.string({ required_error: 'Повторите пароль' }),
  }).refine((data) => data.password === data.confirmPassword, {
    message: 'Пароли не совпадают',
    path: ['confirmPassword'],
  }),
);
const { defineField, handleSubmit, errors, isSubmitting } = useForm({ validationSchema });
const [password, passwordAttrs] = defineField('password');
const [confirmPassword, confirmPasswordAttrs] = defineField('confirmPassword');

onMounted(async () => {
  token.value = String(route.query.token ?? '');
  await router.replace({ query: {} });
  if (!token.value) {
    status.value = 'invalid';
    return;
  }

  try {
    await apiClient.registration.validateTokenApiRegistrationValidatePost({ token: token.value });
    status.value = 'ready';
  } catch {
    status.value = 'invalid';
  }
});

const onSubmit = handleSubmit(async (values) => {
  try {
    await apiClient.registration.confirmApiRegistrationConfirmPost({
      token: token.value,
      password: values.password,
    });
    sessionStorage.removeItem('registrationEmail');
    sessionStorage.removeItem('registrationResendAllowedAt');
    status.value = 'confirmed';
  } catch {
    status.value = 'invalid';
  }
});

useHead({
  title: 'Подтверждение почты — Kantano',
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
      to="/"
      class="absolute left-6 top-6 z-20 flex items-center gap-2 rounded-full bg-white/70 px-3 py-2 text-sm font-medium text-slate-700 shadow-md backdrop-blur transition-colors hover:bg-white dark:bg-dark-surface/70 dark:text-white dark:hover:bg-dark-surface"
    >
      <i class="pi pi-arrow-left" />
      На главную
    </RouterLink>

    <section class="z-10 w-full max-w-md rounded-2xl border border-gray-100 bg-white p-8 shadow-xl transition-colors duration-300 dark:border-dark-border dark:bg-dark-surface">
      <header class="mb-8 text-center">
        <RouterLink to="/" class="inline-block">
          <h1 class="mb-6 text-3xl font-bold tracking-tight text-slate-800 dark:text-white">Kantano</h1>
        </RouterLink>
        <div
          class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full"
          :class="status === 'invalid' ? 'bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-300' : 'bg-primary-100 text-primary-600 dark:bg-primary-500/20 dark:text-primary-300'"
        >
          <i
            :class="status === 'loading' ? 'pi pi-spinner pi-spin' : status === 'invalid' ? 'pi pi-times-circle' : status === 'confirmed' ? 'pi pi-check-circle' : 'pi pi-shield'"
            style="font-size: 1.5rem"
          />
        </div>

        <template v-if="status === 'loading'">
          <h2 class="text-2xl font-bold text-slate-800 dark:text-white">Проверяем ссылку</h2>
          <p class="mt-2 text-slate-500 dark:text-slate-400">Это займёт всего несколько секунд.</p>
        </template>
        <template v-else-if="status === 'ready'">
          <h2 class="text-2xl font-bold text-slate-800 dark:text-white">Почта подтверждена</h2>
          <p class="mt-2 text-slate-500 dark:text-slate-400">Придумайте пароль для нового аккаунта.</p>
        </template>
        <template v-else-if="status === 'confirmed'">
          <h2 class="text-2xl font-bold text-slate-800 dark:text-white">Аккаунт создан</h2>
          <p class="mt-2 text-slate-500 dark:text-slate-400">Почта подтверждена. Теперь можно войти.</p>
        </template>
        <template v-else>
          <h2 class="text-2xl font-bold text-slate-800 dark:text-white">Ссылка недействительна</h2>
          <p class="mt-2 text-slate-500 dark:text-slate-400">Возможно, она уже использована или срок её действия истёк.</p>
        </template>
      </header>

      <form v-if="status === 'ready'" class="space-y-3" @submit.prevent="onSubmit">
        <div>
          <label for="verification-password" class="mb-2 block text-base font-medium text-slate-700 dark:text-gray-200">Пароль</label>
          <Password
            input-id="verification-password"
            v-model="password"
            v-bind="passwordAttrs"
            :invalid="!!errors.password"
            :feedback="false"
            toggle-mask
            class="w-full"
            input-class="w-full !p-3 !text-base"
            :input-props="{ autocomplete: 'new-password' }"
          />
          <div class="mt-1 min-h-[1.5rem]">
            <small v-if="errors.password" class="text-red-500">{{ errors.password }}</small>
          </div>
        </div>
        <div>
          <label for="verification-confirm-password" class="mb-2 block text-base font-medium text-slate-700 dark:text-gray-200">Повторите пароль</label>
          <Password
            input-id="verification-confirm-password"
            v-model="confirmPassword"
            v-bind="confirmPasswordAttrs"
            :invalid="!!errors.confirmPassword"
            :feedback="false"
            toggle-mask
            class="w-full"
            input-class="w-full !p-3 !text-base"
            :input-props="{ autocomplete: 'new-password' }"
          />
          <div class="mt-1 min-h-[1.5rem]">
            <small v-if="errors.confirmPassword" class="text-red-500">{{ errors.confirmPassword }}</small>
          </div>
        </div>
        <Button
          type="submit"
          label="Создать аккаунт"
          :loading="isSubmitting"
          class="mt-2 w-full !rounded-xl !border-none !bg-primary-600 !py-3.5 !text-base !font-semibold !text-white shadow-md shadow-primary-500/30 hover:!bg-primary-700"
        />
      </form>

      <div v-else-if="status === 'confirmed'" class="text-center">
        <RouterLink to="/login" class="inline-flex w-full items-center justify-center rounded-xl bg-primary-600 px-4 py-3.5 text-base font-semibold text-white shadow-md shadow-primary-500/30 transition-colors hover:bg-primary-700">
          Войти
        </RouterLink>
      </div>

      <div v-else-if="status === 'invalid'" class="text-center">
        <RouterLink to="/register" class="inline-flex w-full items-center justify-center rounded-xl bg-primary-600 px-4 py-3.5 text-base font-semibold text-white shadow-md shadow-primary-500/30 transition-colors hover:bg-primary-700">
          Зарегистрироваться заново
        </RouterLink>
      </div>
    </section>
  </div>
</template>

<style scoped>
:deep(.p-password .p-icon) {
  @apply text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300;
}
</style>
