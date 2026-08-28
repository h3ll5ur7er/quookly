import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { RecipesService, TranslationDraftView } from '@api';

/**
 * Correcting a recipe's translation (ADR-064).
 *
 * A model's German is a starting point; the cook who wrote the recipe knows what it says.
 * Until this screen existed the storage could record that somebody had written a
 * translation and nothing could put one there.
 *
 * Two things make it more than a form. The **author's own words sit beside every field**,
 * because proof-reading a translation without the original in front of you is guessing at
 * it. And a correction of sentences that have since moved is *kept and not shown* — so
 * this screen is the only place those words exist at all, and it has to say so plainly
 * rather than looking like a translation that is live.
 */
@Component({
  selector: 'app-translate-recipe',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './translate-recipe.component.html',
  styleUrl: './translate-recipe.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TranslateRecipeComponent {
  private readonly recipes = inject(RecipesService);
  private readonly forms = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute).snapshot.paramMap;

  protected readonly recipeId = Number(this.route.get('id'));
  private readonly locale = this.route.get('locale') ?? '';

  protected readonly draft = signal<TranslationDraftView | null>(null);
  protected readonly missing = signal(false);
  protected readonly saveFailed = signal(false);
  protected readonly saved = signal(false);

  protected readonly words = this.forms.nonNullable.group({
    title: [''],
    summary: [''],
    steps: this.forms.nonNullable.array<string>([]),
  });

  protected get steps(): FormArray {
    return this.words.controls.steps;
  }

  /** The author's step beside the translated one, paired by position as storage pairs them. */
  protected readonly sourceSteps = computed(() => this.draft()?.source.steps ?? []);

  constructor() {
    this.recipes.getTranslation(this.recipeId, this.locale).subscribe({
      next: (draft) => this.arrived(draft),
      // Nothing to correct is not a failure: a recipe read in its own language has no
      // translation, and neither does one nobody has asked for in another.
      error: () => this.missing.set(true),
    });
  }

  protected save(): void {
    this.saveFailed.set(false);
    this.saved.set(false);
    const form = this.words.getRawValue();
    this.recipes
      .correctTranslation(this.recipeId, this.locale, {
        title: form.title,
        // An empty summary is no summary rather than an empty one: a recipe without one
        // should not gain a blank line by being translated.
        summary: form.summary.trim() || null,
        steps: form.steps,
      })
      .subscribe({
        next: (draft) => {
          this.arrived(draft);
          this.saved.set(true);
        },
        // The form keeps what was typed. Clearing it would lose the correction and leave
        // the cook guessing whether it landed.
        error: () => this.saveFailed.set(true),
      });
  }

  private arrived(draft: TranslationDraftView): void {
    this.draft.set(draft);
    this.steps.clear();
    for (const step of draft.steps) {
      this.steps.push(this.forms.nonNullable.control(step));
    }
    this.words.patchValue({ title: draft.title, summary: draft.summary ?? '' });
  }
}
