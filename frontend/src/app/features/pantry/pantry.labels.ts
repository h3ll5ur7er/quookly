import { Freshness, StockLotView, WasteReason } from '@api';
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
