import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { TimingView } from '@api';
import { span } from './duration';

/**
 * How long a recipe takes, as the two questions a cook is actually asking.
 *
 * *Can I do this tonight?* is hands-on time. *When do we eat?* is total time. Every
 * recipe site answers with one figure, and one figure answers whichever question the
 * reader was not asking: a cake shown as "1 h 50" reads as a weekend project when it is a
 * Tuesday one with a gap in the middle.
 *
 * Work done the day before gets neither number and a line of its own. Folded into the
 * total, soaking beans overnight would make an ordinary dish read as a nine-hour ordeal;
 * left out silently, somebody starts dinner at six and finds the beans wanted starting
 * yesterday (ADR-037).
 */
@Component({
  selector: 'app-timing',
  templateUrl: './timing.component.html',
  styleUrl: './timing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TimingComponent {
  readonly timing = input.required<TimingView>();

  /** Set on a list row, where the labels are more words than a scanning eye wants. */
  readonly compact = input(false);

  protected readonly span = span;
}
