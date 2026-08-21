import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Outcome, PlanView, PlansService, SlotView } from '@api';
import { period, weekday } from '../../core/dates/format';
import { outcomeBadge, worthMarking } from '../../core/dietary/labels';
import { attending, mealLabel, sizingNote } from './plan.labels';

/** One day of the period, with whatever has been put in it. */
interface Day {
  readonly on: string;
  readonly slots: readonly SlotView[];
}

@Component({
  selector: 'app-plan',
  imports: [RouterLink],
  templateUrl: './plan.component.html',
  styleUrl: './plan.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlanComponent {
  private readonly plans = inject(PlansService);
  private readonly router = inject(Router);
  protected readonly planId = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));

  protected readonly plan = signal<PlanView | null>(null);
  protected readonly missing = signal(false);
  protected readonly failed = signal(false);

  protected readonly weekday = weekday;
  protected readonly mealLabel = mealLabel;
  protected readonly sizingNote = sizingNote;
  protected readonly attending = attending;
  protected readonly outcomeBadge = outcomeBadge;

  protected readonly heading = computed(() => {
    const plan = this.plan();
    return plan === null ? '' : period(plan.starts_on, plan.ends_on);
  });

  /**
   * Every day of the period, empty ones included.
   *
   * The gaps are the point. A list of only what is planned reads as a finished week; a
   * row per day shows a cook where Thursday still is. The period is bounded server-side,
   * so this is a month at most.
   */
  protected readonly days = computed<Day[]>(() => {
    const plan = this.plan();
    if (plan === null) {
      return [];
    }
    const days: Day[] = [];
    const last = new Date(`${plan.ends_on}T00:00:00`);
    for (
      const cursor = new Date(`${plan.starts_on}T00:00:00`);
      cursor <= last;
      cursor.setDate(cursor.getDate() + 1)
    ) {
      const on = this.iso(cursor);
      days.push({ on, slots: plan.slots.filter((slot) => slot.on_date === on) });
    }
    return days;
  });

  constructor() {
    this.load();
  }

  protected badge(slot: SlotView): Outcome | null {
    return worthMarking(slot.suitability?.outcome);
  }

  protected discard(): void {
    this.plans.deletePlan(this.planId).subscribe({
      next: () => void this.router.navigateByUrl('/plans'),
      error: () => this.failed.set(true),
    });
  }

  private load(): void {
    this.plans.getPlan(this.planId).subscribe({
      next: (plan) => this.plan.set(plan),
      error: () => this.missing.set(true),
    });
  }

  /** A local calendar day, not an instant: `toISOString` is UTC and shifts the date. */
  private iso(when: Date): string {
    const month = `${when.getMonth() + 1}`.padStart(2, '0');
    const day = `${when.getDate()}`.padStart(2, '0');
    return `${when.getFullYear()}-${month}-${day}`;
  }
}
