<script
    setup
    lang="ts"
>
import {useAuthStore} from '../store/auth.store';
import { useRouter, useRoute } from 'vue-router';
import {useToast} from 'primevue/usetoast';
import {useForm} from 'vee-validate';
import {useHead} from "@unhead/vue";
import {toTypedSchema} from '@vee-validate/zod';
import * as z from 'zod';
import {useTheme} from '@/composables/useTheme';

import InputText from 'primevue/inputtext';
import Button from 'primevue/button';
import {getErrorMessage} from "@/utils/error.ts";
import yandexLogo from '@/assets/images/brand/yandex.svg';
import {redirectToYandexAuth} from '@/modules/auth/lib/yandex-auth';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const toast = useToast();
const {isDark, toggleTheme} = useTheme();

const validationSchema = toTypedSchema(
    z.object({
      username: z.string({required_error: 'Обязательное поле'})
          .min(3, 'Минимум 3 символа')
          .max(50, 'Максимум 50 символов'),
      email: z.string({required_error: 'Обязательное поле'})
          .email('Введите корректный email'),
    })
);

const { defineField, handleSubmit, errors, isSubmitting } = useForm({
  validationSchema,
  initialValues: {
    email: (route.query.email as string) || '',
    username: ''
  }
});

const [username, usernameAttrs] = defineField('username');
const [email, emailAttrs] = defineField('email');

const onSubmit = handleSubmit(async (values) => {
  try {
    await authStore.register({
      username: values.username,
      email: values.email,
    });

    toast.add({
      severity: 'success',
      summary: 'Проверьте почту',
      detail: 'Мы отправили ссылку для подтверждения email',
      life: 5000
    });

    await router.push('/register/check-email');

  } catch (error: any) {
    const errorMsg = getErrorMessage(error);

    toast.add({
      severity: 'error',
      summary: 'Ошибка',
      detail: errorMsg,
      life: 5000
    });
  }
});

useHead({
  title: 'Регистрация в Kantano',
  meta:[
    { name: 'robots', content: 'noindex, nofollow' }
  ]
});
</script>

<template>
  <div class="min-h-screen flex items-center justify-center p-4 relative overflow-hidden transition-colors duration-300">

    <!-- Decorative Blobs -->
    <div class="absolute top-[-5%] left-[-5%] w-48 h-48 sm:w-64 sm:h-64 md:w-80 md:h-80 lg:w-96 lg:h-96 bg-primary-500/20 rounded-full blur-3xl pointer-events-none"></div>
    <div class="absolute bottom-[-5%] right-[-5%] w-48 h-48 sm:w-64 sm:h-64 md:w-80 md:h-80 lg:w-96 lg:h-96 bg-purple-500/20 rounded-full blur-3xl pointer-events-none"></div>

    <!-- Theme Toggle -->
    <button
        @click="toggleTheme"
        class="absolute top-6 right-6 p-2 rounded-full hover:bg-gray-200 dark:hover:bg-dark-surface transition-colors z-20"
    >
      <i :class="isDark ? 'pi pi-sun text-yellow-400' : 'pi pi-moon text-slate-600'" style="font-size: 1.5rem"></i>
    </button>

    <!-- Back To Landing -->
    <router-link
        to="/"
        class="absolute top-6 left-6 z-20 flex items-center gap-2
           px-3 py-2 rounded-full
           bg-white/70 dark:bg-dark-surface/70 backdrop-blur
           hover:bg-white dark:hover:bg-dark-surface
           transition-colors shadow-md"
    >
      <i class="pi pi-arrow-left text-slate-700 dark:text-white"></i>
      <span class="text-sm font-medium text-slate-700 dark:text-white">
    Назад
  </span>
    </router-link>

    <!-- Register Card -->
    <div class="w-full max-w-md bg-white dark:bg-dark-surface rounded-2xl shadow-xl p-8 z-10 border border-gray-100 dark:border-dark-border transition-colors duration-300">

      <div class="text-center mb-8">
        <router-link to="/"><h1 class="text-3xl font-bold text-slate-800 dark:text-white mb-2 tracking-tight">Kantano</h1></router-link>
        <p class="text-slate-500 dark:text-slate-400">Создайте аккаунт в Kantano</p>
      </div>

      <form @submit.prevent="onSubmit" class="space-y-3">

        <!-- Username -->
        <div>
          <label for="reg-username" class="block text-base font-medium text-slate-700 dark:text-gray-200 mb-2">Имя пользователя</label>
          <InputText
              id="reg-username"
              v-model="username"
              v-bind="usernameAttrs"
              :invalid="!!errors.username"
              class="w-full !p-3"
              placeholder="ivan_ivanov"
          />
          <div class="min-h-[1.5rem] mt-1">
            <small class="text-red-500" v-if="errors.username">{{ errors.username }}</small>
          </div>
        </div>

        <!-- Email -->
        <div>
          <label for="reg-email" class="block text-base font-medium text-slate-700 dark:text-gray-200 mb-2">Email</label>
          <InputText
              id="reg-email"
              v-model="email"
              v-bind="emailAttrs"
              :invalid="!!errors.email"
              class="w-full !p-3"
              placeholder="example@mail.com"
          />
          <div class="min-h-[1.5rem] mt-1">
            <small class="text-red-500" v-if="errors.email">{{ errors.email }}</small>
          </div>
        </div>

        <Button
            type="submit"
            label="Создать аккаунт"
            :loading="isSubmitting"
            class="w-full !rounded-xl !bg-primary-600 hover:!bg-primary-700 !border-none !py-3.5 !text-base !font-semibold shadow-md shadow-primary-500/30 !text-white mt-2"
        />
      </form>

      <div class="my-5 flex items-center gap-3 text-xs uppercase text-slate-400 dark:text-slate-500">
        <span class="h-px flex-1 bg-slate-200 dark:bg-dark-border"></span>
        <span>или</span>
        <span class="h-px flex-1 bg-slate-200 dark:bg-dark-border"></span>
      </div>

      <button
          type="button"
          class="flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-4 text-base font-semibold text-slate-800 transition-colors hover:bg-slate-50 dark:border-dark-border dark:bg-dark-bg dark:text-white dark:hover:bg-slate-800"
          @click="redirectToYandexAuth"
      >
        <img
            :src="yandexLogo"
            alt=""
            class="h-5 w-5"
        >
        <span>Войти через Yandex</span>
      </button>

      <!-- Footer -->
      <div class="mt-6 text-center text-sm text-slate-500 dark:text-slate-400">
        Уже есть аккаунт?
        <router-link
            to="/login"
            class="text-primary-600 dark:text-primary-400 hover:underline font-medium"
        >Войти
        </router-link>
      </div>
    </div>
  </div>
</template>
