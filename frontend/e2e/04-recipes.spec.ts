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
  await expect(page).toHaveURL(/\/recipes$/);
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
    await expect(page.getByText('30 min')).toBeVisible();
    await expect(page.getByText('1800')).toHaveCount(0);
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
    await page.getByLabel('Colour theme').selectOption('dark');
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
