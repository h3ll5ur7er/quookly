import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthStore } from './auth.store';

/**
 * Attaches the bearer token to outgoing requests.
 *
 * A header the caller set already is left alone, so a deliberate choice at the call site
 * is never quietly overwritten by this.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const token = inject(AuthStore).token();
  if (token === null || request.headers.has('Authorization')) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};
