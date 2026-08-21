import { SetupStep } from '@api';

/** In the order they are worth asking for; who is eating is what the product is about. */
export const SETUP_STEPS: readonly SetupStep[] = [
  SetupStep.household,
  SetupStep.constraints,
  SetupStep.units,
  SetupStep.locale,
];

export function stepTitle(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return $localize`:@@setupHouseholdTitle:Who you cook for`;
    case SetupStep.constraints:
      return $localize`:@@setupConstraintsTitle:What they avoid`;
    case SetupStep.units:
      return $localize`:@@setupUnitsTitle:How you measure`;
    case SetupStep.locale:
      return $localize`:@@setupLocaleTitle:Your language`;
  }
}

/** Why it is worth doing, which is the part a checklist usually leaves out. */
export function stepWhy(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return $localize`:@@setupHouseholdWhy:Recipes are scaled to the people at your table, not to a head count.`;
    case SetupStep.constraints:
      return $localize`:@@setupConstraintsWhy:Allergies, intolerances and dislikes. Every recipe is then checked against them.`;
    case SetupStep.units:
      return $localize`:@@setupUnitsWhy:Grams or ounces, millilitres or decilitres — per kind of ingredient.`;
    case SetupStep.locale:
      return $localize`:@@setupLocaleWhy:Kept with your account, so it follows you to your next device.`;
  }
}

export function stepAction(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return $localize`:@@setupHouseholdAction:Add someone`;
    case SetupStep.constraints:
      return $localize`:@@setupConstraintsAction:Record what they avoid`;
    case SetupStep.units:
      return $localize`:@@setupUnitsAction:Choose units`;
    case SetupStep.locale:
      return $localize`:@@setupLocaleAction:Choose a language`;
  }
}

/**
 * How to answer the question without having anything to record.
 *
 * The one piece of setup that is stored, because nothing else can tell a household where
 * genuinely nobody has a restriction from one nobody has been asked about (FR-15).
 */
export function stepDecline(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return $localize`:@@setupHouseholdDecline:I cook for nobody in particular`;
    case SetupStep.constraints:
      return $localize`:@@setupConstraintsDecline:Nobody avoids anything`;
    case SetupStep.units:
      return $localize`:@@setupUnitsDecline:The defaults suit me`;
    case SetupStep.locale:
      return $localize`:@@setupLocaleDecline:The current language suits me`;
  }
}

/** What a declared step says afterwards, so a tick does not lose which answer was given. */
export function stepDeclared(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return $localize`:@@setupHouseholdDeclared:You said you cook for nobody in particular.`;
    case SetupStep.constraints:
      return $localize`:@@setupConstraintsDeclared:You said nobody avoids anything.`;
    case SetupStep.units:
      return $localize`:@@setupUnitsDeclared:You kept the default units.`;
    case SetupStep.locale:
      return $localize`:@@setupLocaleDeclared:You kept the current language.`;
  }
}

export function stepRoute(step: SetupStep): string {
  switch (step) {
    case SetupStep.household:
      return '/household/new';
    case SetupStep.constraints:
      return '/household';
    case SetupStep.units:
    case SetupStep.locale:
      return '/settings';
  }
}
