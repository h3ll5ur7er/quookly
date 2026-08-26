import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { AcademyService, ClaimantView, PageView } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { LOCALES } from '../../core/locale/locale.store';

@Component({
  selector: 'app-academy-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './page.component.html',
  styleUrl: './page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AcademyPageComponent {
  private readonly service = inject(AcademyService);
  private readonly route = inject(ActivatedRoute).snapshot;
  private readonly forms = inject(FormBuilder);

  /** Correcting the Academy changes what every cook here reads, so it is an admin's. */
  protected readonly isAdmin = inject(AuthStore).isAdmin;
  protected readonly locales = LOCALES;

  protected readonly correcting = signal(false);
  protected readonly saveFailed = signal(false);

  /**
   * One language's wording, whole.
   *
   * Spellings are edited one per line rather than comma-separated: a comma is a character
   * a spelling may contain — the registry is full of names like `sugar, brown` — and a
   * separator that can appear inside a value is a separator that will one day split one.
   */
  protected readonly wording = this.forms.nonNullable.group({
    locale: ['en-GB'],
    name: [''],
    spellings: [''],
    summary: [''],
    explanation: [''],
    caution: [''],
    name_matches: [true],
  });

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

  /** Open the form, filled in with what the page says in the language being read. */
  protected correct(): void {
    const shown = this.page();
    if (shown === null) {
      return;
    }
    this.saveFailed.set(false);
    this.wording.setValue({
      locale: this.wording.getRawValue().locale,
      name: shown.name,
      spellings: shown.spellings.join('\n'),
      summary: shown.summary,
      explanation: shown.explanation,
      caution: shown.caution ?? '',
      name_matches: true,
    });
    this.correcting.set(true);
  }

  protected save(): void {
    const shown = this.page();
    if (shown === null) {
      return;
    }
    const written = this.wording.getRawValue();
    this.saveFailed.set(false);
    this.service
      .amendPage(shown.slug, written.locale, {
        name: written.name.trim(),
        spellings: written.spellings
          .split('\n')
          .map((one) => one.trim())
          .filter((one) => one.length > 0),
        summary: written.summary.trim(),
        explanation: written.explanation.trim(),
        caution: written.caution.trim() || null,
        name_matches: written.name_matches,
      })
      .subscribe({
        next: (saved) => {
          this.page.set(saved);
          this.correcting.set(false);
        },
        // The form keeps what was typed: clearing it would lose the correction and leave
        // the editor guessing whether it landed.
        error: () => this.saveFailed.set(true),
      });
  }

  /** Say that somebody here has read this page. Not that they wrote it (ADR-056). */
  protected approve(): void {
    const shown = this.page();
    if (shown === null) {
      return;
    }
    this.saveFailed.set(false);
    this.service.approvePage(shown.slug).subscribe({
      next: (approved) => this.page.set(approved),
      error: () => this.saveFailed.set(true),
    });
  }
}
