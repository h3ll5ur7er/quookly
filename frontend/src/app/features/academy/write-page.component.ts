import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AcademyService, PageKind } from '@api';

/**
 * Writing a page for the Academy (UC-7.4).
 *
 * In one language — the cook's own. Somebody who knows how to spatchcock a chicken is not
 * thereby a translator, and a page written in one language is one the other two fall back
 * from (ADR-057). Translating it is a separate act, on the page itself.
 */
@Component({
  selector: 'app-write-academy-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './write-page.component.html',
  styleUrl: './write-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WritePageComponent {
  private readonly academy = inject(AcademyService);
  private readonly router = inject(Router);

  protected readonly page = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(200)]],
    slug: ['', [Validators.required, Validators.pattern(/^[a-z0-9]+(-[a-z0-9]+)*$/)]],
    // Not a field: there is one section so far, and a select with a single option is a
    // question with one answer. It becomes a choice when the ingredient section lands.
    kind: [PageKind.technique],
    spellings: [''],
    summary: ['', [Validators.required, Validators.maxLength(400)]],
    explanation: ['', Validators.required],
    caution: [''],
    name_matches: [true],
  });

  protected readonly saving = signal(false);
  protected readonly failed = signal<string | null>(null);

  /**
   * Whether the cook has typed a slug themselves.
   *
   * Until they have, the name suggests one — nobody should have to invent a URL fragment
   * to contribute a paragraph. After they have, the suggestion stops: a field that keeps
   * overwriting what somebody typed is worse than one that was never filled in.
   */
  private ownSlug = false;

  constructor() {
    this.page.controls.slug.valueChanges.pipe(takeUntilDestroyed()).subscribe(() => {
      if (this.page.controls.slug.dirty) {
        this.ownSlug = true;
      }
    });
    this.page.controls.name.valueChanges.pipe(takeUntilDestroyed()).subscribe((name) => {
      if (!this.ownSlug) {
        this.page.controls.slug.setValue(sluggify(name), { emitEvent: false });
      }
    });
    this.page.statusChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.filled.set(this.page.valid));
  }

  /**
   * Whether there is enough to send.
   *
   * Mirrored into a signal rather than read off the form. `computed(() => form.valid)` is
   * the obvious line and it is wrong: a reactive form's validity is not a signal, so the
   * computed reads it once and the submit button never enables.
   */
  private readonly filled = signal(false);
  protected readonly ready = computed(() => this.filled());

  protected write(): void {
    if (!this.page.valid || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(null);

    const written = this.page.getRawValue();
    this.academy
      .writePage({
        slug: written.slug,
        kind: written.kind,
        name: written.name.trim(),
        // One per line rather than comma-separated: a spelling may contain a comma, and a
        // separator that can appear inside a value is one that will split one eventually.
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
        next: (made) => void this.router.navigate(['/academy', made.slug]),
        error: (refusal: HttpErrorResponse) => {
          this.saving.set(false);
          const detail: unknown = refusal.error?.detail;
          this.failed.set(
            typeof detail === 'string'
              ? detail
              : $localize`:@@academyWriteFailed:Could not save that. Please try again.`,
          );
        },
      });
  }
}

/** A name as a slug: lower case, words joined by hyphens, nothing else kept. */
function sluggify(name: string): string {
  return (
    name
      .toLowerCase()
      .normalize('NFD')
      // Strip the accents rather than the letters they sit on: `flambé` is `flambe`, not
      // `flamb`.
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
  );
}
