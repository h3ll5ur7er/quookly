import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AcademyService, PageKind, PageSummaryView } from '@api';

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
   * Which section is being read.
   *
   * Filtered here rather than re-asked. The Academy arrives whole and is small enough to,
   * and a round trip to hide half a list is a round trip a cook waits for.
   */
  protected readonly kinds = PageKind;
  protected readonly section = signal<PageKind | null>(null);

  /**
   * Pages nobody here has read yet.
   *
   * Shown to everybody rather than to administrators alone. An author needs to see that
   * their own page is waiting — otherwise the first thing they notice is that the word
   * they just explained is not marked in their recipes, and nothing says why (ADR-060).
   */
  protected readonly waiting = computed(() => this.shown().filter((one) => !one.approved));

  /** What the Academy answers with today: everything a reader can rely on. */
  protected readonly settled = computed(() => this.shown().filter((one) => one.approved));

  /** Whichever section is being read, or all of them. */
  private readonly shown = computed(() => {
    const found = this.pages() ?? [];
    const wanted = this.section();
    return wanted === null ? found : found.filter((one) => one.kind === wanted);
  });

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
