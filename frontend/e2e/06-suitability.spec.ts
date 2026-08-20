import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Whether the people at the table can eat this, on the way to a screen (V5, ADR-006).
 *
 * The four outcomes are exercised against a real instance, because the one that matters
 * is *unknown* and the only way it goes wrong is by looking like one of the others.
 */

const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
  password: 'a-sufficiently-long-password',
};

/** An ingredient nobody has ever classified, which is not the same as one that is clear. */
const MYSTERY = {
  quookly: 1,
  exported_at: '2026-08-21T12:00:00Z',
  locale: 'en-GB',
  ingredients: [{ slug: 'mystery-paste', kind: 'solid', density: '1.0', names: ['mystery paste'] }],
  recipes: [
    {
      title: 'Mystery Bake',
      summary: 'One ingredient nobody has looked at.',
      yield_magnitude: '4',
      yield_unit: 'serving',
      provenance: 'authored',
      lines: [{ ingredient: 'mystery-paste', magnitude: '200', unit: 'g' }],
      steps: [{ instruction: 'Bake it and hope.' }],
    },
  ],
};

let token: string;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  const signIn = await request.post('/api/v1/accounts/sign-in', {
    data: { email: COOK.email, password: COOK.password },
  });
  token = (await signIn.json()).token;
  const auth = { Authorization: `Bearer ${token}` };

  await request.post('/api/v1/recipes/import', { data: MYSTERY, headers: auth });

  // Start from a household of exactly one person, so a verdict is about her alone.
  const existing = await (await request.get('/api/v1/eaters', { headers: auth })).json();
  for (const person of existing) {
    await request.delete(`/api/v1/eaters/${person.id}`, { headers: auth });
  }
  await request.post('/api/v1/eaters', {
    data: {
      name: 'Ada',
      age_band: 'adult',
      constraints: [
        { allergen: 'gluten', ingredient_slug: null, severity: 'medical' },
        { allergen: 'milk', ingredient_slug: null, severity: 'intolerance' },
      ],
    },
    headers: auth,
  });
});

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/recipes$/);
});

async function open(page: import('@playwright/test').Page, title: string): Promise<void> {
  await page.goto('/recipes');
  await page.getByText(title, { exact: true }).click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}

test.describe('a recipe somebody cannot eat', () => {
  test('says so, in words', async ({ page }) => {
    await open(page, 'Shortbread');
    await expect(page.getByText('Not suitable')).toBeVisible();
  });

  test('names who and what, so the cook can act on it', async ({ page }) => {
    await open(page, 'Shortbread');
    const verdict = page.locator('.verdict');
    await expect(verdict.getByText('Ada').first()).toBeVisible();
    await expect(verdict.getByText('plain flour').first()).toBeVisible();
  });

  test('marks which finding is the blocker and which is only a caution', async ({ page }) => {
    /*
     * Ada cannot have gluten and does not tolerate milk. Both appear; only one is the
     * reason the recipe is refused, and a band that shows them identically says nothing
     * about which to act on.
     */
    await open(page, 'Shortbread');
    const flour = page.locator('.verdict__finding').filter({ hasText: 'plain flour' });
    const butter = page.locator('.verdict__finding').filter({ hasText: 'unsalted butter' });
    await expect(flour.locator('.verdict__severity')).toHaveText('never');
    await expect(butter.locator('.verdict__severity')).toHaveText('warn');
    // And the blocker is first: the reason the recipe was refused should not be the
    // second thing read.
    await expect(page.locator('.verdict__finding').first()).toContainText('plain flour');
  });

  test('says it before the ingredients rather than after them', async ({ page }) => {
    await open(page, 'Shortbread');
    const verdictTop = await page.locator('.verdict').boundingBox();
    const ingredientsTop = await page.getByRole('heading', { name: 'Ingredients' }).boundingBox();
    expect(verdictTop!.y).toBeLessThan(ingredientsTop!.y);
  });

  test('has no accessibility violations', async ({ page }) => {
    await open(page, 'Shortbread');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await open(page, 'Shortbread');
    await expect(page.locator('.verdict')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/verdict-unsuitable.png', fullPage: true });
  });
});

test.describe('a recipe nobody has checked', () => {
  test('is unknown, not suitable', async ({ page }) => {
    await open(page, 'Mystery Bake');
    await expect(page.getByText('Not enough is known')).toBeVisible();
    await expect(page.getByText('Suits everyone')).toHaveCount(0);
  });

  test('says which ingredient was never checked', async ({ page }) => {
    await open(page, 'Mystery Bake');
    await expect(page.locator('.verdict').getByText('mystery paste').first()).toBeVisible();
    await expect(page.getByText('not checked for allergens').first()).toBeVisible();
  });

  test('does not wear the styling of a clean bill of health', async ({ page }) => {
    await open(page, 'Mystery Bake');
    await expect(page.locator('.verdict--unknown')).toBeVisible();
    await expect(page.locator('.verdict--suitable')).toHaveCount(0);
  });

  test('has no accessibility violations', async ({ page }) => {
    await open(page, 'Mystery Bake');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await open(page, 'Mystery Bake');
    await expect(page.locator('.verdict')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/verdict-unknown.png', fullPage: true });
  });
});

test.describe('a household nobody has described', () => {
  test('gets no verdict rather than a reassuring one', async ({ page, request }) => {
    const auth = { Authorization: `Bearer ${token}` };
    const existing = await (await request.get('/api/v1/eaters', { headers: auth })).json();
    for (const person of existing) {
      await request.delete(`/api/v1/eaters/${person.id}`, { headers: auth });
    }
    await open(page, 'Shortbread');
    await expect(page.locator('.verdict')).toHaveCount(0);
  });
});
