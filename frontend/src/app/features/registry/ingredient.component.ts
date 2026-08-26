import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  Allergen,
  IngredientKind,
  IngredientsService,
  RegistryEntryDetailView,
  RegistryEntryView,
} from '@api';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged, switchMap } from 'rxjs';
import { AuthStore } from '../../core/auth/auth.store';
import { ALLERGENS, allergenLabel } from '../../core/dietary/labels';
import { kindLabel } from '../../core/measure/kinds';

/** The kinds, in the order the unit preferences list them. */
/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

/** A shortlist. Merging is a decision, not a browse. */
const CANDIDATES = 8;

const KINDS: readonly IngredientKind[] = [
  IngredientKind.solid,
  IngredientKind.liquid,
  IngredientKind.powder,
  IngredientKind.countable,
];

@Component({
  selector: 'app-ingredient',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './ingredient.component.html',
  styleUrl: './ingredient.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class IngredientComponent {
  private readonly service = inject(IngredientsService);
  private readonly forms = inject(FormBuilder);
  private readonly router = inject(Router);

  protected readonly isAdmin = inject(AuthStore).isAdmin;
  private readonly slug = inject(ActivatedRoute).snapshot.paramMap.get('slug') ?? '';

  protected readonly detail = signal<RegistryEntryDetailView | null>(null);
  protected readonly missing = signal(false);
  protected readonly failed = signal(false);
  protected readonly saveFailed = signal(false);
  protected readonly nothingChanged = signal(false);
  /**
   * What the server said when it refused a name, verbatim.
   *
   * Verbatim because the useful part is *which entry* holds the spelling, and only
   * the server knows that. A generic "could not save" would throw away the one
   * signal worth having: two entries wanting one name in one language are often one
   * ingredient an import split in two.
   */
  protected readonly nameRefused = signal<string | null>(null);

  protected readonly kinds = KINDS;
  protected readonly allergens = ALLERGENS;
  protected readonly kindLabel = kindLabel;
  protected readonly allergenLabel = allergenLabel;

  protected readonly entry = computed(() => this.detail()?.entry ?? null);

  /** Locale to spellings, as rows a template can loop over. */
  protected readonly languages = computed(() => Object.entries(this.detail()?.names ?? {}));

  /**
   * An entry an import created is named only in the language of the page it came from.
   * Saying so is the prompt: it is the gap somebody reading this screen can actually fill.
   */
  protected readonly oneLanguageOnly = computed(() => this.languages().length === 1);

  /** The three facts an import guesses at. Blank means absent, which is a real answer. */
  protected readonly correction = this.forms.nonNullable.group({
    kind: [IngredientKind.solid],
    density: [''],
    piece_grams: [''],
  });

  /** Ticked classes. Submitting with none ticked is "I looked, there is nothing in it". */
  protected readonly ticked = signal<ReadonlySet<Allergen>>(new Set());

  /**
   * Which language to rename, and to what.
   *
   * Only the languages the entry already has: renaming one it does not have is just
   * adding a name, which the form below already does.
   */
  protected readonly renaming = this.forms.nonNullable.group({
    locale: ['', Validators.required],
    name: ['', Validators.required],
  });

  /** What to search the registry for when looking for the entry this really is. */
  protected readonly mergeInto = new FormControl('', { nonNullable: true });

  /** Candidates for the merge, never including this entry itself. */
  protected readonly candidates = signal<RegistryEntryView[]>([]);
  protected readonly searched = signal(false);

  /**
   * The entry an admin has chosen but not yet confirmed.
   *
   * Two steps on purpose. Merging repoints recipe lines, pantry lots, waste, shopping
   * ticks and every eater's dietary constraints, and it cannot be undone — a single click
   * is the wrong shape for that.
   */
  protected readonly proposed = signal<RegistryEntryView | null>(null);

  protected readonly naming = this.forms.nonNullable.group({
    locale: ['', Validators.required],
    spelling: ['', Validators.required],
  });

  constructor() {
    this.mergeInto.valueChanges
      .pipe(
        debounceTime(SETTLE),
        distinctUntilChanged(),
        switchMap((term) =>
          this.service.listRegistry(term.trim() || undefined, undefined, undefined, 0, CANDIDATES),
        ),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (page) => {
          // Never itself: an entry cannot be its own target, and offering it invites the
          // one mistake the API refuses anyway.
          this.candidates.set(page.entries.filter((entry) => entry.slug !== this.slug));
          this.searched.set(true);
        },
        error: () => this.failed.set(true),
      });

    this.service.getIngredient(this.slug).subscribe({
      next: (found) => this.arrived(found),
      error: (refusal: { status?: number }) =>
        refusal.status === 404 ? this.missing.set(true) : this.failed.set(true),
    });
  }

  protected isTicked(allergen: Allergen): boolean {
    return this.ticked().has(allergen);
  }

  protected toggle(allergen: Allergen): void {
    this.ticked.update((held) => {
      const next = new Set(held);
      if (!next.delete(allergen)) {
        next.add(allergen);
      }
      return next;
    });
  }

  /**
   * Send only what actually changed.
   *
   * The distinction the API is built around: a field left out keeps its value, and an
   * explicit `null` clears it. Sending the whole form would clear a density every time
   * somebody fixed the kind beside it.
   */
  protected save(): void {
    const entry = this.entry();
    if (entry === null) {
      return;
    }
    const form = this.correction.getRawValue();
    const change: { kind?: IngredientKind; density?: string | null; piece_grams?: string | null } =
      {};
    if (form.kind !== entry.kind) {
      change.kind = form.kind;
    }
    if (form.density.trim() !== (entry.density ?? '')) {
      change.density = form.density.trim() || null;
    }
    if (form.piece_grams.trim() !== (entry.piece_grams ?? '')) {
      change.piece_grams = form.piece_grams.trim() || null;
    }

    this.saveFailed.set(false);
    if (Object.keys(change).length === 0) {
      this.nothingChanged.set(true);
      return;
    }
    this.nothingChanged.set(false);
    this.service.amendIngredient(this.slug, change).subscribe({
      next: (amended) => this.replace(amended),
      // The form keeps what was typed. Clearing it would lose the correction and leave
      // the admin guessing whether it landed.
      error: () => this.saveFailed.set(true),
    });
  }

  /**
   * Record what is in this ingredient.
   *
   * Its own act, and its own request. Ticking nothing and pressing this says "I looked,
   * there is nothing in it" — a real answer, and the only control on the screen that can
   * give it. Folding it into `save` would make an untouched allergen section indistinguish-
   * able from that answer, which is unknown quietly becoming safe (ADR-006).
   */
  protected classify(): void {
    this.saveFailed.set(false);
    this.service.classifyIngredient(this.slug, { allergens: [...this.ticked()] }).subscribe({
      next: (classified) => this.replace(classified),
      error: () => this.saveFailed.set(true),
    });
  }

  /**
   * Change what one language calls this entry.
   *
   * Distinct from adding a spelling: this decides which of them is *the* name, the one a
   * cook is shown and a shopping list is written with. The previous one is kept, so pages
   * that use it still resolve.
   */
  protected doRename(): void {
    if (this.renaming.invalid) {
      return;
    }
    const { locale, name } = this.renaming.getRawValue();
    this.saveFailed.set(false);
    this.nameRefused.set(null);
    this.service.renameIngredient(this.slug, { locale, name: name.trim() }).subscribe({
      next: (renamed) => this.arrived(renamed),
      error: (refusal: { status?: number; error?: { detail?: string } }) =>
        refusal.status === 409
          ? this.nameRefused.set(refusal.error?.detail ?? null)
          : this.saveFailed.set(true),
    });
  }

  protected addName(): void {
    if (this.naming.invalid) {
      return;
    }
    const { locale, spelling } = this.naming.getRawValue();
    this.saveFailed.set(false);
    this.nameRefused.set(null);
    this.service
      .nameIngredient(this.slug, { locale: locale.trim(), spellings: [spelling.trim()] })
      .subscribe({
        next: (named) => {
          this.arrived(named);
          this.naming.reset({ locale: '', spelling: '' });
        },
        error: (refusal: { status?: number; error?: { detail?: string } }) =>
          refusal.status === 409
            ? this.nameRefused.set(refusal.error?.detail ?? null)
            : this.saveFailed.set(true),
      });
  }

  /** Choose a target, which shows the confirmation rather than doing anything. */
  protected propose(candidate: RegistryEntryView): void {
    this.proposed.set(candidate);
  }

  protected cancelMerge(): void {
    this.proposed.set(null);
  }

  /**
   * Do it.
   *
   * The page is about to describe an entry that no longer exists, so it navigates to the
   * survivor rather than re-rendering something that has been merged away.
   */
  protected confirmMerge(): void {
    const target = this.proposed();
    if (target === null) {
      return;
    }
    this.saveFailed.set(false);
    this.service.mergeIngredient(this.slug, { into: target.slug }).subscribe({
      next: (merged) => {
        this.proposed.set(null);
        void this.router.navigate(['/settings/registry', merged.entry.slug]);
      },
      error: () => this.saveFailed.set(true),
    });
  }

  protected approve(): void {
    this.saveFailed.set(false);
    this.service.approveIngredient(this.slug).subscribe({
      next: (approved) => this.replace(approved),
      error: () => this.saveFailed.set(true),
    });
  }

  /** Take the whole entry as the server describes it, and restate the form from it. */
  private arrived(found: RegistryEntryDetailView): void {
    this.detail.set(found);
    this.restate(found.entry);
    const [first] = Object.keys(found.names);
    this.renaming.setValue({ locale: first ?? '', name: '' });
  }

  /** A write returns the entry alone; the names it answers to are unchanged. */
  private replace(entry: RegistryEntryView): void {
    this.detail.update((held) => (held === null ? held : { ...held, entry }));
    this.restate(entry);
  }

  private restate(entry: RegistryEntryView): void {
    this.correction.setValue({
      kind: entry.kind,
      density: entry.density ?? '',
      piece_grams: entry.piece_grams ?? '',
    });
    this.nothingChanged.set(false);
    this.ticked.set(new Set(entry.allergens));
  }
}
