import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ThemePreference, ThemeStore } from './theme.store';

@Component({
  selector: 'app-theme-picker',
  template: `
    <label class="picker">
      <span class="picker__label" i18n="@@themePickerLabel">Theme</span>
      <select
        class="picker__select"
        [value]="theme.preference()"
        (change)="pick($event)"
        i18n-aria-label="@@themePickerAriaLabel"
        aria-label="Colour theme"
      >
        @for (choice of theme.available; track choice.id) {
          <option [value]="choice.id">{{ choice.label }}</option>
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
export class ThemePickerComponent {
  protected readonly theme = inject(ThemeStore);

  protected pick(event: Event): void {
    this.theme.choose((event.target as HTMLSelectElement).value as ThemePreference);
  }
}
