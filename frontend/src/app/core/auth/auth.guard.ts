import { inject } from '@angular/core';
import { CanActivateFn, CanMatchFn, Router } from '@angular/router';
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

/**
 * Matches only while nobody is signed in.
 *
 * `canMatch` rather than `canActivate`, because this is not "may you enter" but "which of
 * these two screens is at this address": `/` is the landing page to a visitor and the
 * home dashboard to a cook, and a guard that redirected between them would put the app's
 * front door at a URL nobody would type.
 */
export const whileSignedOut: CanMatchFn = () => !inject(AuthStore).isSignedIn();
