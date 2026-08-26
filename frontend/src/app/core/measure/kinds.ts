import { IngredientKind } from '@api';

/**
 * What a kind of ingredient is called, for one of them.
 *
 * Singular, because this labels an entry: a registry row is one ingredient and reads
 * "Solid". The plural form is a different sentence — see `kindsLabel`.
 */
export function kindLabel(kind: IngredientKind): string {
  switch (kind) {
    case IngredientKind.powder:
      return $localize`:@@kindOnePowder:Powder`;
    case IngredientKind.liquid:
      return $localize`:@@kindOneLiquid:Liquid`;
    case IngredientKind.solid:
      return $localize`:@@kindOneSolid:Solid`;
    case IngredientKind.countable:
      return $localize`:@@kindOneCountable:Countable`;
  }
}

/**
 * The same kinds, as a class of things.
 *
 * Used where the sentence is about all of them at once — "Powders: grams" in unit
 * preferences. Kept beside the singular so the vocabulary has one home rather than a
 * switch statement in every component that names a kind.
 */
export function kindsLabel(kind: IngredientKind): string {
  switch (kind) {
    case IngredientKind.powder:
      return $localize`:@@kindPowder:Powders`;
    case IngredientKind.liquid:
      return $localize`:@@kindLiquid:Liquids`;
    case IngredientKind.solid:
      return $localize`:@@kindSolid:Solids`;
    case IngredientKind.countable:
      return $localize`:@@kindCountable:Countable things`;
  }
}
