import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PantryService, PlanView, PlansService, ShoppingLineView } from '@api';
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

  protected readonly inTheBasket = computed(() => this.lines().filter((line) => line.bought));

  /** Whether a shop is being unpacked or a list is being emptied. */
  protected readonly stowing = signal(false);
  protected readonly stowFailed = signal(false);

  protected readonly forWeek = computed(() => {
    const plan = this.plan();
    return plan === null ? '' : period(plan.starts_on, plan.ends_on);
  });

  private readonly plans = inject(PlansService);
  private readonly pantry = inject(PantryService);

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

  /**
   * Put what was bought on the shelf (S3).
   *
   * One lot per ticked line, with the quantity the line carries rather than one parsed
   * back out of "200 g" — the server sends both halves for exactly this. Each line is
   * unticked once its lot exists, so an interrupted unpack leaves the basket
   * holding the things that are still in a bag rather than a list that lies either way.
   *
   * No date. A shopping list does not know when anything goes off, and a use-by invented
   * here would be a use-by nobody wrote — the lot page is where a cook adds it.
   */
  protected stow(): void {
    this.putAway(true);
  }

  /** Empty the basket without stocking anything (S4). */
  protected clearBasket(): void {
    this.putAway(false);
  }

  private putAway(toTheShelf: boolean): void {
    const plan = this.plan();
    if (plan === null || this.stowing()) {
      return;
    }
    this.stowing.set(true);
    this.stowFailed.set(false);
    const queue = [...this.inTheBasket()];

    const next = (): void => {
      const line = queue.shift();
      if (line === undefined) {
        this.stowing.set(false);
        return;
      }
      const untick = (): void =>
        void this.plans.markBought(plan.id, line.ingredient_id, { bought: false }).subscribe({
          next: (updated) => {
            this.plan.set(updated);
            next();
          },
          error: () => {
            this.stowing.set(false);
            this.stowFailed.set(true);
          },
        });

      if (!toTheShelf) {
        untick();
        return;
      }
      this.pantry
        .receiveStock({
          ingredient_id: line.ingredient_id,
          magnitude: line.magnitude,
          unit: line.unit,
        })
        .subscribe({
          next: untick,
          error: () => {
            this.stowing.set(false);
            this.stowFailed.set(true);
          },
        });
    };
    next();
  }
}
