import { Meal, Sizing, SlotView } from '@api';

/** In the order a day runs, which is the order a plan is read in. */
export const MEALS: readonly Meal[] = [Meal.breakfast, Meal.lunch, Meal.dinner, Meal.snack];

export function mealLabel(meal: Meal): string {
  switch (meal) {
    case Meal.breakfast:
      return $localize`:@@mealBreakfast:Breakfast`;
    case Meal.lunch:
      return $localize`:@@mealLunch:Lunch`;
    case Meal.dinner:
      return $localize`:@@mealDinner:Dinner`;
    case Meal.snack:
      return $localize`:@@mealSnack:Snack`;
  }
}

/**
 * What a cook needs told about how this meal was sized, or nothing.
 *
 * Only `unscalable` earns a note. "Nobody is coming yet" is already visible — the guest
 * list on the same row says so — and saying it twice would train a cook to read past the
 * notes that do matter.
 */
export function sizingNote(slot: SlotView): string | null {
  if (slot.sizing !== Sizing.unscalable) {
    return null;
  }
  return $localize`:@@planUnscalable:This recipe does not say how many it serves, so the list is for one batch.`;
}

/** Who is coming, or that nobody has said — which is not the same as nobody coming. */
export function attending(slot: SlotView): string {
  return slot.attendees.length === 0
    ? $localize`:@@planNobodyYet:Nobody said yet`
    : slot.attendees.join(', ');
}
