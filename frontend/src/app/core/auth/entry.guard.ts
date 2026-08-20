import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AccountsService } from '@api';
import { catchError, map, of } from 'rxjs';
import { AuthStore } from './auth.store';

/**
 * Sends a visitor to the right front door.
 *
 * A fresh instance has no accounts and must be claimed before anyone can sign in; a
 * claimed one must not offer the bootstrap form to the next passer-by. Both questions
 * are answered by the same call, so the guard is written once and inverted.
 */
function entryGuard(whenBootstrapRequired: string, otherwise: string): CanActivateFn {
  return () => {
    const router = inject(Router);
    const auth = inject(AuthStore);

    if (auth.isSignedIn()) {
      return router.createUrlTree(['/dashboard']);
    }

    return inject(AccountsService).getBootstrapState().pipe(
      map((state) => {
        const target = state.required ? whenBootstrapRequired : otherwise;
        return target === '' ? true : router.createUrlTree([target]);
      }),
      // If the instance cannot be asked, let the page render. A network blip should not
      // strand someone on a blank screen with nothing to try.
      catchError(() => of(true)),
    );
  };
}

/** On the sign-in page: divert to the bootstrap form if the instance is unclaimed. */
export const requireClaimedInstance = entryGuard('/bootstrap', '');

/** On the bootstrap page: divert to sign-in if the instance is already claimed. */
export const requireUnclaimedInstance = entryGuard('', '/sign-in');
