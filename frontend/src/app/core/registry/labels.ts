import { Resemblance } from '@api';

/**
 * Why the matcher thinks two names are the same ingredient.
 *
 * The reason is shown beside every suggestion for the same reason a ranked recipe says why
 * it is where it is (ADR-046): a list that only reordered itself would be asking to be
 * trusted rather than earning it. "The same words" is something somebody can check at a
 * glance; a confidence of 0.92 is not.
 */
export function resemblanceLabel(reason: Resemblance): string {
  switch (reason) {
    case Resemblance.same_spelling:
      return $localize`:@@resemblanceSameSpelling:the same spelling`;
    case Resemblance.same_words:
      return $localize`:@@resemblanceSameWords:the same words`;
    case Resemblance.contains:
      return $localize`:@@resemblanceContains:all of these words`;
    case Resemblance.spelling:
      return $localize`:@@resemblanceSpelling:a close spelling`;
  }
}
