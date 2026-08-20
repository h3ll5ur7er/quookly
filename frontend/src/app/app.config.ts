import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { provideApi } from '../api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideApi(window.location.origin),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes)
  ]
};
