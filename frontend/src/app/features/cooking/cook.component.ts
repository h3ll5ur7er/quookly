import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { CookingService, GuidedStepView, SessionOutcome, SessionView, Sizing } from '@api';
import { Observable } from 'rxjs';
import { VerdictComponent } from '../../core/dietary/verdict.component';
import { keepScreenAwake } from '../../core/screen/wake-lock';
import { attentionNote } from '../../core/time/labels';
import { TimerComponent } from './timer.component';

/**
 * Cooking mode: one meal, one step at a time (UC-9.*).
 *
 * Not the recipe page with bigger text. The cook is standing, hands occupied and possibly
 * wet, glancing from a metre away — so the density rises, one step fills the screen, and
 * the controls sit low where a thumb reaches.
 *
 * Nothing here is remembered locally. Every move is written through to the server as it
 * happens, which is what makes a dropped connection or a dead battery cost nothing but the
 * walk back to the app (FR-13, UC-9.7).
 */
@Component({
  selector: 'app-cook',
  imports: [RouterLink, TimerComponent, VerdictComponent],
  templateUrl: './cook.component.html',
  styleUrl: './cook.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CookComponent {
  private readonly cooking = inject(CookingService);
  private readonly router = inject(Router);
  private readonly sessionId = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));

  protected readonly session = signal<SessionView | null>(null);
  protected readonly missing = signal(false);

  /**
   * Whether a change is still with the server.
   *
   * The controls are disabled while it is, which is not about protecting the backend —
   * moving to a step is idempotent — but about what the cook sees. Two taps on *Next*
   * before the first answer arrives both ask for the same step, so a cook who taps twice
   * moves once and concludes the button is broken.
   */
  protected readonly busy = signal(false);

  /** What the cook has already got ready. Ticks live here and nowhere else: a prep list is
   *  a glance at what is left, not a fact about the meal worth a table of its own. */
  private readonly done = signal<ReadonlySet<string>>(new Set());

  protected readonly attentionNote = attentionNote;
  protected readonly asWritten = Sizing.as_written;
  protected readonly unscalable = Sizing.unscalable;
  protected readonly completed = SessionOutcome.completed;

  /** Where the cook is: the prep list, or one step. */
  protected readonly step = computed<GuidedStepView | null>(() => {
    const session = this.session();
    if (session === null || session.at_step === null || session.at_step === undefined) {
      return null;
    }
    return session.steps.find((one) => one.position === session.at_step) ?? null;
  });

  /** "Step 2 of 6" — counted over the steps for tonight, which is what the cook is doing. */
  protected readonly place = computed(() => {
    const session = this.session();
    const step = this.step();
    if (session === null || step === null) {
      return { at: 0, of: 0 };
    }
    return { at: session.steps.indexOf(step) + 1, of: session.steps.length };
  });

  protected readonly last = computed(() => this.place().at === this.place().of);

  constructor() {
    keepScreenAwake();
    this.load(this.cooking.getSession(this.sessionId));
  }

  protected isDone(prep: string): boolean {
    return this.done().has(prep);
  }

  protected tick(prep: string): void {
    this.done.update((current) => {
      const next = new Set(current);
      if (!next.delete(prep)) {
        next.add(prep);
      }
      return next;
    });
  }

  protected begin(): void {
    this.moveTo(this.session()?.steps[0]?.position ?? 0);
  }

  protected onwards(by: number): void {
    const session = this.session();
    const at = this.place().at - 1;
    if (session === null || at < 0) {
      return;
    }
    const next = session.steps[at + by];
    // Off the front of the list is the prep list, which is a real place to go back to.
    this.moveTo(next === undefined ? null : next.position);
  }

  protected moveTo(position: number | null): void {
    this.load(this.cooking.moveToStep(this.sessionId, { position }));
  }

  protected startTimer(step: GuidedStepView): void {
    this.load(this.cooking.startTimer(this.sessionId, step.position));
  }

  protected pauseTimer(step: GuidedStepView): void {
    this.load(this.cooking.pauseTimer(this.sessionId, step.position));
  }

  protected resetTimer(step: GuidedStepView): void {
    this.load(this.cooking.resetTimer(this.sessionId, step.position));
  }

  protected finish(): void {
    this.load(this.cooking.completeSession(this.sessionId));
  }

  protected giveUp(): void {
    this.cooking.abandonSession(this.sessionId).subscribe({
      next: () => void this.router.navigate(['/plans']),
      error: () => this.missing.set(true),
    });
  }

  private load(request: Observable<SessionView>): void {
    this.busy.set(true);
    request.subscribe({
      next: (session) => {
        this.session.set(session);
        this.missing.set(false);
        this.busy.set(false);
      },
      // Another cook's session, or one that is not there. Absent rather than forbidden,
      // for the same reason the API says so.
      error: () => {
        this.missing.set(true);
        this.busy.set(false);
      },
    });
  }
}
