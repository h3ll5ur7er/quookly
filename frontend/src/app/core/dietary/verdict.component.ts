import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Outcome, VerdictView } from '@api';
import { outcomeExplanation, outcomeLabel, severityMark } from './labels';

/**
 * Whether the people at the table can eat this, and why.
 *
 * Shown without being asked for: the system already knows, and making a cook apply a
 * filter to learn it would be the worse interface.
 *
 * *Unknown* is deliberately not styled like *suitable*. It is the outcome that exists
 * because silence about a nut is not an absence of nuts (ADR-006), and a verdict that
 * looks reassuring is worse than no verdict at all.
 */
@Component({
  selector: 'app-verdict',
  templateUrl: './verdict.component.html',
  styleUrl: './verdict.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VerdictComponent {
  readonly verdict = input.required<VerdictView>();

  protected readonly outcomeLabel = outcomeLabel;
  protected readonly outcomeExplanation = outcomeExplanation;
  protected readonly severityMark = severityMark;
  protected readonly suitable = Outcome.suitable;
}
