import { SpanView } from '@api';

/**
 * How long, in words a cook reads rather than the seconds a timer counts.
 *
 * Rounded to the minute. A recipe that claims 12 min 30 s of chopping is claiming a
 * precision nobody measured, and the extra digits cost more attention than they carry.
 */
export function minutes(seconds: number): string {
  const total = Math.round(seconds / 60);
  if (total < 60) {
    return $localize`:@@durationMinutes:${total}:minutes: min`;
  }
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0
    ? $localize`:@@durationHours:${hours}:hours: h`
    : $localize`:@@durationHoursMinutes:${hours}:hours: h ${rest}:minutes: min`;
}

/**
 * A stretch of time, saying so when it is only the floor.
 *
 * A step that forgot to give a duration does not make the recipe shorter — it makes the
 * answer a lower bound, and a number printed without that mark is a number somebody plans
 * an evening around (ADR-037).
 */
export function span(value: SpanView): string {
  const written = minutes(value.seconds);
  return value.at_least ? $localize`:@@durationAtLeast:at least ${written}:duration:` : written;
}
