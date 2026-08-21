/**
 * The last thing the server said, kept where a dropped connection cannot reach it.
 *
 * Deliberately not the service worker's data cache. That caches by URL, and a URL here
 * answers differently depending on who is asking — two people sharing a tablet would see
 * each other's meals. This is keyed, cleared when anybody signs in or out, and holds only
 * what the cook is actually in the middle of.
 */

const PREFIX = 'quookly.kept.';

/** Remember what the server said. Failing to remember must not fail the request. */
export function keep(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Private browsing, a full store, a disabled one. The screen still works with a
    // connection; it just will not survive losing one.
  }
}

/** What the server last said, if anything, and if it is still readable. */
export function kept<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? null : (JSON.parse(raw) as T);
  } catch {
    return null;
  }
}

/**
 * Forget all of it.
 *
 * Called when anybody signs in or out, because the next person at this device is not
 * necessarily the last one, and half a stranger's dinner is not something to leave lying
 * about in a browser.
 */
export function forgetKept(): void {
  try {
    const keys = Object.keys(localStorage).filter((key) => key.startsWith(PREFIX));
    for (const key of keys) {
      localStorage.removeItem(key);
    }
  } catch {
    // Nothing was kept, then.
  }
}
