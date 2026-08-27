import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormBuilder, FormControl, ReactiveFormsModule } from '@angular/forms';
import { AcademyService, ClaimantView, PageView } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { PictureComponent } from '../../core/media/picture.component';
import { LOCALES, preferredLocale } from '../../core/locale/locale.store';
import { allergenLabel } from '../../core/dietary/labels';

@Component({
  selector: 'app-academy-page',
  imports: [PictureComponent, ReactiveFormsModule, RouterLink],
  templateUrl: './page.component.html',
  styleUrl: './page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AcademyPageComponent {
  private readonly service = inject(AcademyService);
  private readonly route = inject(ActivatedRoute).snapshot;
  private readonly forms = inject(FormBuilder);

  /** Correcting the Academy changes what every cook here reads, so it is an admin's. */
  private readonly auth = inject(AuthStore);
  protected readonly isAdmin = this.auth.isAdmin;
  /** Reading needs no account; everything that changes the Academy does (ADR-063). */
  protected readonly isSignedIn = this.auth.isSignedIn;
  protected readonly locales = LOCALES;
  /** The fourteen have names a reader knows; the enum has slugs. */
  protected readonly allergenLabel = allergenLabel;

  protected readonly correcting = signal(false);
  /** Whether the admin has asked to put this page away and not yet confirmed. */
  protected readonly declining = signal(false);
  protected readonly illustrating = signal(false);
  /** Alt text is required, so the button stays disabled until there is some. */
  protected readonly describing = new FormControl('', { nonNullable: true });
  protected readonly chosen = signal<File | null>(null);
  protected readonly saveFailed = signal(false);

  /** Asking a model to explain a word nobody here has explained (ADR-062). */
  protected readonly asking = signal(false);
  protected readonly askFailed = signal<string | null>(null);

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

  private readonly router = inject(Router);

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
      // The language is sent, not derived: a signed-out reader has no cook record for the
      // server to take one from. It is ignored where there is one (ADR-063).
      this.service.readPage(slug, preferredLocale()).subscribe({
        next: (found) => this.page.set(found),
        error: (refusal: { status?: number }) =>
          refusal.status === 404 ? this.missing.set(true) : this.failed.set(true),
      });
      return;
    }
    if (this.term !== null) {
      this.service.pagesForTerm(this.term, preferredLocale()).subscribe({
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

  protected choose(event: Event): void {
    const picked = (event.target as HTMLInputElement).files;
    this.chosen.set(picked && picked.length > 0 ? picked[0] : null);
  }

  /**
   * Put a picture on this page.
   *
   * The description is not optional and the control says so: a picture without alt text is
   * an accessibility failure, and there is nowhere sensible to default one from.
   */
  protected illustrate(): void {
    const shown = this.page();
    const picture = this.chosen();
    const description = this.describing.value.trim();
    if (shown === null || picture === null || !description) {
      return;
    }
    this.saveFailed.set(false);
    this.service.illustratePage(shown.slug, picture, description).subscribe({
      next: (saved) => {
        this.page.set(saved);
        this.illustrating.set(false);
        this.chosen.set(null);
        this.describing.setValue('');
      },
      error: () => this.saveFailed.set(true),
    });
  }

  protected removePicture(pictureId: number): void {
    const shown = this.page();
    if (shown === null) {
      return;
    }
    this.saveFailed.set(false);
    this.service.unillustratePage(shown.slug, pictureId).subscribe({
      next: (saved) => this.page.set(saved),
      error: () => this.saveFailed.set(true),
    });
  }

  /** Put this page away, then go back to the list it has just left. */
  protected decline(): void {
    const shown = this.page();
    if (shown === null) {
      return;
    }
    this.saveFailed.set(false);
    this.service.declinePage(shown.slug).subscribe({
      next: () => {
        this.declining.set(false);
        void this.router.navigate(['/academy']);
      },
      error: () => {
        this.declining.set(false);
        this.saveFailed.set(true);
      },
    });
  }

  /**
   * Ask for an explanation of the word that was looked up.
   *
   * What comes back is shown in place of the chooser: it is a page, and the page screen
   * already knows how to say that a model wrote it and nobody has read it (ADR-056).
   */
  protected ask(): void {
    const wanted = this.term;
    if (wanted === null || this.asking()) {
      return;
    }
    this.asking.set(true);
    this.askFailed.set(null);

    this.service.explainTerm({ term: wanted }).subscribe({
      next: (written) => {
        this.asking.set(false);
        // Out of the chooser and onto the page, without a navigation: the address still
        // names the term, and coming back to it should still be the term screen.
        this.choices.set(null);
        this.page.set(written);
      },
      error: (refusal: { error?: { detail?: unknown } }) => {
        this.asking.set(false);
        const detail = refusal.error?.detail;
        this.askFailed.set(
          typeof detail === 'string'
            ? detail
            : $localize`:@@academyAskFailed:That did not work. Please try again.`,
        );
      },
    });
  }
}
