import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthStore } from './auth.store';

/**
 * Keeps strangers out of the private area.
 *
 * The intended URL travels along as `returnUrl` so that signing in continues where the
 * cook was going, rather than dropping them on the dashboard to navigate again.
 */
export const requireSignedIn: CanActivateFn = (_route, state) => {
  if (inject(AuthStore).isSignedIn()) {
    return true;
  }
  return inject(Router).createUrlTree(['/sign-in'], {
    queryParams: { returnUrl: state.url },
  });
};
