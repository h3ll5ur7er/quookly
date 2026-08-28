/**
 * Which locale the application runs in.
 *
 * Resolved before bootstrap, because `$localize` catalogues are loaded once and
 * `LOCALE_ID` is fixed for the lifetime of the application (ADR-025). Changing locale
 * therefore reloads.
 *
 * This is deliberately plain functions rather than an injectable: it runs before there is
 * an injector.
 */

export const LOCALE_STORAGE_KEY = 'quookly.locale';

interface LocaleChoice {
  readonly id: string;
  /** Named in its own language — someone looking for their language reads it, not English. */
  readonly label: string;
}

export const LOCALES: readonly LocaleChoice[] = [
  { id: 'en-GB', label: 'English' },
  { id: 'de-CH', label: 'Deutsch' },
  { id: 'fr-CH', label: 'Français' },
];

export const DEFAULT_LOCALE = 'en-GB';

export function isLocale(value: unknown): value is string {
  return typeof value === 'string' && LOCALES.some((locale) => locale.id === value);
}

function storedLocale(): string | null {
  try {
    const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
    return isLocale(stored) ? stored : null;
  } catch {
    return null;
  }
}

/**
 * The locale to run in: a stored choice, else the closest thing the browser asks for.
 *
 * Region is matched first, then language. Someone whose browser says `de-DE` gets `de-CH`
 * — not the same thing, but far closer than falling back to English.
 */
export function preferredLocale(): string {
  const stored = storedLocale();
  if (stored !== null) {
    return stored;
  }
  for (const requested of navigator.languages ?? []) {
    const exact = LOCALES.find((locale) => locale.id === requested);
    if (exact !== undefined) {
      return exact.id;
    }
    const language = requested.split('-')[0];
    const sameLanguage = LOCALES.find((locale) => locale.id.startsWith(`${language}-`));
    if (sameLanguage !== undefined) {
      return sameLanguage.id;
    }
  }
  return DEFAULT_LOCALE;
}

export function storeLocale(locale: string): void {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // The choice holds for this load; it just will not survive a reload.
  }
}

/**
 * Forget the stored choice, so the next load falls back to the browser again.
 *
 * Called when somebody signs out. A household shares a device, and the language on it
 * belongs to the person who chose it rather than to the box: leaving it behind hands the
 * next cook somebody else's language — and hands their *account* that language the first
 * time they sign in without one of their own (L6).
 */
export function forgetLocale(): void {
  try {
    localStorage.removeItem(LOCALE_STORAGE_KEY);
  } catch {
    // Nothing to do. The next load reads whatever is there, which is what it did before.
  }
}
