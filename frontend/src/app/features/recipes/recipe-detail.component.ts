import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { PresentedLine, PresentedRecipe, PresentedStep, RecipesService, VerdictView } from '@api';
import { VerdictComponent } from '../../core/dietary/verdict.component';
import { NutritionComponent } from '../../core/nutrition/nutrition.component';
import { minutes } from '../../core/time/duration';
import { attentionNote } from '../../core/time/labels';
import { TimingComponent } from '../../core/time/timing.component';

@Component({
  selector: 'app-recipe-detail',
  imports: [NutritionComponent, ReactiveFormsModule, RouterLink, TimingComponent, VerdictComponent],
  templateUrl: './recipe-detail.component.html',
  styleUrl: './recipe-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecipeDetailComponent {
  private readonly recipes = inject(RecipesService);
  private readonly recipeId = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));

  protected readonly recipe = signal<PresentedRecipe | null>(null);
  protected readonly missing = signal(false);
  protected readonly servings = signal<number | null>(null);

  /** Asking for a version of this one (UC-1.7). */
  protected readonly variant = inject(FormBuilder).nonNullable.group({
    change: ['', [Validators.required, Validators.maxLength(300)]],
  });
  protected readonly varying = signal(false);
  protected readonly varyFailed = signal<string | null>(null);
  protected readonly refused = signal<VerdictView | null>(null);

  private readonly router = inject(Router);

  /** The yield currently shown, for the stepper to work from. */
  protected readonly currentYield = computed(() => {
    const shown = this.recipe();
    return shown ? Number(shown.yield_quantity.magnitude) : 0;
  });

  constructor() {
    this.load(null);
  }

  /**
   * Re-ask the backend for the recipe at a different yield.
   *
   * The arithmetic stays on the server: scaling has to agree with unit conversion and
   * rounding, and a second implementation here would drift from the first.
   */
  showFor(servings: number): void {
    if (!Number.isFinite(servings) || servings <= 0) {
      return;
    }
    this.servings.set(servings);
    this.load(servings);
  }

  protected step(by: number): void {
    this.showFor(this.currentYield() + by);
  }

  protected onYieldInput(event: Event): void {
    this.showFor(Number((event.target as HTMLInputElement).value));
  }

  /**
   * The ingredient, carrying the comma that introduces its preparation.
   *
   * Together, because the two are flex items and a long preparation wraps as a whole —
   * which left the comma sitting at the start of the second line, under the name it
   * belongs to.
   */
  protected named(line: PresentedLine): string {
    return line.preparation ? `${line.ingredient},` : line.ingredient;
  }

  /**
   * Ask for a version of this recipe, and go to it.
   *
   * A refusal comes back as a verdict rather than a sentence, for the same reason writing
   * one from nothing does: "Mira — cream" is something a cook can act on, and it is why
   * the version was not kept (ADR-047).
   */
  protected makeVersion(): void {
    if (!this.variant.valid || this.varying()) {
      return;
    }
    this.varying.set(true);
    this.varyFailed.set(null);
    this.refused.set(null);

    this.recipes.varyRecipe(this.recipeId, this.variant.getRawValue()).subscribe({
      next: (made) => void this.router.navigate(['/recipes', made.id]),
      error: (response: HttpErrorResponse) => {
        this.varying.set(false);
        const detail: unknown = response.error?.detail;
        if (detail !== null && typeof detail === 'object' && 'verdict' in detail) {
          const refusal = detail as { message: string; verdict: VerdictView };
          this.refused.set(refusal.verdict);
          this.varyFailed.set(refusal.message);
          return;
        }
        this.varyFailed.set(
          typeof detail === 'string'
            ? detail
            : $localize`:@@recipeVaryFailed:That did not work. Please try again.`,
        );
      },
    });
  }

  /** Seconds are how a timer is stored; minutes are how a cook reads one. */
  protected readonly minutes = minutes;

  /** What this step asks of the cook, where that is worth marking. */
  protected note(step: PresentedStep): string | null {
    return attentionNote(step.attention);
  }

  private load(servings: number | null): void {
    // Sent as text, not as a JSON number: the backend holds yields as exact decimals,
    // and a value that has been through a binary float is no longer the one asked for.
    this.recipes
      .getRecipe(this.recipeId, servings === null ? undefined : String(servings))
      .subscribe({
        next: (recipe) => {
          this.recipe.set(recipe);
          this.missing.set(false);
        },
        error: () => this.missing.set(true),
      });
  }
}
