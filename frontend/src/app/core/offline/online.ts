import { DestroyRef, Signal, inject, signal } from '@angular/core';

/**
 * Whether the browser thinks it can reach anything.
 *
 * `navigator.onLine` is a weak signal — it says the device has *a* network, not that the
 * instance is reachable — so nothing here refuses to try. It is used to explain a failure
 * that has already happened and to know when it is worth retrying, never to decide in
 * advance that a request would fail.
 *
 * Must be called from an injection context; the listeners go with the caller.
 */
export function online(): Signal<boolean> {
  const reachable = signal(navigator.onLine);
  const up = (): void => reachable.set(true);
  const down = (): void => reachable.set(false);

  window.addEventListener('online', up);
  window.addEventListener('offline', down);
  inject(DestroyRef).onDestroy(() => {
    window.removeEventListener('online', up);
    window.removeEventListener('offline', down);
  });

  return reachable.asReadonly();
}

/**
 * Do something when the connection comes back.
 *
 * An event rather than an effect on `online()`, deliberately. An effect would run whenever
 * *either* of its inputs changed — so a request that failed while the browser still
 * believed it was online would be retried the instant it was queued, fail again, and queue
 * again. This fires on the transition and only on the transition.
 *
 * Must be called from an injection context; the listener goes with the caller.
 */
export function whenReconnected(resume: () => void): void {
  window.addEventListener('online', resume);
  inject(DestroyRef).onDestroy(() => window.removeEventListener('online', resume));
}
