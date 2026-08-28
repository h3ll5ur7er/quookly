import { registerLocaleData } from '@angular/common';
import localeDeCh from '@angular/common/locales/de-CH';
import localeEnGb from '@angular/common/locales/en-GB';
import localeFrCh from '@angular/common/locales/fr-CH';
import { LOCALE_ID } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { loadTranslations } from '@angular/localize';

import { App } from './app/app';
import { appConfig } from './app/app.config';
import { preferredLocale } from './app/core/locale/locale.store';

registerLocaleData(localeEnGb, 'en-GB');
registerLocaleData(localeDeCh, 'de-CH');
registerLocaleData(localeFrCh, 'fr-CH');

interface Catalogue {
  readonly translations: Record<string, string>;
}

/**
 * Load the catalogue before the application starts.
 *
 * `$localize` resolves each message once, so translations must be in place before
 * bootstrap (ADR-025). A missing or unreadable catalogue is not fatal: `$localize` falls
 * back to the source text, which is English — a legible application beats a blank one.
 */
async function loadCatalogue(locale: string): Promise<void> {
  try {
    const response = await fetch(`/i18n/${locale}.json`);
    if (!response.ok) {
      return;
    }
    const catalogue = (await response.json()) as Catalogue;
    loadTranslations(catalogue.translations ?? {});
  } catch {
    // Source text stands.
  }
}

async function start(): Promise<void> {
  const locale = preferredLocale();
  // What the document says it is written in. `index.html` ships `lang="en"` and nothing
  // ever changed it, so a German page told a screen reader to pronounce German as
  // English — and told a translation tool it had nothing to do.
  document.documentElement.lang = locale;
  await loadCatalogue(locale);

  await bootstrapApplication(App, {
    ...appConfig,
    providers: [...appConfig.providers, { provide: LOCALE_ID, useValue: locale }],
  });
}

void start().catch((error: unknown) => console.error(error));
