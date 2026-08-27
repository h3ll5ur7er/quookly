import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { AcademyService, PageKind, PageSummaryView } from '@api';

@Component({
  selector: 'app-academy',
  imports: [ReactiveFormsModule, RouterLink],
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
   * A word to look up.
   *
   * The way in to the term screen, and the reason it needs one: a word nobody has
   * explained is a word no recipe underlines, so without this the screen that says
   * "nobody has explained that yet" — and the offer to ask — cannot be reached at all.
   */
  protected readonly looking = new FormControl('', { nonNullable: true });
  private readonly typed = signal('');
  protected readonly canLook = computed(() => this.typed().length > 0);

  private readonly router = inject(Router);

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
    this.looking.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((word) => this.typed.set(word.trim()));

    inject(AcademyService)
      .browseAcademy()
      .subscribe({
        // An empty Academy and an unreachable one look identical unless one says so.
        next: (found) => this.pages.set(found),
        error: () => this.failed.set(true),
      });
  }

  /** Go to whatever claims this word — or to the screen that says nobody has. */
  protected look(): void {
    const wanted = this.typed();
    if (wanted) {
      void this.router.navigate(['/academy', 'terms', wanted]);
    }
  }
}
