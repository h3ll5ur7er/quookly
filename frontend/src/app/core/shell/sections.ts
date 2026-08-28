/** One destination in the application's navigation. */
export interface Section {
  readonly name: 'home' | 'recipes' | 'plan' | 'shopping' | 'pantry' | 'academy';
  readonly path: string;
  /**
   * Shown only where there is a column to show it in.
   *
   * A phone bar holds five targets and a sixth costs the others a whole word — "Shoppi…"
   * is what six looks like. The sidebar has the opposite problem: five rows and half a
   * laptop screen of nothing under them.
   */
  readonly wide?: boolean;
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
 *
 * The Academy comes last and only on a wide screen. It is read rather than done — nobody
 * opens it in the middle of a shop — but it is a whole section of the product whose only
 * ways in were a recipe step's underlined word and a row inside Settings (W1).
 */
export const SECTIONS: readonly Section[] = [
  { name: 'home', path: '/' },
  { name: 'recipes', path: '/recipes' },
  { name: 'plan', path: '/plans' },
  { name: 'shopping', path: '/shopping' },
  { name: 'pantry', path: '/pantry' },
  { name: 'academy', path: '/academy', wide: true },
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
    case 'academy':
      return $localize`:@@navAcademy:Academy`;
  }
}
