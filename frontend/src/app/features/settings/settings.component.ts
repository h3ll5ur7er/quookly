import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  InferenceStatusView,
  IngredientKind,
  InstanceService,
  PreferencesService,
  UnitPreferenceView,
} from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { kindsLabel } from '../../core/measure/kinds';
import { unitsFor } from '../../core/measure/units';
import { LocalePickerComponent } from '../../core/locale/locale-picker.component';
import { ThemePickerComponent } from '../../core/theme/theme-picker.component';

@Component({
  selector: 'app-settings',
  imports: [LocalePickerComponent, RouterLink, ThemePickerComponent],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsComponent {
  private readonly preferences = inject(PreferencesService);

  private readonly auth = inject(AuthStore);
  private readonly router = inject(Router);

  protected readonly name = computed(() => this.auth.cook()?.display_name ?? '');
  protected readonly email = computed(() => this.auth.cook()?.email ?? '');
  protected readonly initial = computed(() => this.name().trim().charAt(0).toUpperCase());

  /**
   * Leave.
   *
   * Navigated afterwards rather than left where they were: a signed-out cook standing on
   * their own pantry would see it empty and read that as the pantry rather than as the
   * signing out.
   *
   * Loaded rather than routed, because signing out gives the device its own language back
   * and catalogues are fixed for the life of the application (ADR-025, L6). Routing would
   * leave the sign-in screen in the language of whoever just left — which is the next
   * cook's first impression of an application that is supposed to follow their account.
   */
  protected signOut(): void {
    this.auth.signOut();
    location.assign('/sign-in');
  }

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

  /** The plural form: this list is about all the powders, not one of them. */
  protected readonly kindLabel = kindsLabel;

  protected optionsFor(kind: IngredientKind): readonly string[] {
    return unitsFor(kind);
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
