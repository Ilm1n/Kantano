<script
    setup
    lang="ts"
>
import {computed, ref, watch} from 'vue';
import {useRouter} from 'vue-router';
import {useAuthStore} from '@/modules/auth/store/auth.store';
import {useTheme} from '@/composables/useTheme';
import SidebarLink from '@/layouts/components/SidebarLink.vue';
import Menu from 'primevue/menu';
import {useBreakpoints} from "@vueuse/core";
import UserAvatar from "@/shared/ui/UserAvatar.vue"; //
import { useRealtimeStore } from '@/modules/realtime/store/realtime.store';
import { useAssistantStore } from '@/modules/assistant/store/assistant.store';
import AssistantPanel from '@/modules/assistant/components/AssistantPanel.vue';

const authStore = useAuthStore();
const realtimeStore = useRealtimeStore();
const assistantStore = useAssistantStore();
const router = useRouter();
const {isDark, toggleTheme} = useTheme();
const isMobileMenuOpen = ref(false);

const isSidebarCollapsed = ref(localStorage.getItem('sidebarCollapsed') === 'true');

const toggleSidebar = () => {
  if (isMobile.value) {
    isMobileMenuOpen.value = false;
    return;
  }

  isSidebarCollapsed.value = !isSidebarCollapsed.value;
};

watch(isSidebarCollapsed, (val) => {
  localStorage.setItem('sidebarCollapsed', String(val));
});

const toggleMobileMenu = () => {
  isMobileMenuOpen.value = !isMobileMenuOpen.value;
};

const menuItems = [
  {label: 'Проекты', to: '/projects', icon: 'pi pi-th-large'},
];

// --- Логика Меню Пользователя ---
const userMenu = ref();
const userMenuItems = [
  {
    label: 'Профиль',
    icon: 'pi pi-user',
    command: () => {
      router.push('/profile');
    }
  },
  {
    separator: true
  },
  {
    label: 'Выйти',
    icon: 'pi pi-sign-out',
    class: 'text-red-500',
    command: () => {
      authStore.logout();
    }
  }
];

const toggleUserMenu = (event: Event) => {
  userMenu.value.toggle(event);
};

const avatarImage = computed<string | undefined>(() =>
    authStore.user?.avatarUrl || undefined
);

const avatarLabel = computed<string | undefined>(() =>
    avatarImage.value
        ? undefined
        : authStore.user?.username?.charAt(0).toUpperCase()
);

const breakpoints = useBreakpoints({
  lg: 1024,
});

const isMobile = breakpoints.smaller('lg');

watch(
  () => authStore.accessToken,
  (token) => {
    if (token) {
      realtimeStore.connectUser();
    } else {
      realtimeStore.disconnectProject();
      realtimeStore.disconnectUser();
      assistantStore.reset();
    }
  },
  { immediate: true }
);
</script>

<template>
  <div class="flex h-screen bg-gray-50 dark:bg-dark-bg transition-colors duration-300 font-sans">

    <!-- Mobile Overlay -->
    <div
        v-if="isMobileMenuOpen"
        class="fixed inset-0 bg-black/50 z-20 lg:hidden backdrop-blur-sm"
        @click="isMobileMenuOpen = false"
    ></div>

    <!-- SIDEBAR -->
    <aside
        class="fixed lg:static inset-y-0 left-0 z-30 bg-white dark:bg-dark-surface border-r border-gray-200 dark:border-dark-border transform transition-all duration-300 ease-in-out flex flex-col overflow-hidden"
        :class="[
        isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        isSidebarCollapsed ? 'w-20' : 'w-72'
      ]"
    >
      <!-- HEADER -->
      <div class="h-16 flex items-center px-5 border-b border-gray-100 dark:border-dark-border/50 flex-shrink-0 transition-all duration-300">
        <div
            class="flex items-center gap-3 overflow-hidden transition-all duration-300 ease-in-out whitespace-nowrap"
            :class="isSidebarCollapsed ? 'w-0 opacity-0 mr-0' : 'w-40 opacity-100 mr-auto'"
        >
          <i class="pi pi-bolt text-primary-500 text-2xl flex-shrink-0"></i>
          <span class="text-lg font-bold text-slate-800 dark:text-white tracking-tight">Kantano</span>
        </div>

        <button
            @click="toggleSidebar"
            class="w-10 h-10 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors flex-shrink-0"
            :title="isSidebarCollapsed ? 'Развернуть' : 'Свернуть'"
        >
          <i
              class="pi"
              :class="isSidebarCollapsed ? 'pi-align-justify' : 'pi-align-left'"
              style="font-size: 1.1rem"
          ></i>
        </button>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 px-3 py-6 space-y-2 overflow-y-auto overflow-x-hidden">
        <SidebarLink
            v-for="item in menuItems"
            :key="item.to"
            v-bind="item"
            :collapsed="isSidebarCollapsed"
            @click="isMobileMenuOpen = false"
        />
        <button
          type="button"
          title="Помощник"
          class="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left font-medium text-slate-600 transition-colors hover:bg-gray-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700/50 dark:hover:text-slate-200"
          :class="isSidebarCollapsed ? 'justify-center !px-2' : ''"
          @click="isMobileMenuOpen = false; assistantStore.openFromMenu()"
        >
          <i class="pi pi-sparkles shrink-0 text-lg" aria-hidden="true"></i>
          <span v-if="!isSidebarCollapsed">Помощник</span>
        </button>
      </nav>

      <!-- User Profile & Footer -->
      <div class="border-t border-gray-100 dark:border-dark-border/50 bg-gray-50/50 dark:bg-slate-800/50 overflow-hidden flex-shrink-0">

        <!-- Theme Toggle -->
        <div class="flex items-center px-5 h-12 transition-all duration-300">
          <span
              class="text-xs font-semibold text-slate-400 uppercase tracking-wider whitespace-nowrap overflow-hidden transition-all duration-300 ease-in-out"
              :class="isSidebarCollapsed ? 'w-0 opacity-0' : 'w-full opacity-100'"
          >
            Тема
          </span>
          <button
              @click="toggleTheme"
              class="w-10 h-10 flex items-center justify-center text-slate-500 hover:text-primary-500 transition-colors flex-shrink-0"
          >
            <i :class="isDark ? 'pi pi-sun' : 'pi pi-moon'"></i>
          </button>
        </div>

        <!-- User Info (Clickable for Menu) -->
        <div class="flex items-center px-3 pb-4 pt-2">
          <div
              @click="toggleUserMenu"
              aria-haspopup="true"
              aria-controls="user_menu"
              class="flex items-center  gap-3 p-2 w-full rounded-xl  hover:bg-white dark:hover:bg-slate-700 transition-colors cursor-pointer group overflow-hidden relative"
          >
            <!-- Аватар -->
            <div
                class="flex items-center justify-center rounded-full  w-10 h-10 flex-shrink-0"
            >
              <UserAvatar
                  :image="avatarImage"
                  :label="avatarLabel"
              />
            </div>

            <!-- Текст -->
            <div
                class="flex items-center justify-between overflow-hidden transition-all duration-300 ease-in-out"
                :class="isSidebarCollapsed ? 'w-0 opacity-0' : 'flex-1 opacity-100 min-w-[120px]'"
            >
              <div class="min-w-0 mr-2 ml-2">
                <p class="text-sm font-semibold text-slate-700 dark:text-gray-200 truncate">
                  {{ authStore.user?.username || authStore.user?.fullName }}
                </p>
                <p class="text-xs text-slate-500 dark:text-slate-400 truncate">
                  {{ authStore.user?.email }}
                </p>
              </div>

              <i class="pi pi-chevron-up text-xs text-slate-400 mr-1"></i>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- Компонент Меню  -->
    <Menu
        ref="userMenu"
        id="user_menu"
        :model="userMenuItems"
        :popup="true"
    />

    <!-- MAIN CONTENT -->
    <main class="flex-1 flex flex-col min-w-0 overflow-hidden relative">
      <!-- Mobile Header -->
      <header class="lg:hidden h-16 bg-white dark:bg-dark-surface border-b border-gray-200 dark:border-dark-border flex items-center px-4 justify-between shrink-0">
        <div class="flex items-center gap-3">
          <button
              @click="toggleMobileMenu"
              class="text-slate-500 hover:text-slate-700 dark:text-slate-400"
          >
            <i class="pi pi-bars text-xl"></i>
          </button>
          <span class="font-bold text-slate-800 dark:text-white">Kantano</span>
        </div>
        <div class="flex items-center gap-3">

          <button
              @click="toggleTheme"
              class="w-10 h-10 flex items-center justify-center text-slate-500 hover:text-primary-500 transition-colors flex-shrink-0"
          >
            <i :class="isDark ? 'pi pi-sun' : 'pi pi-moon'"></i>
          </button>
          <div
              @click="toggleUserMenu"
              aria-haspopup="true"
              aria-controls="user_menu"
              class="flex items-center  gap-3 p-2 w-full rounded-xl  hover:bg-white dark:hover:bg-slate-700 transition-colors cursor-pointer group overflow-hidden relative"
          >
            <UserAvatar
                :image="avatarImage"
                :label="avatarLabel"
            />
          </div>
        </div>
      </header>

      <div class="flex-1 overflow-auto scroll-smooth">
        <div class="h-full">
          <router-view />
        </div>
      </div>
    </main>
    <AssistantPanel v-if="assistantStore.isOpen" />
  </div>
</template>

<style>
</style>
