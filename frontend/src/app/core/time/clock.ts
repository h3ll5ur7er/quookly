import { DestroyRef, Signal, inject, signal } from '@angular/core';

/**
 * A signal that ticks once a second.
 *
 * Everything that counts down reads this rather than keeping its own interval: one timer
 * on the page means one wake-up per second however many timers are showing, and it means
 * they all agree about what time it is.
 *
 * Must be called from an injection context — the interval is cleared with the component
 * that asked for it, so a cook leaving the kitchen screen leaves nothing running.
 */
export function everySecond(): Signal<number> {
  const now = signal(Date.now());
  const handle = setInterval(() => now.set(Date.now()), 1000);
  inject(DestroyRef).onDestroy(() => clearInterval(handle));
  return now.asReadonly();
}
