import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The recipe screens, on a phone, against a real instance.
 *
 * A recipe is seeded through the import endpoint: it is the only way to get ingredients
 * into a fresh registry today, and it exercises the interchange format at the same time.
 */

const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
  password: 'a-sufficiently-long-password',
};

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
      title: 'Buttermilk Pancakes',
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

  await request.post('/api/v1/recipes/import', {
    data: DOCUMENT,
    headers: { Authorization: `Bearer ${token}` },
  });
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
    await expect(page.getByText('Buttermilk Pancakes')).toBeVisible();
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
    await page.getByText('Buttermilk Pancakes').click();
    await expect(page.getByRole('heading', { name: 'Buttermilk Pancakes' })).toBeVisible();
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

  test('marks the optional ingredient', async ({ page }) => {
    await expect(page.getByText('optional')).toBeVisible();
  });

  test('scales when the yield changes', async ({ page }) => {
    await expect(page.getByText('300 ml')).toBeVisible();
    for (let i = 0; i < 6; i++) {
      await page.getByRole('button', { name: 'Fewer' }).click();
    }
    await expect(page.getByText('Makes').locator('..').getByText('6', { exact: true })).toBeVisible();
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
