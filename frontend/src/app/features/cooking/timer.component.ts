import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
} from '@angular/core';
import { TimerView } from '@api';
import { readyToSound, sound } from '../../core/screen/alarm';
import { everySecond } from '../../core/time/clock';
import { onTheClock, remaining } from '../../core/time/countdown';

/**
 * One step's timer, counting down from what the server said.
 *
 * The client ticks; it is not the source of truth. Every second it re-reads the same two
 * instants the server holds — when the timer was last started, and what it had already
 * counted — so a phone that locked, a tab that slept, and a tablet in the other room all
 * arrive at the same number (ADR-013).
 *
 * It counts *past* zero rather than stopping there. A pan does not stop cooking because a
 * timer ran out, and "+2:10" is the number a cook needs when they come back to it.
 */
@Component({
  selector: 'app-timer',
  templateUrl: './timer.component.html',
  styleUrl: './timer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TimerComponent {
  readonly duration = input.required<number>();
  readonly timer = input<TimerView | null>(null);

  /** Set when there is no connection. A timer the server cannot stamp is a timer that
   *  would lose however long the network was down (ADR-013). */
  readonly stranded = input(false);

  // Past tense, and not `start`/`pause`: an output named for a DOM event shadows it.
  readonly started = output<void>();
  readonly paused = output<void>();
  readonly cleared = output<void>();

  private readonly now = everySecond();

  /** Seconds left, negative once it has run past. */
  protected readonly left = computed(() => {
    const running = this.timer();
    return running === null || running === undefined
      ? this.duration()
      : remaining(running, this.now());
  });

  protected readonly running = computed(() => {
    const timer = this.timer();
    return timer != null && timer.running_since != null;
  });

  protected readonly over = computed(() => this.left() < 0);

  protected readonly display = computed(() => {
    const left = this.left();
    return left < 0 ? `+${onTheClock(left)}` : onTheClock(left);
  });

  /** Whether the cook has been told. Reset by anything that puts time back on the clock. */
  private readonly announced = signal(false);

  constructor() {
    effect(() => {
      if (!this.over()) {
        this.announced.set(false);
        return;
      }
      // Once per expiry, not once per second. A timer that buzzes every tick is a timer
      // that gets silenced, and then the next one is not heard either.
      if (!this.announced() && this.running()) {
        this.announced.set(true);
        sound();
      }
    });
  }

  protected toggle(): void {
    if (this.running()) {
      this.paused.emit();
      return;
    }
    // The gesture a browser needs before it will let a page make a sound. Asked for here,
    // when the cook taps start, rather than when the timer runs out and it is too late.
    readyToSound();
    this.started.emit();
  }
}
