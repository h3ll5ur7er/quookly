import { Attention } from '@api';

/**
 * What a step asks of the cook, where that is worth saying.
 *
 * Nothing for hands-on work, which is what a step is unless it says otherwise — marking
 * every one of them would put a badge on the whole method and single out nothing. Same
 * rule as a suitable verdict: the label exists to point at the exception.
 */
export function attentionNote(attention: Attention): string | null {
  switch (attention) {
    case Attention.hands_on:
      return null;
    case Attention.waiting:
      return $localize`:@@attentionWaiting:you can walk away`;
    case Attention.ahead:
      return $localize`:@@attentionAhead:do this the day before`;
  }
}
