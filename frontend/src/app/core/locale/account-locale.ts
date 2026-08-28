import { Injectable, inject } from '@angular/core';
import type { Authenticated } from '@api';
import { SetupService } from '@api';
import { isLocale, preferredLocale, storeLocale } from './locale.store';

/**
 * Settling which language to run in, once somebody has signed in.
 *
 * **The account wins.** A household shares a device and often a browser, and a cook whose
 * account is German must read German without anybody reconfiguring an operating system
 * that is not theirs to reconfigure. So the browser's languages are the fallback for
 * somebody who has *no* account — a visitor on the landing page — and nothing else (L6,
 * [ADR-066](../../../../doc/07-decisions.md)).
 *
 * The interesting case is the account with no language recorded at all, which is every
 * account until somebody opens the picker. Left alone, the two halves of the product
 * answer differently for ever: the interface follows the browser and the server falls back
 * to English for ingredient names, so a German screen says "caster sugar". Writing down
 * whatever is being read makes the account the authority it is supposed to be, from the
 * first sign-in rather than from the first visit to Settings.
 */
@Injectable({ providedIn: 'root' })
export class AccountLocale {
  private readonly setup = inject(SetupService);

  /**
   * Bring the device into line with the account.
   *
   * Returns whether the page has to be loaded again for it to take effect: catalogues are
   * fixed for the life of the application (ADR-025), so adopting a language means a
   * reload, and the caller is the one that knows where the cook was going.
   */
  settle(authenticated: Authenticated): boolean {
    const theirs = authenticated.cook.locale;
    if (theirs !== null && theirs !== undefined && theirs !== '') {
      // A language this build has no catalogue for is still a choice somebody made.
      // Overwriting it with the one on whichever device they are at is how a preference
      // quietly disappears.
      if (!isLocale(theirs) || theirs === preferredLocale()) {
        return false;
      }
      storeLocale(theirs);
      return true;
    }

    // No language on the account. Record the one being read, so the server stops
    // answering in a different one from the screen.
    this.setup.chooseLocale({ locale: preferredLocale() }).subscribe({
      // Failing to record it is not a reason to refuse the sign-in. The screen is already
      // in the right language; the next request is the one that would disagree, and the
      // next attempt at this fixes it.
      error: () => undefined,
    });
    return false;
  }
}
