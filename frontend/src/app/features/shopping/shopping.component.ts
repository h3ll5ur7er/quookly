import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PlanView, PlansService } from '@api';
import { period } from '../../core/dates/format';

/**
 * What is still to buy (UC-4.4).
 *
 * Its own screen because of where it is used. A cook holding a basket has one hand and
 * thirty seconds, so this opens on the list itself — no week to choose, no plan to scroll
 * past — and the lines are set large enough to read at arm's length in a shop.
 *
 * Derived from the plan's reservations rather than computed here, so the list and the week
 * cannot come to disagree about the same butter (FR-7).
 */
@Component({
  selector: 'app-shopping',
  imports: [RouterLink],
  templateUrl: './shopping.component.html',
  styleUrl: './shopping.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShoppingComponent {
  protected readonly plan = signal<PlanView | null>(null);
  protected readonly loaded = signal(false);
  protected readonly failed = signal(false);

  protected readonly lines = computed(() => this.plan()?.shopping ?? []);

  protected readonly forWeek = computed(() => {
    const plan = this.plan();
    return plan === null ? '' : period(plan.starts_on, plan.ends_on);
  });

  constructor() {
    inject(PlansService)
      .currentPlan()
      .subscribe({
        next: (plan) => {
          this.plan.set(plan);
          this.loaded.set(true);
        },
        // An empty list and a failed request look identical unless one of them says so,
        // and "you have nothing to buy" is a bad thing to tell somebody untruthfully.
        error: () => {
          this.failed.set(true);
          this.loaded.set(true);
        },
      });
  }
}
