import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { SetupService } from '@api';
import { AuthStore } from '../auth/auth.store';
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
    :host {
      display: block;
    }

    /* A fixed label column, so two of these stacked line their labels and their selects up
       with each other. They were two inline rows of different widths with their labels at
       different x positions, which is what made them read as adrift (Y2). */
    .picker {
      display: grid;
      grid-template-columns: 4.5rem minmax(0, 1fr);
      align-items: center;
      gap: var(--space-3);
      font-size: var(--text-sm);
      color: var(--on-surface-muted);
    }

    .picker__select {
      inline-size: 100%;
      min-height: 44px;
      padding: var(--space-2) var(--space-3);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-md);
      background: var(--surface-raised);
      color: var(--on-surface);
      font: inherit;
      font-size: var(--text-md);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LocalePickerComponent {
  private readonly auth = inject(AuthStore);
  private readonly setup = inject(SetupService);

  protected readonly locales = LOCALES;
  protected readonly current = preferredLocale();

  /**
   * Catalogues load once before bootstrap, so a change takes effect on reload (ADR-025).
   * Reloading immediately is clearer than leaving the page in the old language with a
   * new value in the picker.
   *
   * A signed-in cook also has the choice kept on their account, so it follows them to
   * their next device. The reload happens either way: a language that failed to save
   * should still take effect here rather than leaving the picker apparently stuck.
   */
  protected pick(event: Event): void {
    const chosen = (event.target as HTMLSelectElement).value;
    if (chosen === this.current) {
      return;
    }
    storeLocale(chosen);
    if (!this.auth.isSignedIn()) {
      location.reload();
      return;
    }
    this.setup.chooseLocale({ locale: chosen }).subscribe({
      next: () => location.reload(),
      error: () => location.reload(),
    });
  }
}
