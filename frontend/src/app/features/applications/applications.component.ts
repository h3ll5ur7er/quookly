import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { AccountsService, Cook } from '@api';

/**
 * Who is waiting to be let in (UC-10.6).
 *
 * The admin half of applying. A queue rather than a list: oldest first, because the
 * person who has been waiting longest is the one most owed an answer, and an admin works
 * down it.
 *
 * Refusing is reversible, and says so. An admin who mis-taps should not have to reach for
 * a database, and the API treats a second decision as an ordinary one.
 */
@Component({
  selector: 'app-applications',
  templateUrl: './applications.component.html',
  styleUrl: './applications.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationsComponent {
  private readonly accounts = inject(AccountsService);

  protected readonly waiting = signal<Cook[]>([]);
  protected readonly loaded = signal(false);
  protected readonly failed = signal(false);
  /** Who a decision is in flight for, so one row's buttons settle without freezing the rest. */
  protected readonly deciding = signal<number | null>(null);
  protected readonly decided = signal<string | null>(null);

  /**
   * Nobody is waiting — and we know that, rather than having failed to ask.
   *
   * The `failed()` term is not defensive tidiness: without it a request that was refused
   * shows "nobody is waiting", which tells an admin the queue is empty when it may not be.
   */
  protected readonly quiet = computed(
    () => this.loaded() && !this.failed() && this.waiting().length === 0,
  );

  constructor() {
    this.load();
  }

  private load(): void {
    this.accounts.listApplications().subscribe({
      next: (applicants) => {
        this.waiting.set(applicants);
        this.loaded.set(true);
      },
      error: () => {
        this.failed.set(true);
        this.loaded.set(true);
      },
    });
  }

  protected decide(applicant: Cook, approved: boolean): void {
    if (this.deciding() !== null) {
      return;
    }
    this.deciding.set(applicant.id);
    this.failed.set(false);
    const answer = approved
      ? this.accounts.approveApplication(applicant.id)
      : this.accounts.refuseApplication(applicant.id);
    answer.subscribe({
      next: () => {
        // Off the queue either way: refused is a decision, not a pending one, and leaving
        // them here would ask the same question every time an admin looked.
        this.waiting.update((queue) => queue.filter((one) => one.id !== applicant.id));
        this.deciding.set(null);
        this.decided.set(
          approved
            ? $localize`:@@applicationsLetIn:${applicant.display_name}:name: can now sign in.`
            : $localize`:@@applicationsTurnedAway:${applicant.display_name}:name: was turned away.`,
        );
      },
      error: () => {
        this.deciding.set(null);
        this.failed.set(true);
      },
    });
  }
}
