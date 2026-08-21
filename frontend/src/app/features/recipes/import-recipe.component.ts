import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { ImportedRecipe, RecipesService, Source } from '@api';

/**
 * Reading a recipe off a web page (UC-1.3) — the founding use case.
 *
 * Two things shape this screen. It is **slow**: a page with no recipe metadata has to be
 * read by a model, which takes the better part of half a minute, so the waiting has to be
 * explained rather than spun at. And it can **fail in ways the cook can act on** — a site
 * that blocks automated readers, a page with no recipe on it, an instance with no model —
 * so the failure is shown as the API worded it rather than flattened into "that did not
 * work".
 */
@Component({
  selector: 'app-import-recipe',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './import-recipe.component.html',
  styleUrl: './import-recipe.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ImportRecipeComponent {
  private readonly recipes = inject(RecipesService);

  protected readonly working = signal(false);
  protected readonly failure = signal<string | null>(null);
  protected readonly outcome = signal<ImportedRecipe | null>(null);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    url: ['', [Validators.required, Validators.pattern(/^https?:\/\/\S+$/i)]],
  });

  /** Whether a model had to read it, which is the slow path and the fallible one. */
  protected readonly readByModel = computed(() => this.outcome()?.read_from === Source.model);

  protected readonly newIngredients = computed(() => this.outcome()?.ingredients_added ?? []);

  protected submit(): void {
    if (this.form.invalid || this.working()) {
      return;
    }
    this.working.set(true);
    this.failure.set(null);
    this.outcome.set(null);

    this.recipes.importRecipeFromUrl(this.form.getRawValue()).subscribe({
      next: (imported) => {
        this.outcome.set(imported);
        this.working.set(false);
        this.form.reset();
      },
      error: (response: HttpErrorResponse) => {
        this.working.set(false);
        // The API writes these for cooks — "that site will not serve an automated reader,
        // but the page works in your browser". Replacing them with something generic
        // would throw away the only part of a failure that is actionable.
        const detail: unknown = response.error?.detail;
        this.failure.set(
          typeof detail === 'string' && detail
            ? detail
            : $localize`:@@importFailedUnknown:That did not work. Please try again.`,
        );
      },
    });
  }
}
