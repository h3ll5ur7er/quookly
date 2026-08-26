import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AcademyService, PageSummaryView } from '@api';

@Component({
  selector: 'app-academy',
  imports: [RouterLink],
  templateUrl: './academy.component.html',
  styleUrl: './academy.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AcademyComponent {
  protected readonly pages = signal<PageSummaryView[] | null>(null);
  protected readonly failed = signal(false);

  /**
   * Pages nobody here has read yet.
   *
   * Shown to everybody rather than to administrators alone. An author needs to see that
   * their own page is waiting — otherwise the first thing they notice is that the word
   * they just explained is not marked in their recipes, and nothing says why (ADR-060).
   */
  protected readonly waiting = computed(() => this.pages()?.filter((one) => !one.approved) ?? []);

  /** What the Academy answers with today: everything a reader can rely on. */
  protected readonly settled = computed(() => this.pages()?.filter((one) => one.approved) ?? []);

  constructor() {
    inject(AcademyService)
      .browseAcademy()
      .subscribe({
        // An empty Academy and an unreachable one look identical unless one says so.
        next: (found) => this.pages.set(found),
        error: () => this.failed.set(true),
      });
  }
}
