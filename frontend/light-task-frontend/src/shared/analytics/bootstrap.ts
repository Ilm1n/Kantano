import type { Router } from "vue-router";

import { onConsentChanged } from "@/shared/consent/consent";
import { ensureAnalyticsState, trackPageView } from "@/shared/analytics/yandex";

let bootstrapped = false;

export function bootstrapAnalytics(router?: Router): void {
  if (bootstrapped) return;
  bootstrapped = true;

  const currentPath = () => window.location.pathname + window.location.search;
  let lastPath: string | null = null;
  const visit = async (path: string): Promise<void> => {
    try {
      await ensureAnalyticsState();
      if (path !== lastPath && trackPageView(path)) lastPath = path;
    } catch {
      // An unavailable analytics provider must not interrupt navigation.
    }
  };

  onConsentChanged(() => {
    lastPath = null;
    void visit(currentPath());
  });

  if (router) {
    router.afterEach((to, _from, failure) => {
      if (!failure) void visit(to.fullPath);
    });
    void router.isReady().then(() => visit(router.currentRoute.value.fullPath));
  } else {
    void visit(currentPath());
  }
}
