import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import {
  IngredientKind,
  IngredientView,
  IngredientsService,
  PantryService,
  PreferencesService,
  ReceiveInput,
} from '@api';
import { unitsFor } from '../../core/measure/units';

@Component({
  selector: 'app-receive-stock',
  imports: [ReactiveFormsModule],
  templateUrl: './receive-stock.component.html',
  styleUrl: './receive-stock.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReceiveStockComponent {
  private readonly pantry = inject(PantryService);
  private readonly registry = inject(IngredientsService);
  private readonly router = inject(Router);

  protected readonly matches = signal<IngredientView[]>([]);
  /** The registry entry the typed name resolved to, or nothing. */
  protected readonly chosen = signal<IngredientView | null>(null);
  protected readonly unmatched = signal(false);
  protected readonly saving = signal(false);
  protected readonly failed = signal(false);

  /** The unit this cook reads each kind in, so the picker starts where they think. */
  private readonly preferred = signal<Record<string, string>>({});

  protected readonly units = computed(() => {
    const entry = this.chosen();
    return entry === null ? unitsFor(IngredientKind.solid) : unitsFor(entry.kind);
  });

  protected readonly form = inject(FormBuilder).nonNullable.group({
    ingredient: ['', Validators.required],
    magnitude: ['', [Validators.required, Validators.pattern(/^\d*\.?\d+$/)]],
    unit: ['g', Validators.required],
    expires_on: [''],
    note: ['', Validators.maxLength(200)],
  });

  constructor() {
    inject(PreferencesService)
      .listUnitPreferences()
      .subscribe({
        next: (preferences) =>
          this.preferred.set(Object.fromEntries(preferences.map((one) => [one.kind, one.unit]))),
        // Not worth a message. The defaults are already sensible, and a cook who came
        // here to put the shopping away does not need to hear about a preferences fetch.
        error: () => this.preferred.set({}),
      });
  }

  /** Look up what the cook is typing, so the stock names a registry entry. */
  protected onIngredientInput(event: Event): void {
    const term = (event.target as HTMLInputElement).value.trim();
    this.unmatched.set(false);
    this.chosen.set(null);
    if (term.length < 2) {
      this.matches.set([]);
      return;
    }
    this.registry.searchIngredients(term).subscribe({
      next: (found) => {
        this.matches.set(found);
        this.settle(term);
      },
      error: () => this.matches.set([]),
    });
  }

  /**
   * Once the typed name matches an entry, move the unit picker to that kind.
   *
   * The cook has said what the thing is; the units for flour and for milk are different
   * questions, and offering millilitres of flour is how a picker teaches somebody to
   * stop reading it.
   */
  private settle(term: string): void {
    const match = this.matches().find((entry) => entry.name.toLowerCase() === term.toLowerCase());
    this.chosen.set(match ?? null);
    if (match === undefined) {
      return;
    }
    const wanted = this.preferred()[match.kind];
    const offered = unitsFor(match.kind);
    this.form.patchValue({ unit: offered.includes(wanted) ? wanted : offered[0] });
  }

  protected save(): void {
    if (this.saving()) {
      return;
    }
    const entry = this.chosen();
    if (entry === null) {
      // A name that resolved to nothing would be stock nothing could ever be matched
      // against — invisible to a shopping list, and to the expiry warnings it is here for.
      this.unmatched.set(true);
      return;
    }
    if (this.form.invalid) {
      return;
    }

    const { magnitude, unit, expires_on, note } = this.form.getRawValue();
    const submitted: ReceiveInput = {
      ingredient_id: entry.id,
      magnitude,
      unit,
      // Empty is not a date. An unanswered field must arrive as "no date on the packet",
      // not as a date the server has to make sense of.
      expires_on: expires_on === '' ? null : expires_on,
      note: note.trim() === '' ? null : note.trim(),
    };

    this.saving.set(true);
    this.failed.set(false);
    this.pantry.receiveStock(submitted).subscribe({
      next: () => void this.router.navigateByUrl('/pantry'),
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }
}
