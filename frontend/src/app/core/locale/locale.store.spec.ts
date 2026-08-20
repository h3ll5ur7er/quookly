import {
  LOCALES,
  LOCALE_STORAGE_KEY,
  isLocale,
  preferredLocale,
  storeLocale,
} from './locale.store';

function navigatorLanguages(languages: readonly string[]): void {
  Object.defineProperty(window.navigator, 'languages', {
    writable: true,
    configurable: true,
    value: languages,
  });
}

describe('locale', () => {
  beforeEach(() => {
    localStorage.clear();
    navigatorLanguages(['en-GB']);
  });

  describe('what is supported', () => {
    it('ships the three locales promised for v1', () => {
      expect(LOCALES.map((l) => l.id)).toEqual(['en-GB', 'de-CH', 'fr-CH']);
    });

    it('names each one in its own language', () => {
      expect(LOCALES.map((l) => l.label)).toEqual(['English', 'Deutsch', 'Français']);
    });

    it('recognises only the locales that exist', () => {
      expect(isLocale('de-CH')).toBe(true);
      expect(isLocale('de-DE')).toBe(false);
      expect(isLocale(null)).toBe(false);
    });
  });

  describe('choosing without being asked', () => {
    it('uses the browser preference when it is one we ship', () => {
      navigatorLanguages(['de-CH', 'en-GB']);
      expect(preferredLocale()).toBe('de-CH');
    });

    it('matches on language when the region differs', () => {
      // de_CH is not de_DE, but German is closer than defaulting to English.
      navigatorLanguages(['de-DE']);
      expect(preferredLocale()).toBe('de-CH');
    });

    it('takes the first language it can serve, in the browser order', () => {
      navigatorLanguages(['ja-JP', 'fr-FR', 'de-DE']);
      expect(preferredLocale()).toBe('fr-CH');
    });

    it('falls back to English when nothing matches', () => {
      navigatorLanguages(['ja-JP']);
      expect(preferredLocale()).toBe('en-GB');
    });
  });

  describe('remembering a choice', () => {
    it('prefers a stored choice over the browser', () => {
      navigatorLanguages(['de-CH']);
      storeLocale('fr-CH');
      expect(preferredLocale()).toBe('fr-CH');
    });

    it('ignores a stored locale that no longer exists', () => {
      localStorage.setItem(LOCALE_STORAGE_KEY, 'la-VA');
      expect(preferredLocale()).toBe('en-GB');
    });
  });
});
