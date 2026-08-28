import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PantryEntry, PantryService, PlanView, PlansService, SlotView } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { weekday } from '../../core/dates/format';

/**
 * What is happening now (UC-3.4, UC-4.4, UC-5.2).
 *
 * The screen the application opens on, and the only one whose job is to answer a question
 * nobody typed: *what should I be doing about dinner*. Everything on it is already
 * somewhere else in the app — the point is that a cook should not have to go and look.
 *
 * Ordered by how soon it matters. What is going off is first because it is the only thing
 * here with a deadline; tonight's meal next; the shopping after that; then what to do when
 * none of the three is pressing.
 *
 * Every card is asked whether or not it has an answer. Hiding the empty ones left the
 * ordinary weekday — a shelf with something on it and nothing planned — as one card and two
 * thirds of an empty screen, which reads as a page that failed to load (H1).
 */
@Component({
  selector: 'app-home',
  imports: [RouterLink],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent {
  private readonly auth = inject(AuthStore);

  protected readonly name = computed(() => this.auth.cook()?.display_name ?? '');

  protected readonly pressing = signal<PantryEntry[]>([]);
  protected readonly plan = signal<PlanView | null>(null);

  /** Today, as the plan writes it, so a slot can be matched against it. */
  protected readonly today = new Date().toISOString().slice(0, 10);

  protected readonly tonight = computed<SlotView[]>(() =>
    (this.plan()?.slots ?? []).filter((slot) => slot.on_date === this.today && slot.recipe_id),
  );

  protected readonly toBuy = computed(() => this.plan()?.shopping.length ?? 0);

  protected readonly weekday = weekday;

  constructor() {
    // Both fail quietly. A home screen that shows an error where the shopping should be is
    // worse than one that shows nothing: nothing is a state a cook understands.
    inject(PantryService)
      .listUsingSoon()
      .subscribe({
        next: (entries) => this.pressing.set(entries),
        error: () => this.pressing.set([]),
      });

    inject(PlansService)
      .currentPlan()
      .subscribe({
        next: (plan) => this.plan.set(plan),
        error: () => this.plan.set(null),
      });
  }

  /** Morning, afternoon or evening — the greeting a person would actually use. */
  protected greeting(): string {
    const hour = new Date().getHours();
    if (hour < 12) {
      return $localize`:@@homeMorning:Good morning`;
    }
    if (hour < 18) {
      return $localize`:@@homeAfternoon:Good afternoon`;
    }
    return $localize`:@@homeEvening:Good evening`;
  }
}
