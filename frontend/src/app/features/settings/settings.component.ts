import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import {
  InferenceStatusView,
  IngredientKind,
  InstanceService,
  PreferencesService,
  UnitPreferenceView,
} from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { LocalePickerComponent } from '../../core/locale/locale-picker.component';

/** The units worth offering per kind. A countable is counted; the rest are measured. */
const UNITS_FOR: Record<string, readonly { value: string; label: string }[]> = {
  [IngredientKind.powder]: [
    { value: 'g', label: 'g' },
    { value: 'kg', label: 'kg' },
    { value: 'oz', label: 'oz' },
    { value: 'lb', label: 'lb' },
  ],
  [IngredientKind.solid]: [
    { value: 'g', label: 'g' },
    { value: 'kg', label: 'kg' },
    { value: 'oz', label: 'oz' },
    { value: 'lb', label: 'lb' },
  ],
  [IngredientKind.liquid]: [
    { value: 'ml', label: 'ml' },
    { value: 'dl', label: 'dl' },
    { value: 'l', label: 'l' },
    { value: 'fl oz (US)', label: 'fl oz (US)' },
  ],
  [IngredientKind.countable]: [{ value: 'piece', label: 'piece' }],
};

@Component({
  selector: 'app-settings',
  imports: [LocalePickerComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent {
  private readonly preferences = inject(PreferencesService);

  protected readonly units = signal<UnitPreferenceView[] | null>(null);
  protected readonly failed = signal(false);

  /** Only an administrator sees the inference section, and only they can act on it. */
  protected readonly isAdmin = inject(AuthStore).isAdmin;
  protected readonly inference = signal<InferenceStatusView | null>(null);

  constructor() {
    this.preferences.listUnitPreferences().subscribe({
      next: (units) => this.units.set(units),
      error: () => this.failed.set(true),
    });

    if (this.isAdmin()) {
      // Its own request and its own failure: a provider that is not answering must not
      // take the units section down with it.
      inject(InstanceService)
        .getInferenceStatus()
        .subscribe({
          next: (status) => this.inference.set(status),
          error: () => this.inference.set(null),
        });
    }
  }

  protected optionsFor(kind: IngredientKind): readonly { value: string; label: string }[] {
    return UNITS_FOR[kind] ?? [];
  }

  protected kindLabel(kind: IngredientKind): string {
    switch (kind) {
      case IngredientKind.powder:
        return $localize`:@@kindPowder:Powders`;
      case IngredientKind.liquid:
        return $localize`:@@kindLiquid:Liquids`;
      case IngredientKind.solid:
        return $localize`:@@kindSolid:Solids`;
      case IngredientKind.countable:
        return $localize`:@@kindCountable:Countable things`;
    }
  }

  protected choose(kind: IngredientKind, event: Event): void {
    const unit = (event.target as HTMLSelectElement).value;
    this.failed.set(false);
    this.preferences.chooseUnit(kind, { unit }).subscribe({
      next: (units) => this.units.set(units),
      error: () => this.failed.set(true),
    });
  }
}
