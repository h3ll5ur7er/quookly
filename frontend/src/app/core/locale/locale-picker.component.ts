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
