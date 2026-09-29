import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/api/config';
import { setAccessTokenValue } from '@/modules/auth/lib/access-token';
import { streamAssistant } from './api';

vi.mock('@/api/config', () => ({
  apiClient: { auth: { refreshJwtApiAuthRefreshPost: vi.fn() } },
}));
vi.mock('@/api/config/axios-instance', () => ({ API_BASE_URL: '' }));
vi.mock('@/modules/auth/lib/access-token', () => ({
  getAccessToken: () => 'test-token', setAccessTokenValue: vi.fn(),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe('assistant stream transport', () => {
  it('does not restore a token when logout aborts an ongoing refresh', async () => {
    let finish!: (value: { accessToken: string; tokenType: string }) => void;
    vi.mocked(apiClient.auth.refreshJwtApiAuthRefreshPost).mockImplementation(
      () => new Promise((resolve) => { finish = resolve; }) as ReturnType<typeof apiClient.auth.refreshJwtApiAuthRefreshPost>,
    );
    const fetch = vi.fn().mockResolvedValue(new Response('', { status: 401 }));
    vi.stubGlobal('fetch', fetch);
    const controller = new AbortController();
    const sending = streamAssistant(1, 'chat', '/runs', { content: 'Question' }, vi.fn(), controller.signal);
    const rejected = expect(sending).rejects.toMatchObject({ name: 'AbortError' });
    await vi.waitFor(() => expect(finish).toBeDefined());
    controller.abort();
    finish({ accessToken: 'late-token', tokenType: 'bearer' });
    await rejected;
    expect(setAccessTokenValue).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('maps a machine-readable conflict to the shared user message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: { code: 'ASSISTANT_RUN_ACTIVE' } }),
      { status: 409 },
    )));
    await expect(streamAssistant(1, 'chat', '/runs', { content: 'Question' }, vi.fn()))
      .rejects.toThrow('Сначала завершите или подтвердите текущий запрос помощника');
  });
});
