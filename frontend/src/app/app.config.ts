import { ApplicationConfig, isDevMode, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideServiceWorker } from '@angular/service-worker';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { provideApi } from '../api';
import { authInterceptor } from './core/auth/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideApi(window.location.origin),
    provideHttpClient(withXhr(), withInterceptors([authInterceptor])),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      // Registering once the app is stable keeps the worker off the critical path of a
      // first paint, which matters most on the phone this is designed for.
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
