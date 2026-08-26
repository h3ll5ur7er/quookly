import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { IngredientsService, Origin, RegistryEntryView } from '@api';
import { debounceTime, distinctUntilChanged } from 'rxjs';
import { kindLabel } from '../../core/measure/kinds';
import { allergenLabel } from '../../core/dietary/labels';

/** A screenful. Enough to scroll, few enough that a phone renders it without thinking. */
const PAGE = 50;

/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

@Component({
  selector: 'app-registry',
  imports: [ReactiveFormsModule],
  templateUrl: './registry.component.html',
  styleUrl: './registry.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RegistryComponent {
  private readonly service = inject(IngredientsService);

  protected readonly entries = signal<RegistryEntryView[] | null>(null);
  protected readonly total = signal(0);
  protected readonly failed = signal(false);

  protected readonly search = new FormControl('', { nonNullable: true });
  protected readonly origin = signal<Origin | null>(null);

  /** Exposed so the template can name a value rather than repeat a string literal. */
  protected readonly Origin = Origin;

  protected readonly kindLabel = kindLabel;
  protected readonly allergenLabel = allergenLabel;

  /** Whether the list on screen is all of it, or the start of something longer. */
  protected readonly more = computed(() => (this.entries() ?? []).length < this.total());

  constructor() {
    this.load();

    // Settled before asking: a box that fires on every keystroke asks the server about
    // "b", "bu" and "but" to answer a question about butter.
    this.search.valueChanges
      .pipe(debounceTime(SETTLE), distinctUntilChanged(), takeUntilDestroyed())
      .subscribe(() => this.load());
  }

  /**
   * Show only what was seeded, or only what an import invented — or all of it.
   *
   * The second is the one this screen exists for. An import creates an entry for a line
   * that resolves to nothing, and what it creates is a guess (ADR-029); until they can be
   * listed apart from nine hundred seeded ones there is no way to review them.
   */
  protected narrowTo(origin: Origin | null): void {
    this.origin.set(origin);
    this.load();
  }

  /** The next page, appended. A cook scrolling a long list has not lost their place. */
  protected showMore(): void {
    this.load({ from: (this.entries() ?? []).length });
  }

  /**
   * Ask for a page.
   *
   * Without `from` this replaces what is on screen, which is what narrowing and searching
   * both want: a filtered list that kept the old rows underneath it would be answering
   * two questions at once.
   */
  private load({ from = 0 } = {}): void {
    const term = this.search.value.trim();
    this.failed.set(false);
    if (from === 0) {
      this.entries.set(null);
    }
    this.service.listRegistry(term || undefined, this.origin() ?? undefined, from, PAGE).subscribe({
      next: (page) => {
        this.entries.update((held) =>
          from === 0 ? page.entries : [...(held ?? []), ...page.entries],
        );
        this.total.set(page.total);
      },
      // An empty registry and an unreachable one look identical unless one of them says
      // so, and "there are no ingredients" is a bad thing to tell somebody untruthfully.
      error: () => this.failed.set(true),
    });
  }
}
