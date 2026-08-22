import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PlanView, PlansService, ShoppingLineView } from '@api';
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

  /** How far through the shop a cook is. The useful question there is "am I nearly done". */
  protected readonly got = computed(() => this.lines().filter((line) => line.bought).length);

  protected readonly forWeek = computed(() => {
    const plan = this.plan();
    return plan === null ? '' : period(plan.starts_on, plan.ends_on);
  });

  private readonly plans = inject(PlansService);

  constructor() {
    this.plans.currentPlan().subscribe({
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

  /**
   * Tick a line off, or put it back (UC-4.4).
   *
   * Marked here first and asked afterwards. A shop is where signal is worst, and a
   * checkbox that waits for a round trip before it moves reads as broken — so the cook
   * sees the tick immediately, the answer replaces it when it lands, and a failure puts
   * it back rather than leaving the screen claiming something it does not know.
   */
  protected mark(line: ShoppingLineView, bought: boolean): void {
    const before = this.plan();
    if (before === null) {
      return;
    }
    this.plan.set({
      ...before,
      shopping: before.shopping.map((one) =>
        one.ingredient_id === line.ingredient_id ? { ...one, bought } : one,
      ),
    });
    this.plans.markBought(before.id, line.ingredient_id, { bought }).subscribe({
      next: (plan) => this.plan.set(plan),
      error: () => this.plan.set(before),
    });
  }
}
