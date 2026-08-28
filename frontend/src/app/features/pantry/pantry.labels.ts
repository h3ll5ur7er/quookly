import { Freshness, PantryEntry, StockLotView, WasteReason } from '@api';
import { day } from '../../core/dates/format';

export { day };

/**
 * How soon a packet wants using, in words.
 *
 * Words rather than a count of days, because "in 2 days" is a number to work out and
 * "the day after tomorrow" is a plan. Null where there is nothing pressing to say: a
 * bag of flour with no date, or one that is still weeks off, does not need a chip
 * telling the cook so.
 *
 * Written out per case rather than as a plural rule, in the same way as the recipe
 * timings: the runtime catalogues hold flat messages, and an ICU plural would have
 * nowhere to be translated (ADR-025).
 */
export function urgency(lot: StockLotView): string | null {
  const days = lot.days_remaining;
  if (days === null) {
    return null;
  }
  if (lot.freshness === Freshness.past) {
    return days === -1
      ? $localize`:@@pantryDueYesterday:Was due yesterday`
      : $localize`:@@pantryDueDaysAgo:Was due ${-days}:count: days ago`;
  }
  if (lot.freshness !== Freshness.soon) {
    return null;
  }
  if (days === 0) {
    return $localize`:@@pantryDueToday:Use today`;
  }
  if (days === 1) {
    return $localize`:@@pantryDueTomorrow:Use by tomorrow`;
  }
  return $localize`:@@pantryDueInDays:Use within ${days}:count: days`;
}

/**
 * How pressing a packet is, in four steps rather than in two.
 *
 * "Use within 2 days" and "use within 20 days" were the same grey line with different
 * words in it, so a shelf could not be scanned — only read (N2). The words still say it;
 * this is what lets the eye find them first.
 */
export function band(lot: StockLotView): 'past' | 'now' | 'soon' | 'later' {
  const days = lot.days_remaining;
  if (lot.freshness === Freshness.past) {
    return 'past';
  }
  if (days === null) {
    return 'later';
  }
  if (days <= 2) {
    return 'now';
  }
  return days <= 7 ? 'soon' : 'later';
}

/**
 * The nearest date any of an entry's packets carries, in days.
 *
 * Null where none of them is dated. An entry is as pressing as its most pressing packet:
 * half a kilo of flour with no date does not make the open bag beside it less urgent.
 */
export function soonest(entry: PantryEntry): number | null {
  const dated = entry.lots
    .map((lot) => lot.days_remaining)
    .filter((days): days is number => days !== null);
  return dated.length === 0 ? null : Math.min(...dated);
}

/** Commonest first: most of what gets binned went off or ran out of date. */
export const WASTE_REASONS: readonly WasteReason[] = [
  WasteReason.spoiled,
  WasteReason.expired,
  WasteReason.uneaten,
  WasteReason.damaged,
  WasteReason.other,
];

export function wasteReasonLabel(reason: WasteReason): string {
  switch (reason) {
    case WasteReason.spoiled:
      return $localize`:@@wasteSpoiled:It had gone off`;
    case WasteReason.expired:
      return $localize`:@@wasteExpired:It was past its date`;
    case WasteReason.uneaten:
      return $localize`:@@wasteUneaten:Cooked but not eaten`;
    case WasteReason.damaged:
      return $localize`:@@wasteDamaged:Spilled, burnt or dropped`;
    case WasteReason.other:
      return $localize`:@@wasteOther:Something else`;
  }
}
