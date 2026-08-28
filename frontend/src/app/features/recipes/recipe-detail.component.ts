import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subject, switchMap } from 'rxjs';
import {
  CookingService,
  PlansService,
  PresentedLine,
  PresentedRecipe,
  PresentedStep,
  RecipesService,
  VerdictView,
} from '@api';
import { PictureComponent } from '../../core/media/picture.component';
import { VerdictComponent } from '../../core/dietary/verdict.component';
import { marked } from '../../core/academy/marked';
import { NutritionComponent } from '../../core/nutrition/nutrition.component';
import { minutes } from '../../core/time/duration';
import { attentionNote } from '../../core/time/labels';
import { TimingComponent } from '../../core/time/timing.component';

@Component({
  selector: 'app-recipe-detail',
  imports: [
    PictureComponent,
    NutritionComponent,
    ReactiveFormsModule,
    RouterLink,
    TimingComponent,
    VerdictComponent,
  ],
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

  /** Acting on the dish rather than reading it: cooking it now, or putting it on a week. */
  private readonly cooking = inject(CookingService);
  private readonly plans = inject(PlansService);
  protected readonly leaving = signal(false);
  /**
   * Whether the cook has asked to put this recipe away and not yet confirmed.
   *
   * Two steps because archiving takes a recipe out of the list and out of search, and the
   * control sits beside ones that do not — a mis-tap should not disappear something.
   */
  protected readonly archiving = signal(false);
  protected readonly archiveFailed = signal(false);

  /** Putting a picture of the dish on it (X4). */
  protected readonly illustrating = signal(false);
  protected readonly chosen = signal<File | null>(null);
  protected readonly describing = new FormControl('', { nonNullable: true });
  protected readonly pictureFailed = signal(false);

  /**
   * Whether this recipe is the reader's to change.
   *
   * A recipe belongs to the cook who wrote it, and another cook's is absent rather than
   * forbidden — so anything that comes back is theirs. Kept as a name rather than a bare
   * `true` because it is what the template is asking.
   */
  protected readonly mine = computed(() => this.recipe() !== null);
  protected readonly wontStart = signal(false);
  protected readonly varyFailed = signal<string | null>(null);
  protected readonly refused = signal<VerdictView | null>(null);

  private readonly router = inject(Router);

  /** The yield currently shown, for the stepper to work from. */
  protected readonly currentYield = computed(() => {
    const shown = this.recipe();
    return shown ? Number(shown.yield_quantity.magnitude) : 0;
  });

  /**
   * The yield being asked for, as a stream so that only the last answer counts.
   *
   * Each change re-asks the server. Without `switchMap` a dozen quick taps on *More* are
   * a dozen requests racing each other, and a slow early one lands last and overwrites the
   * yield the cook actually asked for. Cancelling is what makes tapping quickly safe.
   */
  private readonly wanted = new Subject<number | null>();

  constructor() {
    this.wanted
      .pipe(
        switchMap((servings) =>
          this.recipes.getRecipe(this.recipeId, servings === null ? undefined : String(servings)),
        ),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (recipe) => {
          this.recipe.set(recipe);
          this.missing.set(false);
        },
        error: () => this.missing.set(true),
      });
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
  /** Cuts an instruction into the words that link and the words that do not. */
  protected readonly marked = marked;

  /** What this step asks of the cook, where that is worth marking. */
  protected note(step: PresentedStep): string | null {
    return attentionNote(step.attention);
  }

  private load(servings: number | null): void {
    // Sent as text, not as a JSON number: the backend holds yields as exact decimals,
    // and a value that has been through a binary float is no longer the one asked for.
    this.wanted.next(servings);
  }

  /**
   * Cook this now (UC-9.1b).
   *
   * The backend puts the meal on the plan and opens a session; this only has to know
   * where to send the cook. A recipe screen that cannot lead to cooking is a recipe
   * screen a cook has to leave and find their way back from.
   */
  cookNow(): void {
    if (this.leaving()) {
      return;
    }
    this.leaving.set(true);
    this.wontStart.set(false);
    this.cooking.startRecipe({ recipe_id: this.recipeId }).subscribe({
      next: (session) => void this.router.navigateByUrl(`/cook/${session.id}`),
      error: () => {
        this.leaving.set(false);
        this.wontStart.set(true);
      },
    });
  }

  /**
   * Put this on the plan (UC-4.2).
   *
   * The meal screen belongs to a plan, so which plan has to be settled first. A cook with
   * no plan yet is sent to make one rather than shown an error: nothing is wrong, there
   * is simply a step in front of the one they asked for.
   */
  addToPlan(): void {
    if (this.leaving()) {
      return;
    }
    this.leaving.set(true);
    this.plans.currentPlan().subscribe({
      next: (plan) =>
        void this.router.navigateByUrl(
          plan ? `/plans/${plan.id}/meal?recipe=${this.recipeId}` : '/plans',
        ),
      error: () => this.leaving.set(false),
    });
  }

  /** Put this recipe away, then go back to the list it has just left. */
  protected archive(): void {
    const held = this.recipe();
    if (held === null) {
      return;
    }
    this.archiveFailed.set(false);
    this.recipes.archiveRecipe(held.id).subscribe({
      next: () => {
        this.archiving.set(false);
        void this.router.navigate(['/recipes']);
      },
      error: () => {
        this.archiving.set(false);
        this.archiveFailed.set(true);
      },
    });
  }

  protected choose(event: Event): void {
    this.chosen.set((event.target as HTMLInputElement).files?.[0] ?? null);
  }

  /** Put the chosen picture on the recipe, and show it. */
  protected illustrate(): void {
    const file = this.chosen();
    const shows = this.describing.value.trim();
    if (file === null || !shows) {
      return;
    }
    this.pictureFailed.set(false);
    this.recipes.illustrateRecipe(this.recipeId, file, shows).subscribe({
      next: (shown) => {
        this.illustrating.set(false);
        this.chosen.set(null);
        this.describing.setValue('');
        this.recipe.set(shown);
      },
      error: () => this.pictureFailed.set(true),
    });
  }

  /** Take it off again. The file stays — collecting orphans is the CLI's. */
  protected removePicture(): void {
    this.pictureFailed.set(false);
    this.recipes.unillustrateRecipe(this.recipeId).subscribe({
      next: (shown) => this.recipe.set(shown),
      error: () => this.pictureFailed.set(true),
    });
  }
}
