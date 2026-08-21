import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PresentedLine, PresentedRecipe, PresentedStep, RecipesService } from '@api';
import { VerdictComponent } from '../../core/dietary/verdict.component';
import { minutes } from '../../core/time/duration';
import { attentionNote } from '../../core/time/labels';
import { TimingComponent } from '../../core/time/timing.component';

@Component({
  selector: 'app-recipe-detail',
  imports: [TimingComponent, VerdictComponent],
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
