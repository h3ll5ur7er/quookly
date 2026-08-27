import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AcademyService, IngredientView, IngredientsService, PageKind } from '@api';
import { debounceTime, distinctUntilChanged } from 'rxjs';

/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

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
  private readonly ingredients = inject(IngredientsService);
  private readonly router = inject(Router);

  protected readonly kinds: readonly PageKind[] = [PageKind.technique, PageKind.ingredient];

  /** The sections have names a cook reads; the enum has slugs. */
  protected sectionLabel(kind: PageKind): string {
    return kind === PageKind.ingredient
      ? $localize`:@@academySectionIngredient:An ingredient`
      : $localize`:@@academySectionTechnique:Something you do`;
  }

  protected readonly page = inject(FormBuilder).nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(200)]],
    slug: ['', [Validators.required, Validators.pattern(/^[a-z0-9]+(-[a-z0-9]+)*$/)]],
    kind: [PageKind.technique],
    spellings: [''],
    summary: ['', [Validators.required, Validators.maxLength(400)]],
    explanation: ['', Validators.required],
    caution: [''],
    name_matches: [true],
  });

  protected readonly saving = signal(false);
  protected readonly failed = signal<string | null>(null);

  /** Which section is being written for, so the form can ask what that section needs. */
  protected readonly section = signal<PageKind>(PageKind.technique);
  protected readonly aboutFood = computed(() => this.section() === PageKind.ingredient);

  /**
   * The registry entry an ingredient page is about.
   *
   * Chosen from the registry rather than typed. A page about a food the registry does not
   * have is a page about nothing — and the facts on the page are that entry's, read from
   * there (ADR-061).
   */
  protected readonly about = signal<IngredientView | null>(null);
  protected readonly looking = new FormControl('', { nonNullable: true });
  protected readonly matches = signal<IngredientView[]>([]);

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
    this.page.controls.kind.valueChanges.pipe(takeUntilDestroyed()).subscribe((kind) => {
      this.section.set(kind);
      // A food chosen for a page that is no longer about food would travel silently.
      if (kind !== PageKind.ingredient) {
        this.about.set(null);
      }
    });
    this.looking.valueChanges
      .pipe(debounceTime(SETTLE), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe((term) => this.look(term));
  }

  /**
   * Whether there is enough to send.
   *
   * Mirrored into a signal rather than read off the form. `computed(() => form.valid)` is
   * the obvious line and it is wrong: a reactive form's validity is not a signal, so the
   * computed reads it once and the submit button never enables.
   */
  private readonly filled = signal(false);
  protected readonly ready = computed(
    () => this.filled() && (!this.aboutFood() || this.about() !== null),
  );

  private look(term: string): void {
    const wanted = term.trim();
    if (!wanted) {
      this.matches.set([]);
      return;
    }
    this.ingredients.searchIngredients(wanted).subscribe({
      next: (found) => this.matches.set(found),
      error: () => this.matches.set([]),
    });
  }

  protected choose(found: IngredientView): void {
    this.about.set(found);
    this.matches.set([]);
    this.looking.setValue('', { emitEvent: false });
  }

  protected write(): void {
    if (!this.ready() || this.saving()) {
      return;
    }
    this.saving.set(true);
    this.failed.set(null);

    const written = this.page.getRawValue();
    this.academy
      .writePage({
        slug: written.slug,
        kind: written.kind,
        about: this.about()?.slug ?? null,
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
