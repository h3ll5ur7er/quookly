import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The recipe screens, on a phone, against a real instance.
 *
 * The instance already has starter recipes — claiming it installs them. This adds one
 * more through the import endpoint, written in US cups, so the conversion the product
 * exists for is visible on screen rather than only in a unit test.
 */

const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
  password: 'a-sufficiently-long-password',
};

// Deliberately a **format 1** document. Format 2 added `serves`; keeping this one at 1
// means every run checks that a file a self-hoster exported before the change still
// imports, which is the whole point of reading more than one version.
const DOCUMENT = {
  quookly: 1,
  exported_at: '2026-08-20T12:00:00Z',
  locale: 'en-GB',
  ingredients: [
    { slug: 'plain-flour', kind: 'powder', density: '0.53', names: ['plain flour'] },
    { slug: 'whole-milk', kind: 'liquid', density: '1.03', names: ['whole milk'] },
    { slug: 'egg', kind: 'countable', density: null, names: ['egg'] },
    { slug: 'unsalted-butter', kind: 'solid', density: '0.911', names: ['unsalted butter'] },
  ],
  recipes: [
    {
      title: 'American Pancakes',
      summary: 'Batter, pan, patience.',
      yield_magnitude: '12',
      yield_unit: 'piece',
      provenance: 'authored',
      lines: [
        { ingredient: 'plain-flour', magnitude: '1', unit: 'cup (US)', preparation: 'sifted' },
        { ingredient: 'whole-milk', magnitude: '300', unit: 'ml' },
        { ingredient: 'egg', magnitude: '2', unit: 'piece', optional: false },
        {
          ingredient: 'unsalted-butter',
          magnitude: '40',
          unit: 'g',
          preparation: 'melted',
          optional: true,
        },
      ],
      steps: [
        { instruction: 'Whisk the dry ingredients together.' },
        { instruction: 'Beat in the milk and eggs, then rest the batter.', duration_seconds: 1800 },
        { instruction: 'Fry until the edges set and bubbles hold.', temperature_celsius: 180 },
      ],
    },
  ],
};

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  const signUp = await request.post('/api/v1/accounts', { data: COOK });
  const token = signUp.ok()
    ? (await signUp.json()).token
    : (
        await (
          await request.post('/api/v1/accounts/sign-in', {
            data: { email: COOK.email, password: COOK.password },
          })
        ).json()
      ).token;

  const imported = await request.post('/api/v1/recipes/import', {
    data: DOCUMENT,
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(imported.ok(), await imported.text()).toBe(true);
});

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
  // Signing in lands on Home; this file is about the recipes.
  await page.goto('/recipes');
});

test.describe('the recipe list', () => {
  test('shows what the cook has', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Recipes' })).toBeVisible();
    await expect(page.getByText('American Pancakes')).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.screenshot({ path: 'e2e/screenshots/recipe-list.png', fullPage: true });
  });
});

test.describe('a recipe', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByText('American Pancakes').click();
    await expect(page.getByRole('heading', { name: 'American Pancakes' })).toBeVisible();
  });

  test('shows a cup of flour in grams', async ({ page }) => {
    /* The founding annoyance, on screen. */
    await expect(page.getByText('125 g')).toBeVisible();
    await expect(page.getByText('plain flour')).toBeVisible();
  });

  test('shows a timing as minutes rather than seconds', async ({ page }) => {
    await expect(page.locator('.steps__facts').getByText('30 min')).toBeVisible();
    await expect(page.getByText('1800')).toHaveCount(0);
  });

  test('says how long it takes without claiming to know more than it does', async ({ page }) => {
    /*
     * The document is format 1, which says nothing about what a step asks of the cook, and
     * two of its three steps carry no duration at all. Both numbers therefore read as
     * floors — a bare "30 min" would be a figure somebody plans an evening around.
     *
     * And the resting counts as work, because a document that does not say is read as
     * hands-on. That over-reports the effort rather than under-reporting it, which is the
     * direction that does not make anybody late (ADR-037).
     */
    const timing = page.locator('app-timing').first();
    await expect(timing.getByText('at least 30 min')).toHaveCount(2);
    await expect(timing.getByText('hands-on')).toBeVisible();
    await expect(timing.getByText('total')).toBeVisible();
  });

  test('marks nothing on a recipe that never said what its steps ask', async ({ page }) => {
    await expect(page.locator('.steps__step .fact--quiet')).toHaveCount(0);
  });

  test('writes a preparation as a person would, comma and all', async ({ page }) => {
    /*
     * Two ways this has gone wrong, neither visible to an assertion about the words.
     *
     * "plain flour , sifted" is what inline elements and a template newline produce. And
     * a comma leading the preparation sits at the start of the next line when a long one
     * wraps, under the ingredient it belongs to — so the comma travels with the name.
     */
    const painted = await page.evaluate(() => {
      const name = [...document.querySelectorAll('.lines__name')].find((node) =>
        node.textContent!.includes('plain flour'),
      )!;
      const [ingredient, preparation] = [...name.children] as HTMLElement[];
      return {
        ingredient: ingredient.textContent,
        preparation: preparation.textContent,
        gap: preparation.getBoundingClientRect().left - ingredient.getBoundingClientRect().right,
      };
    });

    expect(painted.ingredient).toBe('plain flour,');
    expect(painted.preparation).toBe('sifted');
    // Measured rather than read: the text content says nothing about what was painted.
    // One word space, not none and not two.
    expect(painted.gap).toBeGreaterThan(1);
    expect(painted.gap).toBeLessThan(12);
  });

  test('marks the optional ingredient', async ({ page }) => {
    await expect(page.getByText('optional')).toBeVisible();
  });

  test('scales when the yield changes', async ({ page }) => {
    await expect(page.getByText('300 ml')).toBeVisible();
    for (let i = 0; i < 6; i++) {
      await page.getByRole('button', { name: 'Fewer' }).click();
    }
    await expect(
      page.getByText('Makes').locator('..').getByText('6', { exact: true }),
    ).toBeVisible();
    await expect(page.getByText('150 ml')).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.screenshot({ path: 'e2e/screenshots/recipe-detail.png', fullPage: true });
    // The picker lives in Settings once somebody is signed in.
    await page.goto('/settings');
    await page.getByLabel('Colour theme').selectOption('dark');
    await page.goBack();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.screenshot({ path: 'e2e/screenshots/recipe-detail-dark.png', fullPage: true });
  });
});

test.describe('how many it feeds', () => {
  /** The "Makes" panel, which is where both numbers live. Scoped, because the recipe
      list behind it carries the same words. */
  function madeAndServed(page: import('@playwright/test').Page) {
    return page.getByRole('region').filter({ has: page.getByRole('heading', { name: 'Makes' }) });
  }

  async function open(page: import('@playwright/test').Page, title: RegExp): Promise<void> {
    await page.goto('/recipes');
    await page.getByRole('link', { name: title }).click();
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
  }

  test('a seeded recipe says so, because twelve pancakes is not four portions', async ({
    page,
  }) => {
    await open(page, /Buttermilk Pancakes/);
    await expect(madeAndServed(page)).toContainText('Serves');
    await expect(madeAndServed(page)).toContainText('4');
    await page.screenshot({ path: 'e2e/screenshots/recipe-serves.png', fullPage: true });
  });

  test('and scales with the batch, so the two numbers never disagree', async ({ page }) => {
    await open(page, /Buttermilk Pancakes/);
    for (let i = 0; i < 12; i++) {
      await page.getByRole('button', { name: 'More' }).click();
    }
    // Twenty-four pancakes, so eight portions.
    await expect(madeAndServed(page)).toContainText('8');
  });

  test('a recipe that never said stays silent about it', async ({ page }) => {
    /* The format 1 import above. Absent is an answer, and a pieces-per-serving figure
       invented for the screen would be a number a cook cannot see is wrong. */
    await open(page, /American Pancakes/);
    await expect(madeAndServed(page)).toContainText('Makes');
    await expect(madeAndServed(page)).not.toContainText('Serves');
  });
});

test.describe('a recipe that says what each step asks of the cook', () => {
  /*
   * The seeded Shortbread, which carries an attention on every step. Fifteen minutes of
   * work spread across an hour and a half of clock — the exact case a single figure
   * describes wrongly in both directions (UC-2.6, ADR-037).
   */
  test.beforeEach(async ({ page }) => {
    await page.getByText('Shortbread').click();
    await expect(page.getByRole('heading', { name: 'Shortbread' })).toBeVisible();
  });

  test('separates the work from the waiting', async ({ page }) => {
    const timing = page.locator('app-timing').first();
    await expect(timing.getByText('15 min')).toBeVisible();
    await expect(timing.getByText('1 h 25 min')).toBeVisible();
    // Both exact: every step said how long it takes, so neither is a floor.
    await expect(timing.getByText('at least')).toHaveCount(0);
  });

  test('marks the steps a cook can walk away from', async ({ page }) => {
    await expect(page.getByText('you can walk away')).toHaveCount(2);
  });

  test('leaves the work unmarked', async ({ page }) => {
    // Four of the six steps are ordinary work. A note on each would mark the whole method.
    await expect(page.locator('.steps__step .fact--quiet')).toHaveCount(2);
  });

  test('says the same thing on the list it says on the page', async ({ page }) => {
    await page.goBack();
    const row = page.locator('.recipes__item').filter({ hasText: 'Shortbread' });
    await expect(row.getByText('15 min')).toBeVisible();
    await expect(row.getByText('hands-on')).toBeVisible();
  });

  test('looks like this', async ({ page }) => {
    await page.screenshot({ path: 'e2e/screenshots/recipe-timing.png', fullPage: true });
  });
});

test.describe('what a recipe contains', () => {
  /*
   * The seeded Shortbread is butter, sugar, flour and salt, and the Swiss table publishes
   * all four — so this one counts whole. The pancakes below do not, which is the more
   * interesting half (UC-2.3, ADR-045).
   */
  test.beforeEach(async ({ page }) => {
    await page.getByText('Shortbread').click();
    await expect(page.getByRole('heading', { name: 'Shortbread' })).toBeVisible();
  });

  test('reads like a packet', async ({ page }) => {
    const panel = page.locator('app-nutrition');
    await expect(panel.getByRole('heading', { name: 'Nutrition' })).toBeVisible();
    await expect(panel.getByText('Per serving')).toBeVisible();
    await expect(panel.getByText('Whole recipe')).toBeVisible();
    await expect(panel.getByRole('rowheader', { name: 'of which saturates' })).toBeVisible();
  });

  test('the figures follow from the quantities', async ({ page }) => {
    /* 225 g of butter at 82.3 g fat per 100 g is 185 g before anything else is added, so
       the whole tray is over that and one of eight servings is well under it. */
    const whole = await page
      .locator('app-nutrition tbody tr')
      .filter({ hasText: 'Fat' })
      .first()
      .locator('td')
      .last()
      .textContent();
    expect(parseFloat(whole!)).toBeGreaterThan(185);
  });

  test('says who measured it', async ({ page }) => {
    /* Mandatory under the Swiss grant, not a courtesy (FR-20). */
    const credit = page.locator('.nutrition__credit a');
    await expect(credit).toContainText('Federal Food Safety and Veterinary Office');
    await expect(credit).toHaveAttribute('href', 'https://naehrwertdaten.ch/');
  });

  test('has no accessibility violations', async ({ page }) => {
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.locator('app-nutrition').scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'e2e/screenshots/recipe-nutrition.png', fullPage: true });
  });
});

test.describe('what a recipe does not say it contains', () => {
  test('names the ingredient no table answers for', async ({ page }) => {
    /* The Swiss database has no baking powder and publishes no portion weight for an egg.
       Both are named, and the totals are marked as floors — a figure that quietly leaves
       out an ingredient is worse than no figure. */
    await page.getByText('Buttermilk Pancakes').click();
    await expect(page.getByRole('heading', { name: 'Buttermilk Pancakes' })).toBeVisible();

    const gap = page.locator('.nutrition__gap');
    await expect(gap).toContainText('At least this much');
    await expect(gap).toContainText('baking powder');
  });
});

test.describe('finding something to cook', () => {
  /*
   * Phase 6's "done when", on screen: what should I cook, answered with something that uses
   * up what is about to go off (UC-3.1, UC-3.3, UC-3.4).
   */
  test('searching finds a recipe by its title', async ({ page }) => {
    await page.getByLabel('Search your recipes').fill('shortbread');
    await expect(page.locator('.recipes__item')).toHaveCount(1);
    await expect(page.locator('.recipes__item')).toContainText('Shortbread');
  });

  test('searching finds a recipe by what is in it', async ({ page }) => {
    /* "What can I do with buttermilk" is a question about ingredients, not titles. */
    await page.getByLabel('Search your recipes').fill('caster sugar');
    await expect(page.locator('.recipes__item').first()).toContainText('Shortbread');
  });

  test('half a word is enough', async ({ page }) => {
    await page.getByLabel('Search your recipes').fill('short');
    await expect(page.locator('.recipes__item').first()).toContainText('Shortbread');
  });

  test('says so when nothing matches rather than looking broken', async ({ page }) => {
    await page.getByLabel('Search your recipes').fill('lobster thermidor');
    await expect(page.getByText('Nothing here matches that')).toBeVisible();
  });

  test('the alphabet is the default, and the other order is a choice', async ({ page }) => {
    /* A cook who came to find a recipe they already have in mind wants the alphabet. */
    await expect(page.getByRole('button', { name: 'A–Z' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Worth cooking' }).click();
    await expect(page.getByRole('button', { name: 'Worth cooking' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  test('an empty kitchen still gets an answer, just not a reason', async ({ page }) => {
    /* Nothing is in the pantry this early in the suite, so nothing has anything to claim.
       The list still comes back — a cook with an empty cupboard is not shown an empty
       screen. What a reason looks like is checked where there is stock, in 09. */
    await page.getByRole('button', { name: 'Worth cooking' }).click();
    await expect(page.locator('.recipes__item').first()).toBeVisible();
    await expect(page.locator('.recipes__reason')).toHaveCount(0);
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.getByRole('button', { name: 'Worth cooking' }).click();
    await expect(page.locator('.recipes__item').first()).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.getByRole('button', { name: 'Worth cooking' }).click();
    await expect(page.locator('.recipes__item').first()).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/recipe-discovery.png', fullPage: true });
  });
});
