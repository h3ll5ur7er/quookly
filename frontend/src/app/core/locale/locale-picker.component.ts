import { ChangeDetectionStrategy, Component } from '@angular/core';
import { LOCALES, preferredLocale, storeLocale } from './locale.store';

@Component({
  selector: 'app-locale-picker',
  template: `
    <label class="picker">
      <span class="picker__label" i18n="@@localePickerLabel">Language</span>
      <select
        class="picker__select"
        [value]="current"
        (change)="pick($event)"
        i18n-aria-label="@@localePickerAriaLabel"
        aria-label="Language"
      >
        @for (locale of locales; track locale.id) {
          <option [value]="locale.id">{{ locale.label }}</option>
        }
      </select>
    </label>
  `,
  styles: `
    .picker {
      display: inline-flex;
      align-items: center;
      gap: var(--space-2);
      font-size: var(--text-sm);
      color: var(--on-surface-muted);
    }

    .picker__select {
      min-height: 44px;
      padding: var(--space-2) var(--space-3);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background: var(--surface-raised);
      color: var(--on-surface);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LocalePickerComponent {
  protected readonly locales = LOCALES;
  protected readonly current = preferredLocale();

  /**
   * Catalogues load once before bootstrap, so a change takes effect on reload (ADR-025).
   * Reloading immediately is clearer than leaving the page in the old language with a
   * new value in the picker.
   */
  protected pick(event: Event): void {
    const chosen = (event.target as HTMLSelectElement).value;
    if (chosen === this.current) {
      return;
    }
    storeLocale(chosen);
    location.reload();
  }
}
