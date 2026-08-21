import { Nutrient } from '@api';

/**
 * What each figure is called, in the order a label prints them.
 *
 * The order is EU Regulation 1169/2011's, which is what a cook here reads on a packet:
 * energy first, then fat with its saturates indented under it, then carbohydrate with its
 * sugars. Printing them in any other order would make the panel unfamiliar for no gain.
 */
export const NUTRIENTS: readonly Nutrient[] = [
  Nutrient.energy_kj,
  Nutrient.energy_kcal,
  Nutrient.fat,
  Nutrient.saturates,
  Nutrient.carbohydrate,
  Nutrient.sugars,
  Nutrient.fibre,
  Nutrient.protein,
  Nutrient.salt,
];

/** The two figures a label prints on one line, joined by a slash. */
export const ENERGY: ReadonlySet<Nutrient> = new Set([Nutrient.energy_kj, Nutrient.energy_kcal]);

/** The ones a label sets underneath the figure they are part of. */
export const OF_WHICH: ReadonlySet<Nutrient> = new Set([Nutrient.saturates, Nutrient.sugars]);

export function nutrientLabel(nutrient: Nutrient): string {
  switch (nutrient) {
    case Nutrient.energy_kj:
    case Nutrient.energy_kcal:
      return $localize`:@@nutrientEnergy:Energy`;
    case Nutrient.fat:
      return $localize`:@@nutrientFat:Fat`;
    case Nutrient.saturates:
      return $localize`:@@nutrientSaturates:of which saturates`;
    case Nutrient.carbohydrate:
      return $localize`:@@nutrientCarbohydrate:Carbohydrate`;
    case Nutrient.sugars:
      return $localize`:@@nutrientSugars:of which sugars`;
    case Nutrient.fibre:
      return $localize`:@@nutrientFibre:Fibre`;
    case Nutrient.protein:
      return $localize`:@@nutrientProtein:Protein`;
    case Nutrient.salt:
      return $localize`:@@nutrientSalt:Salt`;
  }
}
