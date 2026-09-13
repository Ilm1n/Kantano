import { isAnalyticsConsentGranted } from '@/shared/consent/consent';
import {
  isAnalyticsRuntimeAllowed,
  isTrustedYandexReplayContext,
} from '@/shared/analytics/replay-context';

declare global {
  interface Window {
    ym?: ((...args: any[]) => void) & { a?: any[]; l?: number };
    [key: string]: unknown;
  }
}

const METRIKA_SCRIPT_SRC = 'https://mc.yandex.ru/metrika/tag.js';
const SCRIPT_ID = 'yandex-metrika-script';
const METRIKA_ID = 107038835;
const ALLOWED_HOSTS = new Set(['kantano.ru']);
const DEBUG_STORAGE_KEY = 'kantano:analytics-debug';

let initialized = false;

function getDisableCounterKey(): string {
  return `disableYaCounter${METRIKA_ID}`;
}

function setCounterDisabled(disabled: boolean): void {
  const key = getDisableCounterKey();
  if (disabled) {
    window[key] = true;
    return;
  }

  // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
  delete window[key];
}

function isProdBuild(): boolean {
  return import.meta.env.PROD;
}

function isHostAllowed(): boolean {
  return ALLOWED_HOSTS.has(window.location.hostname);
}

function isLocalhost(): boolean {
  return window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
}

function isDebugQueryEnabled(): boolean {
  return new URLSearchParams(window.location.search).get('analytics_debug') === '1';
}

function isDebugQueryDisabled(): boolean {
  return new URLSearchParams(window.location.search).get('analytics_debug') === '0';
}

function isDebugStorageEnabled(): boolean {
  return window.localStorage.getItem(DEBUG_STORAGE_KEY) === '1';
}

function persistDebugFlagFromQuery(): void {
  if (!isLocalhost()) return;
  if (isDebugQueryEnabled()) {
    window.localStorage.setItem(DEBUG_STORAGE_KEY, '1');
    return;
  }

  if (isDebugQueryDisabled()) {
    window.localStorage.removeItem(DEBUG_STORAGE_KEY);
  }
}

function isAnalyticsDebugEnabled(): boolean {
  if (!isLocalhost()) return false;
  return isDebugQueryEnabled() || isDebugStorageEnabled();
}

function shouldEnableByEnvironment(): boolean {
  persistDebugFlagFromQuery();
  const isAllowedProdHost = isProdBuild() && isHostAllowed();
  return isAllowedProdHost || isAnalyticsDebugEnabled();
}

function isConsentAllowedNow(): boolean {
  // Allow Yandex replay tools to bootstrap the counter inside their iframe
  // without changing the stored consent requirement for normal visitors.
  return isAnalyticsRuntimeAllowed({
    environmentEnabled: shouldEnableByEnvironment(),
    storedConsentGranted: isAnalyticsConsentGranted(),
    trustedReplayContext: isTrustedYandexReplayContext(),
  });
}

function createYmStub(): void {
  window.ym =
    window.ym ||
    function (...args: any[]) {
      (window.ym!.a = window.ym!.a || []).push(args);
    };
  window.ym.l = Date.now();
}

function createYmNoop(): void {
  window.ym = function () {};
}

function loadMetrikaScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById(SCRIPT_ID)) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = METRIKA_SCRIPT_SRC;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error('Failed to load Yandex Metrika script'));
    document.head.appendChild(script);
  });
}

function getDomainCandidates(hostname: string): string[] {
  const parts = hostname.split('.').filter(Boolean);
  const domains = new Set<string>([hostname, `.${hostname}`]);

  for (let i = 0; i < parts.length - 1; i += 1) {
    const domain = parts.slice(i).join('.');
    domains.add(domain);
    domains.add(`.${domain}`);
  }

  return [...domains];
}

function clearCookieByName(name: string): void {
  const domains = getDomainCandidates(window.location.hostname);
  const paths = ['/', '/projects', '/profile', '/invite', window.location.pathname];

  domains.forEach((domain) => {
    paths.forEach((path) => {
      const normalizedPath = path || '/';
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=${normalizedPath}; domain=${domain}; SameSite=Lax`;
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=${normalizedPath}; SameSite=Lax`;
    });
  });
}

function deleteMetrikaCookies(): void {
  const knownNames = ['_ym_uid', '_ym_d', '_ym_isad', '_ym_visorc', '_ym_hostIndex', 'yabs-sid'];
  const dynamicYmNames = document.cookie
    .split(';')
    .map((cookie) => cookie.trim().split('=')[0])
    .filter((name): name is string => typeof name === 'string' && name.length > 0)
    .filter((name) => name.startsWith('_ym'));

  const cookieNames = new Set<string>([...knownNames, ...dynamicYmNames]);
  cookieNames.forEach((name) => clearCookieByName(name));
}

function removeStorageKeysByPrefix(
  storage: Storage,
  prefixes: readonly string[],
): void {
  const keysToRemove: string[] = [];

  for (let i = 0; i < storage.length; i += 1) {
    const key = storage.key(i);
    if (!key) continue;
    if (prefixes.some((prefix) => key.startsWith(prefix))) {
      keysToRemove.push(key);
    }
  }

  keysToRemove.forEach((key) => storage.removeItem(key));
}

function deleteMetrikaStorage(): void {
  const prefixes = ['_ym'];
  removeStorageKeysByPrefix(window.localStorage, prefixes);
  removeStorageKeysByPrefix(window.sessionStorage, prefixes);
}

function disableMetrikaRuntime(): void {
  setCounterDisabled(true);

  const script = document.getElementById(SCRIPT_ID);
  if (script) {
    script.parentNode?.removeChild(script);
  }

  const counterGlobalKey = `yaCounter${METRIKA_ID}`;
  if (counterGlobalKey in window) {
    const counter = window[counterGlobalKey];
    if (counter && typeof (counter as { destruct?: () => void }).destruct === 'function') {
      try {
        (counter as { destruct: () => void }).destruct();
      } catch {
        // no-op: best effort shutdown for metrika runtime
      }
    }
    // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
    delete window[counterGlobalKey];
  }

  if (typeof window.ym === 'function') {
    try {
      window.ym(METRIKA_ID, 'destruct');
    } catch {
      // no-op: command may be unsupported in some metrika versions
    }
  }

  createYmNoop();
  initialized = false;
}

function clearMetrikaSideEffects(): void {
  const hasYmCookies = document.cookie
    .split(';')
    .some((cookie) => cookie.trim().startsWith('_ym'));

  if (!initialized && !isScriptPresent() && !hasYmCookies) {
    setCounterDisabled(true);
    return;
  }

  disableMetrikaRuntime();
  deleteMetrikaCookies();
  deleteMetrikaStorage();
  setTimeout(deleteMetrikaCookies, 250);
  setTimeout(deleteMetrikaCookies, 1000);
  setTimeout(deleteMetrikaCookies, 2500);
  setTimeout(deleteMetrikaStorage, 250);
  setTimeout(deleteMetrikaStorage, 1000);
  setTimeout(deleteMetrikaStorage, 2500);
}

function isScriptPresent(): boolean {
  return !!document.getElementById(SCRIPT_ID);
}

function shouldSkipInitialization(): boolean {
  return initialized || isScriptPresent();
}

export async function ensureAnalyticsState(): Promise<void> {
  if (!isConsentAllowedNow()) {
    clearMetrikaSideEffects();
    return;
  }

  if (shouldSkipInitialization()) return;

  setCounterDisabled(false);
  createYmStub();
  await loadMetrikaScript();

  window.ym?.(METRIKA_ID, 'init', {
    defer: true,
    clickmap: true,
    trackLinks: true,
    accurateTrackBounce: true,
    webvisor: true,
    ecommerce: 'dataLayer',
  });

  initialized = true;
}

export function trackPageView(path: string): boolean {
  if (!initialized || !window.ym || !isConsentAllowedNow()) return false;

  const url = `${window.location.origin}${path}`;
  window.ym(METRIKA_ID, 'hit', url);
  return true;
}
