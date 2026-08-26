import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AcademyService, ClaimantView, PageView } from '@api';

@Component({
  selector: 'app-academy-page',
  imports: [RouterLink],
  templateUrl: './page.component.html',
  styleUrl: './page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AcademyPageComponent {
  private readonly service = inject(AcademyService);
  private readonly route = inject(ActivatedRoute).snapshot;

  protected readonly page = signal<PageView | null>(null);
  protected readonly missing = signal(false);
  protected readonly failed = signal(false);

  /**
   * Where several pages answer to one term, the ones to choose between.
   *
   * A step's word links to the *term*, not to a page: one claimant opens it and several
   * offer this (ADR-058). Nothing picks arbitrarily.
   */
  protected readonly choices = signal<ClaimantView[] | null>(null);
  protected readonly term = this.route.paramMap.get('term');

  constructor() {
    const slug = this.route.paramMap.get('slug');
    if (slug !== null) {
      this.service.readPage(slug).subscribe({
        next: (found) => this.page.set(found),
        error: (refusal: { status?: number }) =>
          refusal.status === 404 ? this.missing.set(true) : this.failed.set(true),
      });
      return;
    }
    if (this.term !== null) {
      this.service.pagesForTerm(this.term).subscribe({
        next: (found) => {
          // One claimant is not a choice. Showing a chooser with a single option would be
          // asking a question that answers itself.
          if (found.length === 1) {
            this.service.readPage(found[0].slug).subscribe({
              next: (page) => this.page.set(page),
              error: () => this.failed.set(true),
            });
            return;
          }
          this.choices.set(found);
        },
        error: () => this.failed.set(true),
      });
    }
  }
}
