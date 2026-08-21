import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { PlanSummaryView, PlansService } from '@api';
import { period } from '../../core/dates/format';

/** Monday of the week that contains `from`. A week is what a household plans in. */
function mondayOf(from: Date): Date {
  const monday = new Date(from);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function iso(when: Date): string {
  const month = `${when.getMonth() + 1}`.padStart(2, '0');
  const day = `${when.getDate()}`.padStart(2, '0');
  return `${when.getFullYear()}-${month}-${day}`;
}

@Component({
  selector: 'app-plans',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './plans.component.html',
  styleUrl: './plans.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PlansComponent {
  private readonly plans = inject(PlansService);
  private readonly router = inject(Router);

  protected readonly weeks = signal<PlanSummaryView[] | null>(null);
  protected readonly failed = signal(false);
  protected readonly opening = signal(false);

  protected readonly period = period;

  /**
   * Next week, Monday to Sunday, filled in.
   *
   * A cook planning on a Sunday evening is planning the week that starts tomorrow, and a
   * blank pair of date fields is a small puzzle in front of the thing they came to do.
   * Both are editable — this is a starting point, not a decision.
   */
  protected readonly form = inject(FormBuilder).nonNullable.group({
    starts_on: [iso(mondayOf(this.nextWeek())), Validators.required],
    ends_on: [iso(new Date(this.nextWeek().getTime() + 6 * 86_400_000)), Validators.required],
  });

  constructor() {
    this.plans.listPlans().subscribe({
      // An empty list and a failed request look identical unless one of them says so.
      next: (weeks) => this.weeks.set(weeks),
      error: () => this.failed.set(true),
    });
  }

  protected open(): void {
    if (this.form.invalid || this.opening()) {
      return;
    }
    this.opening.set(true);
    this.plans.createPlan(this.form.getRawValue()).subscribe({
      next: (plan) => void this.router.navigateByUrl(`/plans/${plan.id}`),
      error: () => {
        this.opening.set(false);
        this.failed.set(true);
      },
    });
  }

  private nextWeek(): Date {
    const monday = mondayOf(new Date());
    monday.setDate(monday.getDate() + 7);
    return monday;
  }
}
