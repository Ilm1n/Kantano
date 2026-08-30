import {createRouter, createWebHistory} from 'vue-router';
import {useAuthStore} from '@/modules/auth/store/auth.store';

// Layouts
const AppLayout = () => import('@/layouts/components/AppLayout.vue');

// Pages
const LoginPage = () => import('@/modules/auth/components/LoginPage.vue');
const RegisterPage = () => import('@/modules/auth/components/RegisterPage.vue');
const YandexCallbackPage = () => import('@/modules/auth/components/YandexCallbackPage.vue');
const VerifyEmailPage = () => import('@/modules/auth/components/VerifyEmailPage.vue');
const CheckEmailPage = () => import('@/modules/auth/components/CheckEmailPage.vue');
const ProjectsList = () => import('@/modules/projects/components/ProjectsList.vue');
const BoardPage = () => import('@/modules/board/pages/BoardPage.vue');
const ProfilePage = () => import('@/modules/profile/pages/ProfilePage.vue');
const LandingPage = () => import('@/modules/landing/pages/LandingPage.vue');
const AcceptInvitationPage = () => import('@/modules/invitations/pages/AcceptInvitationPage.vue');
const NotFoundPage = () => import('@/modules/common/pages/NotFoundPage.vue');


const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'landing',
      component: LandingPage,
      meta: { requiresAuth: false }
    },
    {
      path: '/login',
      name: 'login',
      component: LoginPage,
      meta: {requiresAuth: false}
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterPage,
      meta: {requiresAuth: false}
    },
    { path: '/register/check-email', component: CheckEmailPage, meta: { requiresAuth: false } },
    { path: '/verify-email', component: VerifyEmailPage, meta: { requiresAuth: false } },
    {
      path: '/auth/yandex/callback',
      name: 'yandex-callback',
      component: YandexCallbackPage,
      meta: {requiresAuth: false}
    },
    {
      path: '/invite/:token',
      name: 'accept-invite',
      component: AcceptInvitationPage,
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        {
          path: 'projects',
          name: 'home',
          component: ProjectsList
        },
        {
          path: 'projects/:projectId/board',
          name: 'project-board',
          component: BoardPage,
          props: true
        },
        {
          path: 'profile',
          name: 'profile',
          component: ProfilePage
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundPage,
      meta: { requiresAuth: false }
    }
  ]
});

router.beforeEach(async (to, _, next) => {
  const authStore = useAuthStore();

  if (to.path === '/login' || to.path === '/register') {
    if (!authStore.isAuthenticated) {
      await authStore.restoreSession();
    }

    if (authStore.isAuthenticated) {
      return next('/projects');
    }
    return next();
  }

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    const restored = await authStore.restoreSession();
    if (!restored) return next('/login');
  }

  next();
});

export default router;
