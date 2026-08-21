import { DestroyRef, inject } from '@angular/core';

/** The bit of `navigator` this needs, without depending on DOM lib versions that vary. */
interface WakeLockCapable {
  wakeLock?: { request(type: 'screen'): Promise<{ release(): Promise<void> }> };
}

/**
 * Hold the screen on for as long as the caller lives (NFR-12).
 *
 * A cook with wet hands cannot tap a phone awake, and a screen that sleeps mid-recipe is
 * the failure cooking mode exists to prevent. The lock is re-acquired when the tab comes
 * back: browsers drop it whenever the page is hidden, so one request at the start would
 * hold until the first time somebody answered a message and no longer.
 *
 * Absent in some browsers, and that is fine — this is a comfort, not a requirement, and a
 * missing API must not take the screen down with it. Must be called from an injection
 * context; the lock is released with the component that asked for it.
 */
export function keepScreenAwake(): void {
  const api = (navigator as Navigator & WakeLockCapable).wakeLock;
  if (api === undefined) {
    return;
  }

  let held: { release(): Promise<void> } | null = null;

  const acquire = (): void => {
    api
      .request('screen')
      .then((lock) => (held = lock))
      // A refused lock is not an error worth showing anybody: the screen dims, which is
      // what would have happened anyway.
      .catch(() => (held = null));
  };

  const onVisible = (): void => {
    if (document.visibilityState === 'visible') {
      acquire();
    }
  };

  acquire();
  document.addEventListener('visibilitychange', onVisible);

  inject(DestroyRef).onDestroy(() => {
    document.removeEventListener('visibilitychange', onVisible);
    void held?.release();
    held = null;
  });
}
