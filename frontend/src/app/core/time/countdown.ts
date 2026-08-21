import { TimerView } from '@api';

/**
 * How long a timer has counted, at this instant.
 *
 * The server holds *when it started* and *what it had already counted*; this is the
 * subtraction that turns those into a number (ADR-013). Doing it here rather than on the
 * server is what lets a locked phone and a tablet in the other room agree: both are
 * reading the same two instants, not asking for a remainder that was true a moment ago.
 */
export function counted(timer: TimerView, now: number): number {
  if (timer.running_since === null || timer.running_since === undefined) {
    return timer.elapsed_seconds;
  }
  const since = (now - Date.parse(timer.running_since)) / 1000;
  // Clamped. A device clock behind the server's would otherwise show a timer that has
  // counted less than it had before it was started.
  return timer.elapsed_seconds + Math.max(Math.floor(since), 0);
}

/** What is left, which goes negative once a timer has run past its step's duration. */
export function remaining(timer: TimerView, now: number): number {
  return timer.duration_seconds - counted(timer, now);
}

/**
 * A stretch of seconds as a clock reads it — "4:20", "1:02:00".
 *
 * Minutes and seconds rather than the words `minutes()` uses. A cook watching a pan wants
 * to see the seconds move; a cook deciding whether to make the recipe at all wants "1 h
 * 50", and those are different questions on different screens.
 */
export function onTheClock(seconds: number): string {
  const whole = Math.max(Math.floor(Math.abs(seconds)), 0);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  const padded = `${String(minutes).padStart(hours > 0 ? 2 : 1, '0')}:${String(rest).padStart(2, '0')}`;
  return hours > 0 ? `${hours}:${padded}` : padded;
}
