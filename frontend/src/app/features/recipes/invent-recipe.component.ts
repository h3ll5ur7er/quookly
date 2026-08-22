import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Freshness, PantryEntry, PantryService, RecipesService, VerdictView } from '@api';
import { VerdictComponent } from '../../core/dietary/verdict.component';

/**
 * Asking for a recipe that does not exist yet (UC-1.4, UC-1.5).
 *
 * Two things shape this screen, and both are about honesty.
 *
 * It is **slow** — a model writes for the better part of a minute — so the waiting is
 * explained rather than spun at, the same as importing.
 *
 * And it can come back **refused**. A recipe the household cannot eat is not stored, and
 * the reason is shown as a verdict rather than as an error string: "Mira — parmesan" is
 * something a cook can act on, and "that did not work" is not.
 */
@Component({
  selector: 'app-invent-recipe',
  imports: [ReactiveFormsModule, RouterLink, VerdictComponent],
  templateUrl: './invent-recipe.component.html',
  styleUrl: './invent-recipe.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InventRecipeComponent {
  private readonly recipes = inject(RecipesService);
  private readonly router = inject(Router);

  protected readonly working = signal(false);
  protected readonly failure = signal<string | null>(null);
  protected readonly refused = signal<VerdictView | null>(null);

  /** What is on the shelf, so "use this up" is a tap rather than a spelling test. */
  protected readonly stocked = signal<PantryEntry[]>([]);
  protected readonly chosen = signal<ReadonlySet<number>>(new Set());

  protected readonly form = inject(FormBuilder).nonNullable.group({
    description: ['', [Validators.maxLength(500)]],
    serves: [4],
  });

  /** Something to go on: a description, some ingredients, or both. */
  protected readonly ready = computed(
    () => this.description().length > 0 || this.chosen().size > 0,
  );

  private readonly typed = signal('');

  constructor() {
    this.form.controls.description.valueChanges.subscribe((written) =>
      this.typed.set(written.trim()),
    );

    inject(PantryService)
      .listPantry()
      .subscribe({
        next: (entries) => this.stocked.set(entries),
        // A pantry that will not load is not a reason to refuse to write a recipe: a
        // description alone is enough to ask with.
        error: () => this.stocked.set([]),
      });
  }

  private description(): string {
    return this.typed();
  }

  /** Whether this packet is one of the ones worth using up first. */
  protected pressing(entry: PantryEntry): boolean {
    return entry.freshness === Freshness.soon || entry.freshness === Freshness.past;
  }

  protected isChosen(ingredientId: number): boolean {
    return this.chosen().has(ingredientId);
  }

  protected choose(ingredientId: number): void {
    this.chosen.update((current) => {
      const next = new Set(current);
      if (!next.delete(ingredientId)) {
        next.add(ingredientId);
      }
      return next;
    });
  }

  protected submit(): void {
    if (!this.ready() || this.working()) {
      return;
    }
    this.working.set(true);
    this.failure.set(null);
    this.refused.set(null);

    this.recipes
      .generateRecipe({
        description: this.description() || null,
        ingredient_ids: [...this.chosen()],
        serves: this.form.getRawValue().serves,
      })
      .subscribe({
        next: (recipe) => void this.router.navigate(['/recipes', recipe.id]),
        error: (response: HttpErrorResponse) => {
          this.working.set(false);
          const detail: unknown = response.error?.detail;
          // A refusal carries its verdict; everything else carries a sentence. Shown as
          // the API worded it rather than flattened into "that did not work".
          if (detail !== null && typeof detail === 'object' && 'verdict' in detail) {
            const refusal = detail as { message: string; verdict: VerdictView };
            this.refused.set(refusal.verdict);
            this.failure.set(refusal.message);
            return;
          }
          this.failure.set(
            typeof detail === 'string'
              ? detail
              : $localize`:@@inventFailedUnknown:That did not work. Please try again.`,
          );
        },
      });
  }
}
