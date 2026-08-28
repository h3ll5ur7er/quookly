import { IngredientKind } from '@api';

/**
 * The units worth offering, per kind of ingredient.
 *
 * A subset of what the server accepts. `MeasureEngine` knows about teaspoons, metric cups
 * and two kinds of fluid ounce; offering nineteen options to somebody putting the shopping
 * away is a worse kind of completeness than offering four.
 *
 * Symbols rather than names, because a symbol is what the API takes and what is printed on
 * the packet. They are deliberately not translated: "g" is "g" in all three shipped
 * languages, and a translated unit would no longer be the string the server parses.
 *
 * One copy, shared by the settings screen and the pantry. Two would be two chances for one
 * of them to learn about decilitres and the other not.
 */
const BY_KIND: Record<IngredientKind, readonly string[]> = {
  [IngredientKind.powder]: ['g', 'kg', 'oz', 'lb'],
  [IngredientKind.solid]: ['g', 'kg', 'oz', 'lb'],
  [IngredientKind.liquid]: ['ml', 'dl', 'l', 'fl oz (US)'],
  [IngredientKind.countable]: ['piece'],
};

export function unitsFor(kind: IngredientKind): readonly string[] {
  return BY_KIND[kind] ?? BY_KIND[IngredientKind.solid];
}

/**
 * What to offer first for this kind, before the cook's own preference is known.
 *
 * A countable is counted, and has nothing else worth offering: six eggs are six eggs. Egg
 * white by the gram is a different registry entry, and it is not a countable.
 */
export function defaultUnitFor(kind: IngredientKind): string {
  return unitsFor(kind)[0];
}

/**
 * A stored decimal as it reads.
 *
 * The backend keeps densities to four places because the arithmetic needs them, so
 * "1.3800" is what crosses the wire. Nobody writes a density that way, and a screen that
 * prints stored precision is showing its schema rather than its answer.
 */
export function tidy(value: string): string {
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}
