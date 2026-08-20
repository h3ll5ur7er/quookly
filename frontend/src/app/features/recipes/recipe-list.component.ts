import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { RecipeSummaryView, RecipesService } from '@api';

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
