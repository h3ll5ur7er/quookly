import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Outcome, RecipeSummaryView, RecipesService } from '@api';
import { outcomeBadge } from '../../core/dietary/labels';

@Component({
  selector: 'app-recipe-list',
  imports: [RouterLink],
  templateUrl: './recipe-list.component.html',
  styleUrl: './recipe-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecipeListComponent {
  protected readonly recipes = signal<RecipeSummaryView[] | null>(null);
  protected readonly failed = signal(false);

  protected readonly outcomeBadge = outcomeBadge;
  protected readonly suitable = Outcome.suitable;

  /**
   * Whether anything here was judged at all.
   *
   * A recipe that suits everybody carries no badge — twenty green ticks would drown the
   * one red one, and restraint is what keeps a warning worth reading. That makes an
   * unbadged list ambiguous on its own, so a cook with nobody recorded is told why they
   * are seeing none rather than left to read the silence as approval.
   */
  protected readonly judged = computed(() =>
    (this.recipes() ?? []).some((recipe) => recipe.suitability != null),
  );

  constructor() {
    inject(RecipesService)
      .listRecipes()
      .subscribe({
        next: (recipes) => this.recipes.set(recipes),
        // An empty list and a failed request look identical on screen unless one of them
        // says so, and "you have no recipes" is a bad thing to tell someone untruthfully.
        error: () => this.failed.set(true),
      });
  }
}
