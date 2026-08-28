import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SessionOutcome } from '@api';

/**
 * The end of a session: what happened, and the way back.
 *
 * Its own component because the cooking screen's stylesheet sits on the 8 kB component
 * budget and the finished screen shares nothing with the step view above it — different
 * posture, different type, different job. Splitting it is what made room for the step
 * view to say what temperature the oven is at (C2).
 */
@Component({
  selector: 'app-cook-finished',
  imports: [RouterLink],
  template: `
    <section class="done">
      @if (completed()) {
        <p class="done__mark" aria-hidden="true">✓</p>
        <h2 i18n="@@cookFinishedHeading">That is dinner</h2>
        <p class="done__lede" i18n="@@cookFinished">
          What this meal was holding has come out of your pantry.
        </p>
      } @else {
        <h2 i18n="@@cookStoppedHeading">You stopped this one</h2>
        <p class="done__lede" i18n="@@cookStopped">
          Nothing came out of your pantry. The meal is still on your plan.
        </p>
      }
      <a class="done__back" routerLink="/plans" i18n="@@cookBackToPlan">Back to the plan</a>
    </section>
  `,
  styles: `
    .done {
      display: grid;
      flex: 1;
      justify-items: center;
      align-content: center;
      gap: var(--space-3);
      padding: var(--space-5) var(--space-4);
      text-align: center;
    }

    .done__mark {
      display: grid;
      place-items: center;
      inline-size: 4rem;
      block-size: 4rem;
      margin: 0;
      border-radius: var(--radius-full);
      background: var(--success);
      color: var(--on-success);
      font-size: var(--text-2xl);
    }

    .done__lede {
      margin: 0;
      color: var(--on-surface-muted);
    }

    .done__back {
      display: grid;
      place-items: center;
      min-height: 48px;
      margin-top: var(--space-4);
      padding-inline: var(--space-5);
      border-radius: var(--radius-md);
      background: var(--primary);
      color: var(--on-primary);
      font-weight: 600;
      text-decoration: none;
    }
  `,
  host: { class: 'cook__body' },
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CookFinishedComponent {
  readonly outcome = input.required<SessionOutcome>();

  /** Eaten or not. The difference between the two is the difference between a meal and not. */
  protected readonly completed = computed(() => this.outcome() === SessionOutcome.completed);
}
