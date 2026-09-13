import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Router } from "vue-router";

const mocks = vi.hoisted(() => ({
  ensure: vi.fn(),
  hit: vi.fn(),
  consent: vi.fn(),
}));
vi.mock("@/shared/analytics/yandex", () => ({
  ensureAnalyticsState: mocks.ensure,
  trackPageView: mocks.hit,
}));
vi.mock("@/shared/consent/consent", () => ({
  onConsentChanged: mocks.consent,
}));

beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
  mocks.ensure.mockResolvedValue(undefined);
  mocks.hit.mockReturnValue(true);
});

describe("analytics bootstrap", () => {
  it("tracks the public document once without a router", async () => {
    const { bootstrapAnalytics } = await import("./bootstrap");
    bootstrapAnalytics();
    bootstrapAnalytics();
    await vi.waitFor(() => expect(mocks.hit).toHaveBeenCalledTimes(1));
    expect(mocks.hit).toHaveBeenCalledWith("/");
  });

  it("does not lose the initial view when consent is granted later", async () => {
    mocks.hit.mockReturnValue(false);
    const { bootstrapAnalytics } = await import("./bootstrap");
    bootstrapAnalytics();
    await vi.waitFor(() => expect(mocks.hit).toHaveBeenCalledTimes(1));
    mocks.hit.mockReturnValue(true);
    mocks.consent.mock.calls[0]![0]();
    await vi.waitFor(() => expect(mocks.hit).toHaveBeenCalledTimes(2));
  });

  it("deduplicates router readiness and initial navigation, then tracks navigation", async () => {
    const afterEach = vi.fn();
    const router = {
      afterEach,
      isReady: () => Promise.resolve(),
      currentRoute: { value: { fullPath: "/projects" } },
    } as unknown as Router;
    const { bootstrapAnalytics } = await import("./bootstrap");
    bootstrapAnalytics(router);
    const navigate = afterEach.mock.calls[0]![0];
    navigate({ fullPath: "/projects" }, {}, undefined);
    await vi.waitFor(() => expect(mocks.hit).toHaveBeenCalledTimes(1));
    navigate({ fullPath: "/profile" }, {}, undefined);
    await vi.waitFor(() => expect(mocks.hit).toHaveBeenCalledTimes(2));
    navigate({ fullPath: "/login" }, {}, new Error("aborted"));
    expect(mocks.hit).toHaveBeenCalledTimes(2);
  });

  it("keeps the page usable when the provider fails", async () => {
    mocks.ensure.mockRejectedValue(new Error("offline"));
    const { bootstrapAnalytics } = await import("./bootstrap");
    bootstrapAnalytics();
    await vi.waitFor(() => expect(mocks.ensure).toHaveBeenCalled());
    expect(mocks.hit).not.toHaveBeenCalled();
  });
});
