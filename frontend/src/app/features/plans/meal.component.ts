import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  CookingService,
  EaterView,
  EatersService,
  Meal,
  PlanView,
  PlansService,
  RecipeSummaryView,
  RecipesService,
  SlotView,
} from '@api';
import { VerdictComponent } from '../../core/dietary/verdict.component';
import { MEALS, mealLabel } from './plan.labels';

/** The value a recipe picker carries when no recipe has been chosen. */
const UNDECIDED = '';

@Component({
  selector: 'app-meal',
  imports: [ReactiveFormsModule, VerdictComponent],
  templateUrl: './meal.component.html',
  styleUrl: './meal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MealComponent {
  private readonly plans = inject(PlansService);
  private readonly cooking = inject(CookingService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute).snapshot;

  protected readonly planId = Number(this.route.paramMap.get('id'));

  protected readonly plan = signal<PlanView | null>(null);
  protected readonly recipes = signal<RecipeSummaryView[]>([]);
  protected readonly household = signal<EaterView[]>([]);
  protected readonly missing = signal(false);
  protected readonly saving = signal(false);
  protected readonly failed = signal(false);

  protected readonly meals = MEALS;
  protected readonly mealLabel = mealLabel;
  protected readonly undecided = UNDECIDED;

  protected readonly attending = signal<number[]>([]);

  /**
   * The dish a recipe sent the cook here with ("add to plan"), if one did.
   *
   * Held rather than only seeded into the form, because the form is refilled every time
   * the day or meal changes. Seeding alone put the picker back to "not decided yet" as
   * soon as the plan arrived, and asked the cook to choose the dish they had just chosen.
   */
  private readonly arrivedWith = this.route.queryParamMap.get('recipe') ?? UNDECIDED;

  protected readonly form = inject(FormBuilder).nonNullable.group({
    on_date: [this.route.queryParamMap.get('on') ?? '', Validators.required],
    meal: [(this.route.queryParamMap.get('meal') as Meal) ?? Meal.dinner, Validators.required],
    recipe_id: [this.arrivedWith],
  });

  /**
   * Which slot the screen is on, mirrored out of the form.
   *
   * A signal rather than read straight from the form, because a reactive form's value is
   * not one: a `computed` over `getRawValue()` is evaluated once and then cached forever,
   * so changing the day would keep showing the day you came from — and *saving* would
   * write to it.
   */
  protected readonly when = signal({
    on: this.form.getRawValue().on_date,
    meal: this.form.getRawValue().meal,
  });

  /**
   * The slot as it already stands, if this day and meal have one.
   *
   * Keyed by day and meal rather than by an id, because that is how the API keys a slot:
   * the same address opens the existing one or makes a new one, and there is no state in
   * which the screen has to decide which of the two it is.
   */
  protected readonly existing = computed<SlotView | null>(() => {
    const plan = this.plan();
    const { on, meal } = this.when();
    if (plan === null || on === '') {
      return null;
    }
    return plan.slots.find((slot) => slot.on_date === on && slot.meal === meal) ?? null;
  });

  protected readonly verdict = computed(() => this.existing()?.suitability ?? null);

  /** A cooked meal is a record, not a plan: nothing about it can be changed. */
  protected readonly cooked = computed(() => this.existing()?.cooked === true);

  constructor() {
    this.plans.getPlan(this.planId).subscribe({
      next: (plan) => {
        this.plan.set(plan);
        if (this.form.getRawValue().on_date === '') {
          this.form.patchValue({ on_date: plan.starts_on });
          this.when.set({ on: plan.starts_on, meal: this.form.getRawValue().meal });
        }
        this.fill();
      },
      error: () => this.missing.set(true),
    });
    // Watched through the form rather than through a DOM `change` handler: a control
    // updates its value on `input`, and a handler on `change` reads whatever the form
    // happened to hold at that moment. This asks the form itself.
    this.form.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => this.moved());

    inject(RecipesService)
      .listRecipes()
      .subscribe({ next: (found) => this.recipes.set(found), error: () => this.recipes.set([]) });
    inject(EatersService)
      .listEaters()
      .subscribe({
        next: (found) => this.household.set(found),
        error: () => this.household.set([]),
      });
  }

  protected isAttending(eaterId: number): boolean {
    return this.attending().includes(eaterId);
  }

  protected toggle(eaterId: number): void {
    this.attending.update((seated) =>
      seated.includes(eaterId) ? seated.filter((one) => one !== eaterId) : [...seated, eaterId],
    );
  }

  protected save(): void {
    // A disabled form reports itself valid, so the cooked case is named rather than
    // left to `invalid` — the screen offers no submit button, but Enter in a field would.
    if (this.cooked() || this.form.invalid || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(false);
    const { on_date, meal, recipe_id } = this.form.getRawValue();
    this.plans
      .placeSlot(this.planId, {
        on_date,
        meal,
        recipe_id: recipe_id === UNDECIDED ? null : Number(recipe_id),
        attendee_ids: this.attending(),
      })
      .subscribe({
        next: () => void this.router.navigateByUrl(`/plans/${this.planId}`),
        error: () => {
          this.saving.set(false);
          this.failed.set(true);
        },
      });
  }

  /**
   * Open cooking mode on this meal (UC-9.1).
   *
   * Starting is idempotent, so a cook who left mid-recipe and tapped this again lands back
   * where they were rather than at the top of a second session.
   */
  protected cookNow(): void {
    const slot = this.existing();
    if (slot === null || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(false);
    this.cooking.startSession({ plan_slot_id: slot.id }).subscribe({
      next: (session) => void this.router.navigateByUrl(`/cook/${session.id}`),
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }

  protected cook(): void {
    const slot = this.existing();
    if (slot === null || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(false);
    this.plans.markCooked(this.planId, slot.id).subscribe({
      next: () => void this.router.navigateByUrl(`/plans/${this.planId}`),
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }

  protected clear(): void {
    const slot = this.existing();
    if (slot === null || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.plans.clearSlot(this.planId, slot.id).subscribe({
      next: () => void this.router.navigateByUrl(`/plans/${this.planId}`),
      error: () => {
        this.saving.set(false);
        this.failed.set(true);
      },
    });
  }

  /** The day or the meal moved, so this is a different slot: take what that one holds
      rather than carrying the last one's guest list onto it. */
  private moved(): void {
    const { on_date, meal } = this.form.getRawValue();
    const showing = this.when();
    if (on_date === showing.on && meal === showing.meal) {
      // Only the recipe changed, and `fill` is what changes it — reacting here would be
      // this method calling itself.
      return;
    }
    this.when.set({ on: on_date, meal });
    this.fill();
  }

  /**
   * Put the form beyond editing, or back within it.
   *
   * The *model*, not a `disabled` attribute on a wrapper: a `fieldset[disabled]` stops a
   * control being used without making the control itself say it is disabled, so the two
   * would disagree — and the form would still submit whatever it held.
   */
  private settleEditability(): void {
    const beyondEditing = this.cooked();
    if (beyondEditing === this.form.disabled) {
      return;
    }
    // Silently: enabling and disabling both fire `valueChanges`, and reacting to that
    // would be this method's own consequence coming back round.
    if (beyondEditing) {
      this.form.disable({ emitEvent: false });
    } else {
      this.form.enable({ emitEvent: false });
    }
  }

  private fill(): void {
    const slot = this.existing();
    this.form.patchValue({
      // A slot that already names a dish wins: the cook is looking at a meal that exists,
      // and what they arrived with was a suggestion for an empty one.
      recipe_id:
        slot?.recipe_id === undefined || slot?.recipe_id === null
          ? this.arrivedWith
          : String(slot.recipe_id),
    });
    this.attending.set(slot === null ? [] : [...slot.attendee_ids]);
    this.settleEditability();
  }
}
