import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PantryEntry, PantryService } from '@api';
import { day, urgency } from './pantry.labels';

@Component({
  selector: 'app-pantry',
  imports: [RouterLink],
  templateUrl: './pantry.component.html',
  styleUrl: './pantry.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PantryComponent {
  protected readonly shelf = signal<PantryEntry[] | null>(null);
  /**
   * What wants eating, asked for separately rather than filtered out of the shelf.
   *
   * How near counts as near is a rule, and rules live on the server. A client that
   * decided it for itself would be a second opinion about the same question — and the
   * planner and the shopping list will need the first one.
   */
  protected readonly pressing = signal<PantryEntry[]>([]);
  protected readonly failed = signal(false);

  protected readonly urgency = urgency;
  protected readonly day = day;

  constructor() {
    const pantry = inject(PantryService);
    pantry.listPantry().subscribe({
      // An empty pantry and a failed request look identical unless one of them says so,
      // and "you have nothing" is a bad thing to tell somebody untruthfully.
      next: (shelf) => this.shelf.set(shelf),
      error: () => this.failed.set(true),
    });
    pantry.listUsingSoon().subscribe({
      next: (pressing) => this.pressing.set(pressing),
      error: () => this.pressing.set([]),
    });
  }
}
