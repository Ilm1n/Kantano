// src/modules/auth/store/auth.store.ts
import {defineStore} from 'pinia';
import {computed, ref} from 'vue';
import {apiClient} from '@/api/config';
import type {
  Body_login_for_access_token_api_auth_login_post,
  RegistrationRequest,
  UserPasswordUpdate,
  UserRead,
  UserUpdate,
} from '@/api/client';
import {useRouter} from 'vue-router';
import {
  accessTokenState,
  setAccessTokenValue,
} from '@/modules/auth/lib/access-token';

export const useAuthStore = defineStore('auth', () => {
  const router = useRouter();

  const accessToken = accessTokenState;
  const user = ref<UserRead | null>(null);
  const isLoading = ref(false);
  const restorePromise = ref<Promise<boolean> | null>(null);

  const isAuthenticated = computed(() => !!accessToken.value);

  function clearSession() {
    accessToken.value = null;
    user.value = null;
    setAccessTokenValue(null);
  }

  async function restoreSession(): Promise<boolean> {
    if (restorePromise.value) return restorePromise.value;

    restorePromise.value = (async () => {
      if (accessToken.value && !user.value) {
        try {
          await fetchUser();
          return true;
        } catch {
          clearSession();
        }
      }

      if (accessToken.value && user.value) {
        return true;
      }

      try {
        const response = await apiClient.auth.refreshJwtApiAuthRefreshPost();
        if (!response.accessToken) {
          clearSession();
          return false;
        }

        setAccessToken(response.accessToken);
        await fetchUser();
        return true;
      } catch {
        clearSession();
        return false;
      } finally {
        restorePromise.value = null;
      }
    })();

    return restorePromise.value;
  }

  async function initAuth() {
    await restoreSession();
  }

  async function login(credentials: Body_login_for_access_token_api_auth_login_post) {
    isLoading.value = true;
    try {
      const response = await apiClient.auth.loginForAccessTokenApiAuthLoginPost(credentials);

      if (response.accessToken) {
        setAccessToken(response.accessToken);
        await fetchUser();

        const pendingInvite = sessionStorage.getItem('pendingInviteToken');
        if (pendingInvite) {
          sessionStorage.removeItem('pendingInviteToken');
          await router.push(`/invite/${pendingInvite}`);
          return true;
        }

        await router.push('/projects');
        return true;
      }
      return false;
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function register(payload: RegistrationRequest) {
    isLoading.value = true;
    try {
      await apiClient.registration.registerApiRegistrationPost(payload);
      sessionStorage.setItem('registrationEmail', payload.email);
      sessionStorage.setItem('registrationResendAllowedAt', String(Date.now() + 60_000));
      return true;
    } catch (error) {
      console.error('Registration failed:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function resendVerification(email: string) {
    isLoading.value = true;
    try {
      await apiClient.registration.resendVerificationApiRegistrationResendPost({ email });
      sessionStorage.setItem('registrationEmail', email);
      sessionStorage.setItem('registrationResendAllowedAt', String(Date.now() + 60_000));
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchUser() {
    isLoading.value = true;
    try {
      user.value = await apiClient.users.readUsersMeApiUsersMeGet();
    } catch (error) {
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function updateProfile(payload: UserUpdate) {
    isLoading.value = true;
    try {
      user.value = await apiClient.users.updateUserMeApiUsersMePatch(payload);
    } catch (error) {
      console.error('Failed to update profile:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function updatePassword(payload: UserPasswordUpdate) {
    isLoading.value = true;
    try {
      user.value = await apiClient.users.updateUserPasswordApiUsersMePasswordPatch(payload);
    } catch (error) {
      console.error('Failed to update password:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function uploadAvatar(file: File) {
    isLoading.value = true;
    try {
      user.value = await apiClient.users.uploadAvatarApiUsersMeAvatarPost({
        file: file
      });
    } catch (error) {
      console.error('Failed to upload avatar:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function deleteAvatar(): Promise<void> {
    isLoading.value = true;
    try {
      user.value = await apiClient.users.deleteAvatarApiUsersMeAvatarDelete();
    } catch (error) {
      console.error('Failed to delete avatar:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function logout() {
    try {
      await apiClient.auth.logoutApiAuthLogoutPost();
    } catch (e) {
      console.warn('Logout request failed', e);
    } finally {
      clearSession();
      await router.push('/login');
    }
  }

  function setAccessToken(access: string) {
    accessToken.value = access;
    setAccessTokenValue(access);
  }

  return {
    accessToken,
    user,
    isLoading,
    isAuthenticated,
    login,
    register,
    resendVerification,
    logout,
    fetchUser,
    initAuth,
    restoreSession,
    setAccessToken,
    updateProfile,
    updatePassword,
    uploadAvatar,
    deleteAvatar,
  };
});
