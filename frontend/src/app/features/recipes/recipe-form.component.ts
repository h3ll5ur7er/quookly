import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  Attention,
  IngredientKind,
  IngredientView,
  IngredientsService,
  PresentedRecipe,
  RecipesService,
} from '@api';
import { debounceTime, distinctUntilChanged } from 'rxjs';
import { unitsFor } from '../../core/measure/units';

/** What a recipe can be measured out in. A subset of what the server accepts. */
const YIELD_UNITS = ['piece', 'serving', 'g', 'kg', 'ml', 'l'] as const;

/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

@Component({
  selector: 'app-recipe-form',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './recipe-form.component.html',
  styleUrl: './recipe-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecipeFormComponent {
  private readonly recipes = inject(RecipesService);
  private readonly ingredients = inject(IngredientsService);
  private readonly forms = inject(FormBuilder);
  private readonly router = inject(Router);

  private readonly parameter = inject(ActivatedRoute).snapshot.paramMap.get('id');
  /**
   * The recipe being corrected, or null while writing a new one.
   *
   * Absent as well as `new`, because `/recipes/new` is its own route and carries no
   * parameter at all — the same trap the eater form documents.
   */
  protected readonly recipeId =
    this.parameter === null || this.parameter === 'new' || !Number.isFinite(Number(this.parameter))
      ? null
      : Number(this.parameter);

  protected readonly missing = signal(false);
  protected readonly failed = signal(false);
  protected readonly incomplete = signal(false);
  protected readonly saving = signal(false);

  protected readonly yieldUnits = YIELD_UNITS;
  protected readonly attentions: readonly Attention[] = [
    Attention.hands_on,
    Attention.waiting,
    Attention.ahead,
  ];

  protected readonly details = this.forms.nonNullable.group({
    title: ['', Validators.required],
    summary: [''],
    yield_magnitude: ['1', Validators.required],
    yield_unit: ['piece'],
    serves: [''],
  });

  protected readonly lines = this.forms.array<ReturnType<typeof this.blankLine>>([]);
  protected readonly steps = this.forms.array<ReturnType<typeof this.blankStep>>([]);

  /** Which line's ingredient search is open, and what it found. */
  protected readonly searchingAt = signal<number | null>(null);
  protected readonly matches = signal<IngredientView[]>([]);
  protected readonly search = new FormControl('', { nonNullable: true });

  protected readonly editing = computed(() => this.recipeId !== null);

  constructor() {
    this.lines.push(this.blankLine());
    this.steps.push(this.blankStep());

    this.search.valueChanges
      .pipe(debounceTime(SETTLE), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe((term) => this.look(term));

    if (this.recipeId !== null) {
      this.recipes.getRecipe(this.recipeId).subscribe({
        next: (recipe) => this.fillFrom(recipe),
        error: (refusal: { status?: number }) =>
          refusal.status === 404 ? this.missing.set(true) : this.failed.set(true),
      });
    }
  }

  private blankLine() {
    return this.forms.nonNullable.group({
      ingredient_id: [0, Validators.min(1)],
      name: [''],
      kind: [IngredientKind.solid],
      magnitude: [''],
      unit: ['g'],
      preparation: [''],
      optional: [false],
    });
  }

  private blankStep() {
    return this.forms.nonNullable.group({
      instruction: ['', Validators.required],
      duration_seconds: [''],
      temperature_celsius: [''],
      attention: [Attention.hands_on],
    });
  }

  /** Fill the form from a recipe as the server presents it. */
  private fillFrom(recipe: PresentedRecipe): void {
    this.details.setValue({
      title: recipe.title,
      summary: recipe.summary ?? '',
      yield_magnitude: recipe.yield_quantity.magnitude,
      yield_unit: recipe.yield_quantity.unit,
      serves: recipe.serves ?? '',
    });

    this.lines.clear();
    for (const line of recipe.lines) {
      const control = this.blankLine();
      control.setValue({
        ingredient_id: line.ingredient_id,
        name: line.ingredient,
        kind: line.ingredient_kind,
        magnitude: line.quantity?.magnitude ?? '',
        unit: line.quantity?.unit ?? 'g',
        preparation: line.preparation ?? '',
        optional: line.optional ?? false,
      });
      this.lines.push(control);
    }
    if (this.lines.length === 0) {
      this.lines.push(this.blankLine());
    }

    this.steps.clear();
    for (const step of recipe.steps) {
      const control = this.blankStep();
      control.setValue({
        // What was stored, not what a cook reads: the two differ when the author linked a
        // word, and filling from the rendered text would delete the link as soon as
        // anything else in the step was corrected.
        instruction: step.written,
        duration_seconds: step.duration_seconds == null ? '' : String(step.duration_seconds),
        temperature_celsius:
          step.temperature_celsius == null ? '' : String(step.temperature_celsius),
        attention: step.attention ?? Attention.hands_on,
      });
      this.steps.push(control);
    }
    if (this.steps.length === 0) {
      this.steps.push(this.blankStep());
    }
  }

  protected unitsForLine(index: number): readonly string[] {
    return unitsFor(this.lines.at(index).getRawValue().kind);
  }

  protected addLine(): void {
    this.lines.push(this.blankLine());
  }

  protected removeLine(index: number): void {
    if (this.lines.length > 1) {
      this.lines.removeAt(index);
    }
  }

  protected addStep(): void {
    this.steps.push(this.blankStep());
  }

  protected removeStep(index: number): void {
    if (this.steps.length > 1) {
      this.steps.removeAt(index);
    }
  }

  /** Open the ingredient search for one line. */
  protected searchAt(index: number): void {
    this.searchingAt.set(index);
    this.matches.set([]);
    this.search.setValue('', { emitEvent: false });
  }

  private look(term: string): void {
    const wanted = term.trim();
    if (!wanted) {
      this.matches.set([]);
      return;
    }
    this.ingredients.searchIngredients(wanted).subscribe({
      next: (found) => this.matches.set(found),
      error: () => this.matches.set([]),
    });
  }

  /** Point a line at a registry entry, and offer the units that entry is measured in. */
  protected choose(found: IngredientView): void {
    const index = this.searchingAt();
    if (index === null) {
      return;
    }
    const line = this.lines.at(index);
    line.patchValue({
      ingredient_id: found.id,
      name: found.name,
      kind: found.kind,
      unit: unitsFor(found.kind)[0],
    });
    this.searchingAt.set(null);
    this.matches.set([]);
  }

  /**
   * Send the recipe.
   *
   * Always the whole thing, whether writing or correcting: lines and steps are ordered
   * collections and the server replaces rather than patches, so a partial body would
   * delete what it left out (ADR-059).
   */
  protected save(): void {
    this.incomplete.set(false);
    this.failed.set(false);

    const named = this.lines.controls.every((line) => line.getRawValue().ingredient_id > 0);
    if (this.details.invalid || this.steps.invalid || !named) {
      this.details.markAllAsTouched();
      this.steps.markAllAsTouched();
      this.incomplete.set(true);
      return;
    }

    const written = this.details.getRawValue();
    const body = {
      title: written.title.trim(),
      summary: written.summary.trim() || null,
      yield_magnitude: written.yield_magnitude,
      yield_unit: written.yield_unit,
      serves: written.serves.trim() || null,
      lines: this.lines.controls.map((line) => {
        const value = line.getRawValue();
        const magnitude = value.magnitude.trim();
        return {
          ingredient_id: value.ingredient_id,
          // Both or neither: "salt, to taste" is a line with no quantity at all, and half
          // a quantity is refused by the server rather than guessed at.
          magnitude: magnitude || null,
          unit: magnitude ? value.unit : null,
          preparation: value.preparation.trim() || null,
          optional: value.optional,
        };
      }),
      steps: this.steps.controls.map((step) => {
        const value = step.getRawValue();
        return {
          instruction: value.instruction.trim(),
          duration_seconds: value.duration_seconds.trim() ? Number(value.duration_seconds) : null,
          temperature_celsius: value.temperature_celsius.trim()
            ? Number(value.temperature_celsius)
            : null,
          attention: value.attention,
        };
      }),
    };

    this.saving.set(true);
    const sent =
      this.recipeId === null
        ? this.recipes.createRecipe(body)
        : this.recipes.amendRecipe(this.recipeId, body);

    sent.subscribe({
      next: (saved) => {
        this.saving.set(false);
        void this.router.navigate(['/recipes', saved.id]);
      },
      // The form keeps what was typed: clearing it would lose the work and leave the cook
      // guessing whether it landed.
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }
}
