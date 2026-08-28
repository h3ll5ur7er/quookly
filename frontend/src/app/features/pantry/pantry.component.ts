import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PantryEntry, PantryService, StockLotView } from '@api';
import { preferredLocale } from '../../core/locale/locale.store';
import { band, day, soonest, urgency } from './pantry.labels';

/** How the shelf is ordered: by what wants eating, or by the alphabet. */
type Order = 'urgency' | 'name';

@Component({
  selector: 'app-pantry',
  imports: [RouterLink],
  templateUrl: './pantry.component.html',
  styleUrl: './pantry.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PantryComponent {
  protected readonly shelf = signal<PantryEntry[] | null>(null);
  protected readonly failed = signal(false);

  /**
   * By what wants eating first.
   *
   * The screen exists because food is thrown away by being forgotten, so the default is
   * the order that answers that. The alphabet is one tap away for a cook who came here to
   * find something rather than to use something up.
   *
   * This replaced a "use these soon" strip above the shelf, which printed the same lots a
   * second time — on a shelf with one thing on it, the screen said everything twice (N1).
   * It also asked the server a second question to build that strip; every lot already
   * carries the server's verdict on how near its date is, so the ordering needs no second
   * opinion about the same thing.
   */
  protected readonly order = signal<Order>('urgency');

  protected readonly shown = computed<PantryEntry[]>(() => {
    const shelf = [...(this.shelf() ?? [])];
    const collator = new Intl.Collator(preferredLocale());
    if (this.order() === 'name') {
      return shelf.sort((a, b) => collator.compare(a.name, b.name));
    }
    // Nearest date first, and a packet with no date at all last — it is not pressing and
    // it never becomes pressing. Ties fall back to the alphabet so the order is total.
    return shelf.sort((a, b) => {
      const left = soonest(a);
      const right = soonest(b);
      if (left === right) {
        return collator.compare(a.name, b.name);
      }
      return (left ?? Infinity) - (right ?? Infinity);
    });
  });

  protected readonly urgency = urgency;
  protected readonly band = band;
  protected readonly day = day;

  constructor() {
    inject(PantryService)
      .listPantry()
      .subscribe({
        // An empty pantry and a failed request look identical unless one of them says so,
        // and "you have nothing" is a bad thing to tell somebody untruthfully.
        next: (shelf) => this.shelf.set(shelf),
        error: () => this.failed.set(true),
      });
  }

  protected orderBy(order: Order): void {
    this.order.set(order);
  }

  protected lotBand(lot: StockLotView): string {
    return band(lot);
  }
}
