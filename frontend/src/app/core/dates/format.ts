import { preferredLocale } from '../locale/locale.store';

/**
 * Dates as this cook's language writes them.
 *
 * `Intl` rather than Angular's date pipe: the application fixes its locale before
 * bootstrap and never registers Angular's locale data (ADR-025), so the pipe would
 * silently format a Swiss cook's dates the American way.
 *
 * The input is an ISO day — `2026-08-24` — parsed at midnight *local* time. Parsing it as
 * an instant makes it UTC, and a date west of Greenwich then reads as the day before.
 */
function on(iso: string): Date {
  return new Date(`${iso}T00:00:00`);
}

/** "24 Aug 2026". For a date that has to be exact, like what is printed on a packet. */
export function day(iso: string): string {
  return new Intl.DateTimeFormat(preferredLocale(), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(on(iso));
}

/**
 * "Monday 24 Aug". For a week, where the weekday is what a cook navigates by and the
 * year is never in question.
 */
export function weekday(iso: string): string {
  return new Intl.DateTimeFormat(preferredLocale(), {
    weekday: 'long',
    day: 'numeric',
    month: 'short',
  }).format(on(iso));
}

/** "24–30 Aug 2026", or the long way round when a period crosses a month or a year. */
export function period(startsOn: string, endsOn: string): string {
  const formatter = new Intl.DateTimeFormat(preferredLocale(), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
  const range = (formatter as { formatRange?: (a: Date, b: Date) => string }).formatRange;
  return range === undefined
    ? `${formatter.format(on(startsOn))} – ${formatter.format(on(endsOn))}`
    : range.call(formatter, on(startsOn), on(endsOn));
}
