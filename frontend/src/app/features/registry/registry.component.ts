import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { DuplicateView, IngredientsService, Origin, RegistryEntryView } from '@api';
import { debounceTime, distinctUntilChanged } from 'rxjs';
import { AuthStore } from '../../core/auth/auth.store';
import { resemblanceLabel } from '../../core/registry/labels';
import { kindLabel } from '../../core/measure/kinds';
import { allergenLabel } from '../../core/dietary/labels';

/** A screenful. Enough to scroll, few enough that a phone renders it without thinking. */
const PAGE = 50;

/** Long enough that a phone keyboard is not searched at, short enough to feel immediate. */
const SETTLE = 200;

@Component({
  selector: 'app-registry',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './registry.component.html',
  styleUrl: './registry.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RegistryComponent {
  private readonly service = inject(IngredientsService);
  private readonly auth = inject(AuthStore);

  /** Signing an entry off is a statement about the instance, so it is an admin's. */
  protected readonly isAdmin = this.auth.isAdmin;

  protected readonly entries = signal<RegistryEntryView[] | null>(null);
  protected readonly total = signal(0);
  protected readonly failed = signal(false);
  /**
   * Separate from `failed`, which means the list could not be fetched.
   *
   * A failed approval still has a list to show. Folding the two together replaced the
   * whole registry with an error because one button did not land, which loses the
   * cook's place and tells them nothing about which entry was affected.
   */
  protected readonly approvalFailed = signal(false);

  protected readonly search = new FormControl('', { nonNullable: true });
  protected readonly origin = signal<Origin | null>(null);
  /** `false` is the queue: entries nobody has reviewed yet (ADR-051). */
  protected readonly approved = signal<boolean | null>(null);

  /** Exposed so the template can name a value rather than repeat a string literal. */
  protected readonly Origin = Origin;

  protected readonly kindLabel = kindLabel;
  protected readonly resemblanceLabel = resemblanceLabel;
  protected readonly allergenLabel = allergenLabel;

  /** Whether the list on screen is all of it, or the start of something longer. */
  /**
   * Pairs the matcher thinks are one ingredient. Empty until somebody asks.
   *
   * On demand rather than on arrival: it compares every entry with every other, which
   * takes seconds against the shipped nine hundred, and nobody opening the registry asked
   * that question. If it ever wants running regularly it belongs in a CLI command and a
   * cron job rather than in a page load.
   */
  protected readonly pairs = signal<DuplicateView[] | null>(null);
  protected readonly sweeping = signal(false);
  protected readonly sweepFailed = signal(false);

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
    this.approved.set(null);
    this.load();
  }

  /**
   * Show only what nobody has reviewed.
   *
   * The filter this screen exists for, and not the same as narrowing by origin: an entry
   * an import invented stays the cook's own after being approved, so provenance cannot
   * tell *reviewed* from *not yet* and the queue would never empty (ADR-051).
   */
  protected showQueue(): void {
    this.origin.set(null);
    this.approved.set(false);
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
    this.approvalFailed.set(false);
    if (from === 0) {
      this.entries.set(null);
    }
    this.service
      .listRegistry(
        term || undefined,
        this.origin() ?? undefined,
        this.approved() ?? undefined,
        from,
        PAGE,
      )
      .subscribe({
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

  /**
   * Record that this entry has been reviewed.
   *
   * The row is replaced with what the server sent back rather than patched locally: the
   * screen should show what was stored, not what was asked for. Where the list is the
   * queue, an approved entry no longer matches it and goes — leaving it visible would
   * show a row the filter says is not there.
   *
   * On failure the entry stays as it was and the notice appears. An optimistic tick that
   * silently did not happen is worse here than a slow one: it is a claim that somebody
   * looked.
   */
  protected approve(entry: RegistryEntryView): void {
    this.approvalFailed.set(false);
    this.service.approveIngredient(entry.slug).subscribe({
      next: (reviewed) => {
        const leaving = this.approved() === false;
        this.entries.update((held) =>
          (held ?? []).flatMap((row) =>
            row.id !== reviewed.id ? [row] : leaving ? [] : [reviewed],
          ),
        );
        if (leaving) {
          this.total.update((count) => Math.max(0, count - 1));
        }
      },
      error: () => this.approvalFailed.set(true),
    });
  }

  /** Compare every entry with every other, and report what might be one ingredient. */
  protected sweep(): void {
    this.sweeping.set(true);
    this.sweepFailed.set(false);
    this.service.findDuplicates().subscribe({
      next: (found) => {
        this.pairs.set(found);
        this.sweeping.set(false);
      },
      // The registry list stays: the sweep is an extra, and losing the page because an
      // extra failed would be a worse answer than no suggestions.
      error: () => {
        this.sweepFailed.set(true);
        this.sweeping.set(false);
      },
    });
  }
}
