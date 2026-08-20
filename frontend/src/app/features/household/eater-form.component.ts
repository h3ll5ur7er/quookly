import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  AgeBand,
  Allergen,
  ConstraintView,
  EaterInput,
  EatersService,
  IngredientView,
  IngredientsService,
  Severity,
} from '@api';
import {
  AGE_BANDS,
  ALLERGENS,
  SEVERITIES,
  ageBandLabel,
  allergenLabel,
  constraintLabel,
  severityLabel,
  severityMark,
} from './household.labels';

/** The option that switches the picker from the fourteen classes to a named ingredient. */
const SOMETHING_ELSE = 'ingredient';

@Component({
  selector: 'app-eater-form',
  imports: [ReactiveFormsModule],
  templateUrl: './eater-form.component.html',
  styleUrl: './eater-form.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EaterFormComponent {
  private readonly eaters = inject(EatersService);
  private readonly ingredients = inject(IngredientsService);
  private readonly router = inject(Router);

  private readonly parameter = inject(ActivatedRoute).snapshot.paramMap.get('id');
  /**
   * Null while adding somebody new; an id while correcting somebody already there.
   *
   * Absent as well as `new`, because `/household/new` is its own route and carries no
   * parameter at all. Reading that as an id asks the API for eater zero, which does not
   * exist, and the add form becomes "that person is not in your household".
   */
  protected readonly eaterId =
    this.parameter === null || this.parameter === 'new' || !Number.isFinite(Number(this.parameter))
      ? null
      : Number(this.parameter);

  protected readonly ageBands = AGE_BANDS;
  protected readonly allergens = ALLERGENS;
  protected readonly severities = SEVERITIES;
  protected readonly somethingElse = SOMETHING_ELSE;

  protected readonly ageBandLabel = ageBandLabel;
  protected readonly allergenLabel = allergenLabel;
  protected readonly constraintLabel = constraintLabel;
  protected readonly severityLabel = severityLabel;
  protected readonly severityMark = severityMark;

  protected readonly constraints = signal<ConstraintView[]>([]);
  protected readonly matches = signal<IngredientView[]>([]);
  protected readonly saving = signal(false);
  protected readonly failed = signal(false);
  protected readonly missing = signal(false);
  protected readonly unmatched = signal(false);
  protected readonly loaded = signal(false);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(100)]],
    age_band: [AgeBand.adult, Validators.required],
    appetite: ['1', [Validators.required, Validators.pattern(/^\d*\.?\d+$/)]],
  });

  /** The constraint being built, kept apart from the person's own fields. */
  protected readonly addition = inject(FormBuilder).nonNullable.group({
    avoids: [String(Allergen.gluten), Validators.required],
    ingredient: [''],
    severity: [Severity.medical, Validators.required],
  });

  protected readonly namingAnIngredient = signal(false);

  protected readonly heading = computed(() =>
    this.eaterId === null
      ? $localize`:@@eaterFormAdd:Add someone`
      : $localize`:@@eaterFormEdit:Edit`,
  );

  constructor() {
    if (this.eaterId === null) {
      this.loaded.set(true);
      return;
    }
    this.eaters.getEater(this.eaterId).subscribe({
      next: (eater) => {
        this.form.setValue({
          name: eater.name,
          age_band: eater.age_band,
          appetite: eater.appetite,
        });
        this.constraints.set(eater.constraints);
        this.loaded.set(true);
      },
      error: () => this.missing.set(true),
    });
  }

  protected onAvoidsChange(value: string): void {
    this.namingAnIngredient.set(value === SOMETHING_ELSE);
    this.unmatched.set(false);
  }

  /** Look up what the cook is typing, so a constraint names a registry entry. */
  protected onIngredientInput(event: Event): void {
    const term = (event.target as HTMLInputElement).value.trim();
    this.unmatched.set(false);
    if (term.length < 2) {
      this.matches.set([]);
      return;
    }
    this.ingredients.searchIngredients(term).subscribe({
      next: (found) => this.matches.set(found),
      error: () => this.matches.set([]),
    });
  }

  /**
   * Add the constraint being built to the list.
   *
   * An ingredient has to resolve to a registry entry. `SuitabilityEngine` matches a
   * constraint to a recipe line by slug, so a typed name that matches nothing produces a
   * constraint that silently never fires — which reads on screen as protection and is
   * the opposite of it.
   */
  protected addConstraint(): void {
    const { avoids, ingredient, severity } = this.addition.getRawValue();

    if (avoids !== SOMETHING_ELSE) {
      this.append({ allergen: avoids as Allergen, ingredient_slug: null, severity });
      return;
    }

    const typed = ingredient.trim().toLowerCase();
    const match = this.matches().find((entry) => entry.name.toLowerCase() === typed);
    if (!match) {
      this.unmatched.set(true);
      return;
    }
    this.append({ allergen: null, ingredient_slug: match.slug, severity });
  }

  protected removeConstraint(index: number): void {
    this.constraints.update((existing) => existing.filter((_, at) => at !== index));
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(false);

    const submitted: EaterInput = {
      ...this.form.getRawValue(),
      constraints: this.constraints(),
    };
    const request =
      this.eaterId === null
        ? this.eaters.createEater(submitted)
        : this.eaters.replaceEater(this.eaterId, submitted);

    request.subscribe({
      next: () => void this.router.navigateByUrl('/household'),
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }

  protected remove(): void {
    if (this.eaterId === null) {
      return;
    }
    this.eaters.deleteEater(this.eaterId).subscribe({
      next: () => void this.router.navigateByUrl('/household'),
      error: () => this.failed.set(true),
    });
  }

  private append(constraint: ConstraintView): void {
    this.unmatched.set(false);
    this.constraints.update((existing) => [...existing, constraint]);
    this.addition.patchValue({ ingredient: '' });
    this.matches.set([]);
  }
}
