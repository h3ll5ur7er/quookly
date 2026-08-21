import { Reason } from '@api';

/**
 * Why a recipe is where it is in the list.
 *
 * A ranked list that only reordered itself would be asking to be trusted rather than
 * earning it — so each suggestion says what it is for. The wording is about the cook's
 * situation, not about the algorithm: "you have everything", never "coverage 100%".
 */
export function reasonLabel(reason: Reason): string {
  switch (reason) {
    case Reason.uses_soon:
      return $localize`:@@reasonUsesSoon:uses something up`;
    case Reason.have_everything:
      return $localize`:@@reasonHaveEverything:you have everything`;
    case Reason.have_most:
      return $localize`:@@reasonHaveMost:you have most of it`;
    case Reason.not_for_everyone:
      return $localize`:@@reasonNotForEveryone:not for everyone`;
  }
}

/** The one reason that is a warning rather than an encouragement. */
export function isWarning(reason: Reason): boolean {
  return reason === Reason.not_for_everyone;
}
