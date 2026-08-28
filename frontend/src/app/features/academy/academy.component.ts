import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { AcademyService, CategoryView, IngredientsService, PageKind, PageSummaryView } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { preferredLocale } from '../../core/locale/locale.store';

/**
 * One section of the Academy.
 *
 * A section is split one of two ways. Techniques get letters, because there is nothing
 * else to file *sear* under. Pages about food get **shelves** — where the registry says
 * that food sits — and letters inside each, so the section reads as
 * *Ingredients > Vegetables > Carrot* rather than as one flat alphabet (ADR-067).
 */
interface PageGroup {
  readonly kind: PageKind;
  readonly shelves: readonly Shelf[];
}

interface Shelf {
  /** Empty for the section's own shelf, which is every page it has no better place for. */
  readonly slug: string;
  /** Absent where the section is not shelved at all, and the letters stand on their own. */
  readonly name: string | null;
  readonly letters: readonly LetterGroup[];
}

interface LetterGroup {
  readonly initial: string;
  readonly pages: readonly PageSummaryView[];
}

/**
 * Pages about food, on the shelf the registry puts that food on.
 *
 * Ordered by the shelf's name in the reader's language, so a German reader gets German
 * headings in German alphabetical order. What nobody has placed goes last, under a
 * heading this screen writes — the server does not invent one, because an invented
 * category cannot be told apart from a known one (ADR-067).
 */
function onShelves(
  pages: readonly PageSummaryView[],
  named: Map<string, string>,
  collator: Intl.Collator,
): Shelf[] {
  const grouped = new Map<string, PageSummaryView[]>();
  for (const page of pages) {
    const slug = page.category_slug ?? '';
    grouped.set(slug, [...(grouped.get(slug) ?? []), page]);
  }

  const shelved = [...grouped]
    .filter(([slug]) => named.has(slug))
    .map(([slug, found]) => ({
      slug,
      name: named.get(slug) ?? slug,
      letters: byLetter(found, collator),
    }))
    .sort((a, b) => collator.compare(a.name, b.name));

  const loose = [...grouped].filter(([slug]) => !named.has(slug)).flatMap(([, found]) => found);
  return loose.length === 0
    ? shelved
    : [
        ...shelved,
        {
          slug: '',
          name: $localize`:@@academyElsewhere:Anything else`,
          letters: byLetter(loose, collator),
        },
      ];
}

/**
 * Entries under the letter they begin with.
 *
 * The letter is taken from the name as the reader's language writes it, uppercased and
 * with its accents folded away — *échalote* belongs under E, not under a heading of its
 * own that only ever holds one word.
 */
function byLetter(pages: readonly PageSummaryView[], collator: Intl.Collator): LetterGroup[] {
  const under = new Map<string, PageSummaryView[]>();
  for (const page of [...pages].sort((a, b) => collator.compare(a.name, b.name))) {
    const initial =
      page.name
        .normalize('NFD')
        .replace(/\p{Diacritic}/gu, '')
        .charAt(0)
        .toUpperCase() || '—';
    under.set(initial, [...(under.get(initial) ?? []), page]);
  }
  return [...under].map(([initial, found]) => ({ initial, pages: found }));
}

/** What a section is called, where the list is showing more than one of them. */
function kindLabel(kind: PageKind): string {
  return kind === PageKind.technique
    ? $localize`:@@academySectionDoing:Things you do`
    : $localize`:@@academySectionFoods:Ingredients`;
}

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
  /** Reading needs no account; everything that changes the Academy does (ADR-063). */
  protected readonly isSignedIn = inject(AuthStore).isSignedIn;

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

  /**
   * The settled pages, by section and then by first letter.
   *
   * Fifty entries in one flat alphabetical column is a column nobody navigates, and it
   * grows with every page anybody writes. Grouping by kind says the other thing the list
   * did not: a technique and an ingredient are different sorts of entry, and the section
   * buttons above only made sense once the list showed the division they filter (A2, X6).
   *
   * Sorted by the reader's language rather than by code point, so *Ähren* files under A.
   */
  protected readonly grouped = computed<PageGroup[]>(() => {
    const collator = new Intl.Collator(preferredLocale());
    const named = new Map(this.tree().map((one) => [one.slug, one.name]));
    const byKind = new Map<PageKind, PageSummaryView[]>();
    for (const page of this.settled()) {
      byKind.set(page.kind, [...(byKind.get(page.kind) ?? []), page]);
    }
    // Techniques first, in the order the section buttons offer them.
    const order = [PageKind.technique, PageKind.ingredient];
    return order
      .filter((kind) => byKind.has(kind))
      .map((kind) => ({
        kind,
        shelves:
          // Only the food section is shelved, and only where there is a tree to shelve it
          // by. A technique has no aisle, and an instance with no tree keeps the alphabet
          // it had.
          kind === PageKind.ingredient && named.size > 0
            ? onShelves(byKind.get(kind) ?? [], named, collator)
            : [{ slug: '', name: null, letters: byLetter(byKind.get(kind) ?? [], collator) }],
      }));
  });

  /**
   * The food tree, for filing the ingredient section.
   *
   * Read rather than derived from the pages: the registry is where a carrot being a
   * vegetable is recorded, and the Academy holding its own copy would be a second answer
   * to drift from the first (ADR-061).
   */
  private readonly tree = signal<readonly CategoryView[]>([]);

  protected readonly kindLabel = kindLabel;

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

    inject(IngredientsService)
      .listFoodCategories()
      .subscribe({
        // A tree that cannot be read leaves the section lettered, which is what it was.
        next: (tree) => this.tree.set(tree),
        error: () => this.tree.set([]),
      });

    inject(AcademyService)
      // The language is sent, not derived: a signed-out reader has no cook record for the
      // server to take one from. It is ignored where there is one (ADR-063).
      .browseAcademy(undefined, undefined, undefined, preferredLocale())
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
