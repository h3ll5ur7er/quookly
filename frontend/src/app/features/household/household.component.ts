import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EaterView, EatersService, HouseholdSummary } from '@api';
import { ageBandLabel, constraintLabel, severityMark } from './household.labels';

@Component({
  selector: 'app-household',
  imports: [RouterLink],
  templateUrl: './household.component.html',
  styleUrl: './household.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HouseholdComponent {
  protected readonly household = signal<EaterView[] | null>(null);
  protected readonly summary = signal<HouseholdSummary | null>(null);
  protected readonly failed = signal(false);

  /**
   * "Cooking for one person" rather than "Cooking for 1", and never "1 people".
   *
   * Written out per count in the same way as the recipe timings, because the runtime
   * catalogues hold flat messages: an ICU plural would have nowhere to be translated.
   */
  protected readonly cookingFor = computed(() => {
    const total = this.summary();
    if (total === null || total.people === 0) {
      return null;
    }
    return total.people === 1
      ? $localize`:@@householdOnePerson:Cooking for one person`
      : $localize`:@@householdPeople:Cooking for ${total.people}:count: people`;
  });

  protected readonly ageBandLabel = ageBandLabel;
  protected readonly constraintLabel = constraintLabel;
  protected readonly severityMark = severityMark;

  constructor() {
    const eaters = inject(EatersService);
    eaters.listEaters().subscribe({
      next: (household) => this.household.set(household),
      // An empty household and a failed request look identical on screen unless one of
      // them says so, and "nobody here" is a bad thing to tell somebody untruthfully —
      // it is also the state in which no recipe would be flagged for anybody.
      error: () => this.failed.set(true),
    });
    eaters.getHouseholdSummary().subscribe({
      next: (summary) => this.summary.set(summary),
      error: () => this.summary.set(null),
    });
  }
}
