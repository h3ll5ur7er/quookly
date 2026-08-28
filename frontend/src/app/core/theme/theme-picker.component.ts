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
export class ThemePickerComponent {
  protected readonly theme = inject(ThemeStore);

  protected pick(event: Event): void {
    this.theme.choose((event.target as HTMLSelectElement).value as ThemePreference);
  }
}
