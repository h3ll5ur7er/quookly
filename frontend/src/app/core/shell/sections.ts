/** One destination in the application's navigation. */
export interface Section {
  readonly name: 'home' | 'recipes' | 'plan' | 'shopping' | 'pantry';
  readonly path: string;
  /** A mark for the phone bar, where five words will not fit but five glyphs will. */
  readonly mark: string;
}

/**
 * Where the application goes, in the order a week does.
 *
 * Home is what is happening now, then the recipes it is drawn from, then the week, then the
 * shop, then the shelf. Household, units, theme and language are *not* here: they are
 * chosen once and then left alone, so they sit behind the account rather than taking a
 * permanent share of a phone screen.
 *
 * Shopping earns a place of its own because of where it is used. A cook holding a basket
 * has one hand and thirty seconds, and "open the plan, scroll past the week" is not a
 * thing anybody does in a shop.
 */
export const SECTIONS: readonly Section[] = [
  { name: 'home', path: '/', mark: '◆' },
  { name: 'recipes', path: '/recipes', mark: '☰' },
  { name: 'plan', path: '/plans', mark: '▤' },
  { name: 'shopping', path: '/shopping', mark: '✓' },
  { name: 'pantry', path: '/pantry', mark: '▦' },
];

export function sectionLabel(name: Section['name']): string {
  switch (name) {
    case 'home':
      return $localize`:@@navHome:Home`;
    case 'recipes':
      return $localize`:@@navRecipes:Recipes`;
    case 'plan':
      return $localize`:@@navPlans:Plan`;
    case 'shopping':
      return $localize`:@@navShopping:Shopping`;
    case 'pantry':
      return $localize`:@@navPantry:Pantry`;
  }
}
