import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { THEME_STORAGE_KEY, ThemeStore } from './theme.store';

/** jsdom has no matchMedia, so tests supply one and assert the fallback when it is absent. */
function systemPrefersDark(dark: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: dark && query.includes('dark'),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

function withoutMatchMedia(): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: undefined,
  });
}

function store(): ThemeStore {
  return TestBed.inject(ThemeStore);
}

describe('ThemeStore', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    systemPrefersDark(false);
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  describe('following the system', () => {
    it('follows the system until the cook chooses', () => {
      expect(store().preference()).toBe('system');
    });

    it('resolves to light when the system prefers light', () => {
      expect(store().resolved()).toBe('light');
    });

    it('resolves to dark when the system prefers dark', () => {
      systemPrefersDark(true);
      expect(store().resolved()).toBe('dark');
    });

    it('falls back to light where the preference cannot be read', () => {
      withoutMatchMedia();
      expect(store().resolved()).toBe('light');
    });
  });

  describe('choosing a theme', () => {
    it('resolves to the chosen theme', () => {
      const theme = store();
      theme.choose('playful');
      expect(theme.resolved()).toBe('playful');
    });

    it('applies the theme to the document', () => {
      store().choose('decorative');
      TestBed.tick();
      expect(document.documentElement.getAttribute('data-theme')).toBe('decorative');
    });

    it('applies the resolved theme without being asked', () => {
      systemPrefersDark(true);
      store();
      TestBed.tick();
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    });

    it('remembers the choice', () => {
      store().choose('dark');
      TestBed.resetTestingModule();
      expect(store().preference()).toBe('dark');
    });

    it('can go back to following the system', () => {
      const theme = store();
      theme.choose('playful');
      theme.choose('system');
      expect(theme.resolved()).toBe('light');
      systemPrefersDark(true);
      TestBed.resetTestingModule();
      expect(store().resolved()).toBe('dark');
    });
  });

  describe('when stored data is unusable', () => {
    it('ignores a theme that no longer exists', () => {
      localStorage.setItem(THEME_STORAGE_KEY, 'neon-1998');
      expect(store().preference()).toBe('system');
    });
  });

  describe('the browser chrome', () => {
    function themeColour(): string | null {
      return document.querySelector('meta[name="theme-color"]')?.getAttribute('content') ?? null;
    }

    beforeEach(() => {
      document.head.querySelector('meta[name="theme-color"]')?.remove();
      const meta = document.createElement('meta');
      meta.setAttribute('name', 'theme-color');
      meta.setAttribute('content', '#000000');
      document.head.appendChild(meta);
      document.documentElement.style.removeProperty('--surface');
    });

    it('follows the theme surface so the chrome matches the page', () => {
      document.documentElement.style.setProperty('--surface', '#123456');
      store().choose('dark');
      TestBed.tick();
      expect(themeColour()).toBe('#123456');
    });

    it('leaves the markup default alone when no surface can be read', () => {
      store().choose('dark');
      TestBed.tick();
      expect(themeColour()).toBe('#000000');
    });
  });

  describe('what is offered', () => {
    it('lists the shipped themes for a picker to render', () => {
      expect(store().available.map((t) => t.id)).toEqual([
        'system',
        'light',
        'dark',
        'playful',
        'decorative',
      ]);
    });

    it('gives every theme a label worth showing', () => {
      for (const theme of store().available) {
        expect(theme.label.length).toBeGreaterThan(0);
      }
    });
  });
});
