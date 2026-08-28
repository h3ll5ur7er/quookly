import { Injectable, computed, signal } from '@angular/core';
import type { Authenticated, Cook } from '@api';
import { forgetLocale } from '../locale/locale.store';
import { forgetKept } from '../offline/kept';

export const SESSION_STORAGE_KEY = 'quookly.session';

/** Whether a stored value is a session rather than whatever else was under the key. */
function isSession(value: unknown): value is Authenticated {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Partial<Authenticated>;
  return typeof candidate.token === 'string' && typeof candidate.cook?.id === 'number';
}

/**
 * Reads the stored session, if there is a usable one.
 *
 * Storage can fail for reasons that have nothing to do with us — private browsing, a
 * disabled store, a half-written value from an older version. None of those should stop
 * the application loading; they just mean nobody is signed in.
 */
function readStoredSession(): Authenticated | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    return isSession(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthStore {
  private readonly session = signal<Authenticated | null>(readStoredSession());

  readonly cook = computed<Cook | null>(() => this.session()?.cook ?? null);
  readonly token = computed<string | null>(() => this.session()?.token ?? null);
  readonly isSignedIn = computed(() => this.session() !== null);
  readonly isAdmin = computed(() => this.session()?.cook.is_admin === true);

  signIn(authenticated: Authenticated): void {
    // Whatever the last person at this device was in the middle of is not this person's
    // business, and a cooking session kept for offline reading is somebody's dinner.
    forgetKept();
    this.session.set(authenticated);
    this.write(JSON.stringify(authenticated));
  }

  signOut(): void {
    forgetKept();
    // The language belonged to whoever chose it, not to the device (L6). Not forgotten on
    // sign-*in*: the next thing that happens there is settling it from the account, and
    // clearing it first would only make the page flash through the browser's language.
    forgetLocale();
    this.session.set(null);
    this.write(null);
  }

  /** Persisting is a convenience; failing to persist must not fail the sign-in. */
  private write(value: string | null): void {
    try {
      if (value === null) {
        localStorage.removeItem(SESSION_STORAGE_KEY);
      } else {
        localStorage.setItem(SESSION_STORAGE_KEY, value);
      }
    } catch {
      // The session still works for this tab; it just will not survive a reload.
    }
  }
}
