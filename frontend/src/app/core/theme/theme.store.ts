import { Injectable, computed, effect, signal } from '@angular/core';

export const THEME_STORAGE_KEY = 'quookly.theme';

/** The themes that exist. Adding one is adding a block to `styles/themes.css` and an entry here. */
export const THEMES = ['light', 'dark', 'playful', 'decorative'] as const;

export type Theme = (typeof THEMES)[number];
export type ThemePreference = Theme | 'system';

interface ThemeChoice {
  readonly id: ThemePreference;
  readonly label: string;
  readonly description: string;
}

const CHOICES: readonly ThemeChoice[] = [
  { id: 'system', label: 'Match my device', description: 'Follows your light or dark setting' },
  { id: 'light', label: 'Light', description: 'Warm and quiet, for a bright kitchen' },
  { id: 'dark', label: 'Dark', description: 'Low glare, for cooking in the evening' },
  { id: 'playful', label: 'Playful', description: 'Bolder colour, rounder edges' },
  { id: 'decorative', label: 'Decorative', description: 'A cookbook feel, set in serif' },
];

function isPreference(value: unknown): value is ThemePreference {
  return value === 'system' || THEMES.includes(value as Theme);
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

/**
 * What the device asks for.
 *
 * Where the preference cannot be read at all — an old browser, a test environment — light
 * is the answer. Guessing dark would be worse: a bright kitchen is the common case.
 */
function systemTheme(): Theme {
  const query = window.matchMedia?.('(prefers-color-scheme: dark)');
  return query?.matches ? 'dark' : 'light';
}

@Injectable({ providedIn: 'root' })
export class ThemeStore {
  private readonly chosen = signal<ThemePreference>(readStoredPreference());
  private readonly system = signal<Theme>(systemTheme());

  readonly available = CHOICES;
  readonly preference = this.chosen.asReadonly();
  readonly resolved = computed<Theme>(() => {
    const preference = this.chosen();
    return preference === 'system' ? this.system() : preference;
  });

  constructor() {
    window
      .matchMedia?.('(prefers-color-scheme: dark)')
      .addEventListener('change', (event) => this.system.set(event.matches ? 'dark' : 'light'));

    effect(() => document.documentElement.setAttribute('data-theme', this.resolved()));
  }

  choose(preference: ThemePreference): void {
    this.chosen.set(preference);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // The choice holds for this tab; it just will not survive a reload.
    }
  }
}
