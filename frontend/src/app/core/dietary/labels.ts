import { AgeBand, Allergen, ConstraintView, Outcome, Severity } from '@api';

/** Youngest first, which is the order a person would read them in. */
export const AGE_BANDS: readonly AgeBand[] = [
  AgeBand.infant,
  AgeBand.child,
  AgeBand.adult,
  AgeBand.elderly,
];

/** Most serious first: the one that matters most should not be the one scrolled to. */
export const SEVERITIES: readonly Severity[] = [
  Severity.medical,
  Severity.ethical,
  Severity.intolerance,
  Severity.preference,
];

/** The fourteen declarable classes, in the order the regulation lists them. */
export const ALLERGENS: readonly Allergen[] = [
  Allergen.gluten,
  Allergen.crustaceans,
  Allergen.eggs,
  Allergen.fish,
  Allergen.peanuts,
  Allergen.soybeans,
  Allergen.milk,
  Allergen.tree_nuts,
  Allergen.celery,
  Allergen.mustard,
  Allergen.sesame,
  Allergen.sulphites,
  Allergen.lupin,
  Allergen.molluscs,
];

export function ageBandLabel(band: AgeBand): string {
  switch (band) {
    case AgeBand.infant:
      return $localize`:@@ageBandInfant:Infant`;
    case AgeBand.child:
      return $localize`:@@ageBandChild:Child`;
    case AgeBand.adult:
      return $localize`:@@ageBandAdult:Adult`;
    case AgeBand.elderly:
      return $localize`:@@ageBandElderly:Elderly`;
  }
}

/** What choosing this severity will actually do, rather than what it is called. */
export function severityLabel(severity: Severity): string {
  switch (severity) {
    case Severity.medical:
      return $localize`:@@severityMedical:Medical — never serve this`;
    case Severity.ethical:
      return $localize`:@@severityEthical:Ethical or religious — never serve this`;
    case Severity.intolerance:
      return $localize`:@@severityIntolerance:Intolerance — warn me`;
    case Severity.preference:
      return $localize`:@@severityPreference:Dislike — just note it`;
  }
}

/**
 * The one word a chip carries alongside its colour.
 *
 * Never colour alone: for a dietary warning that is a safety rule rather than a
 * preference (ADR-006), and a red chip means nothing to somebody who cannot see red.
 */
export function severityMark(severity: Severity): string {
  switch (severity) {
    case Severity.medical:
    case Severity.ethical:
      return $localize`:@@severityMarkNever:never`;
    case Severity.intolerance:
      return $localize`:@@severityMarkWarn:warn`;
    case Severity.preference:
      return $localize`:@@severityMarkNote:note`;
  }
}

export function allergenLabel(allergen: Allergen): string {
  switch (allergen) {
    case Allergen.gluten:
      return $localize`:@@allergenGluten:Cereals containing gluten`;
    case Allergen.crustaceans:
      return $localize`:@@allergenCrustaceans:Crustaceans`;
    case Allergen.eggs:
      return $localize`:@@allergenEggs:Eggs`;
    case Allergen.fish:
      return $localize`:@@allergenFish:Fish`;
    case Allergen.peanuts:
      return $localize`:@@allergenPeanuts:Peanuts`;
    case Allergen.soybeans:
      return $localize`:@@allergenSoybeans:Soybeans`;
    case Allergen.milk:
      return $localize`:@@allergenMilk:Milk`;
    case Allergen.tree_nuts:
      return $localize`:@@allergenTreeNuts:Tree nuts`;
    case Allergen.celery:
      return $localize`:@@allergenCelery:Celery`;
    case Allergen.mustard:
      return $localize`:@@allergenMustard:Mustard`;
    case Allergen.sesame:
      return $localize`:@@allergenSesame:Sesame`;
    case Allergen.sulphites:
      return $localize`:@@allergenSulphites:Sulphur dioxide and sulphites`;
    case Allergen.lupin:
      return $localize`:@@allergenLupin:Lupin`;
    case Allergen.molluscs:
      return $localize`:@@allergenMolluscs:Molluscs`;
  }
}

/**
 * What a constraint avoids, as a person would say it.
 *
 * An ingredient constraint holds a registry slug, which is a key rather than a word. It
 * is unhyphenated for display; a locale-aware name would mean a lookup per constraint,
 * and the slug is close enough to English to be read until that exists.
 */
export function outcomeLabel(outcome: Outcome): string {
  switch (outcome) {
    case Outcome.unsuitable:
      return $localize`:@@outcomeUnsuitable:Not suitable`;
    case Outcome.unknown:
      return $localize`:@@outcomeUnknown:Not enough is known`;
    case Outcome.caution:
      return $localize`:@@outcomeCaution:Take care`;
    case Outcome.suitable:
      return $localize`:@@outcomeSuitable:Suits everyone`;
  }
}

/** What the cook should do about it, which is the part a verdict alone does not say. */
export function outcomeExplanation(outcome: Outcome): string {
  switch (outcome) {
    case Outcome.unsuitable:
      return $localize`:@@outcomeUnsuitableWhy:Somebody at your table cannot eat this.`;
    case Outcome.unknown:
      return $localize`:@@outcomeUnknownWhy:An ingredient has never been checked for allergens, so this cannot be called safe. It has not been called unsafe either.`;
    case Outcome.caution:
      return $localize`:@@outcomeCautionWhy:Somebody at your table has an intolerance to something in this.`;
    case Outcome.suitable:
      return $localize`:@@outcomeSuitableWhy:Nothing here conflicts with what you have recorded.`;
  }
}

export function constraintLabel(constraint: ConstraintView): string {
  if (constraint.allergen) {
    return allergenLabel(constraint.allergen);
  }
  return (constraint.ingredient_slug ?? '').replace(/-/g, ' ');
}
