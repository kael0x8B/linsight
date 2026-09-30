import { afterEach, describe, expect, it, vi } from 'vitest';

import { createQuietRefresh } from './quiet-refresh';

afterEach(() => vi.useRealTimers());
describe('task background refresh', () => {
  it('coalesces lifecycle scheduling and waits for a slow request before polling again', async () => {
    vi.useFakeTimers();
    let resolve!: (value: number) => void;
    const fetch = vi.fn(
      () =>
        new Promise<number>((r) => {
          resolve = r;
        }),
    );
    const apply = vi.fn();
    const loop = createQuietRefresh({
      active: () => true,
      fetch,
      apply,
      onError: vi.fn(),
    });
    loop.schedule();
    loop.schedule();
    loop.schedule();
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetch).toHaveBeenCalledTimes(1);
    loop.schedule();
    await vi.advanceTimersByTimeAsync(20_000);
    expect(fetch).toHaveBeenCalledTimes(1);
    resolve(1);
    await vi.advanceTimersByTimeAsync(0);
    expect(apply).toHaveBeenCalledWith(1);
    await vi.advanceTimersByTimeAsync(4999);
    expect(fetch).toHaveBeenCalledTimes(1);
    loop.stop();
  });
  it('does not repaint or resume while deactivated, hidden or editing', async () => {
    vi.useFakeTimers();
    let active = true;
    let resolve!: (value: number) => void;
    const fetch = vi.fn(
      () =>
        new Promise<number>((r) => {
          resolve = r;
        }),
    );
    const apply = vi.fn();
    const loop = createQuietRefresh({
      active: () => active,
      fetch,
      apply,
      onError: vi.fn(),
    });
    loop.schedule();
    await vi.advanceTimersByTimeAsync(5000);
    active = false;
    loop.stop();
    resolve(1);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(apply).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1);
    active = true;
    loop.schedule();
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetch).toHaveBeenCalledTimes(2);
    loop.stop();
  });
  it('ignores a response invalidated by a manual filter or page change', async () => {
    vi.useFakeTimers();
    let resolve!: (value: string) => void;
    const apply = vi.fn();
    const loop = createQuietRefresh({
      active: () => true,
      fetch: () =>
        new Promise<string>((r) => {
          resolve = r;
        }),
      apply,
      onError: vi.fn(),
    });
    loop.schedule();
    await vi.advanceTimersByTimeAsync(5000);
    loop.stop();
    resolve('previous filter');
    await vi.advanceTimersByTimeAsync(0);
    expect(apply).not.toHaveBeenCalled();
    loop.stop();
  });
});
