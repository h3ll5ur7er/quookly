import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { RecipeSummaryView, RecipesService, SuggestionView } from '@api';
import { debounceTime, distinctUntilChanged, startWith, switchMap } from 'rxjs';
import { isWarning, reasonLabel } from '../../core/discovery/labels';
import { outcomeBadge, worthMarking } from '../../core/dietary/labels';
import { TimingComponent } from '../../core/time/timing.component';

/** How the list is ordered when nothing has been typed. */
type Order = 'name' | 'worth';

/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

@Component({
  selector: 'app-recipe-list',
  imports: [ReactiveFormsModule, RouterLink, TimingComponent],
  templateUrl: './recipe-list.component.html',
  styleUrl: './recipe-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecipeListComponent {
  private readonly service = inject(RecipesService);

  protected readonly recipes = signal<RecipeSummaryView[] | null>(null);
  protected readonly failed = signal(false);

  protected readonly search = new FormControl('', { nonNullable: true });
  protected readonly order = signal<Order>('name');

  /**
   * Whether the cook is looking through what they put away.
   *
   * One list or the other, never both: what a cook has and what they archived are
   * different questions, and mixing them would make putting something away pointless
   * (ADR-059).
   */
  protected readonly showingArchived = signal(false);

  protected readonly reasonLabel = reasonLabel;
  protected readonly isWarning = isWarning;

  protected readonly outcomeBadge = outcomeBadge;
  protected readonly worthMarking = worthMarking;

  /**
   * Whether anything here was judged at all.
   *
   * A recipe that suits everybody carries no badge — twenty green ticks would drown the
   * one red one, and restraint is what keeps a warning worth reading. That makes an
   * unbadged list ambiguous on its own, so a cook with nobody recorded is told why they
   * are seeing none rather than left to read the silence as approval.
   */
  protected readonly judged = computed(() =>
    (this.rows() ?? []).some((row) => row.recipe.suitability != null),
  );

  /** What the cook has typed, as a signal, so the screen can tell asking from browsing. */
  private readonly typed = toSignal(this.search.valueChanges.pipe(startWith(this.search.value)), {
    initialValue: '',
  });

  protected readonly asking = computed(() => this.typed().trim().length > 0);

  /** Suggestions, which only arrive when something was asked or the order calls for them. */
  private readonly suggestions = signal<SuggestionView[] | null>(null);

  /**
   * The list, however it was arrived at.
   *
   * A plain listing is a set of recipes and a suggestion is a recipe with reasons, so the
   * plain one is widened rather than the two being drawn separately: a recipe should read
   * the same whichever question brought it up.
   */
  protected readonly rows = computed<SuggestionView[] | null>(() => {
    if (this.asking() || this.order() === 'worth') {
      return this.suggestions();
    }
    const listed = this.recipes();
    return listed === null
      ? null
      : listed.map((recipe) => ({ recipe, reasons: [], pressing: [], missing: 0 }));
  });

  constructor() {
    this.service.listRecipes().subscribe({
      // An empty list and a failed request look identical on screen unless one of them says
      // so, and "you have no recipes" is a bad thing to tell someone untruthfully.
      next: (recipes) => this.recipes.set(recipes),
      error: () => this.failed.set(true),
    });

    // Settled before asking, because a search box that fires on every keystroke asks the
    // server about "p", "pa" and "pan" to answer a question about pancakes.
    this.search.valueChanges
      .pipe(
        debounceTime(SETTLE),
        distinctUntilChanged(),
        switchMap((written) => this.service.suggestRecipes(written.trim() || undefined)),
        takeUntilDestroyed(),
      )
      .subscribe({
        next: (found) => this.suggestions.set(found),
        error: () => this.failed.set(true),
      });
  }

  /**
   * Order the list by what is worth cooking, or back to the alphabet.
   *
   * Explicit rather than automatic. A cook who came to find a recipe they already have in
   * mind wants the alphabet, and a list that quietly reorders itself around the spinach is
   * a list they cannot learn the shape of.
   */
  protected orderBy(order: Order): void {
    this.order.set(order);
    if (order === 'worth' && this.suggestions() === null) {
      this.service.suggestRecipes().subscribe({
        next: (found) => this.suggestions.set(found),
        error: () => this.failed.set(true),
      });
    }
  }

  /** Look through what has been put away, or come back to what is current. */
  protected showArchived(archived: boolean): void {
    this.showingArchived.set(archived);
    this.recipes.set(null);
    this.failed.set(false);
    this.service.listRecipes(archived).subscribe({
      next: (found) => this.recipes.set(found),
      error: () => this.failed.set(true),
    });
  }
}
