import { claim, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Finding something to cook, with a stocked kitchen (UC-3.3, UC-3.4).
 *
 * Its own file, running last, because it needs stock on the shelf and stock is what every
 * other spec's expectations are built on. Adding a bag of flour in the middle of the pantry
 * suite changed what the plan's shopping list came to two files later — so this one puts
 * its own kitchen together and disturbs nobody after it.
 */

/** Everything the seeded Shortbread needs, so the pantry can cover it whole. */
const SHORTBREAD = ['unsalted-butter', 'caster-sugar', 'plain-flour'];

function inDays(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  return when.toISOString().slice(0, 10);
}

test.describe.configure({ mode: 'serial' });

/** Held from `beforeAll` so the tests below do not each fetch a token of their own. */
let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };

  for (const slug of SHORTBREAD) {
    const found = await request.get(`/api/v1/ingredients?search=${slug.replace(/-/g, '%20')}`, {
      headers,
    });
    const entry = ((await found.json()) as { id: number; slug: string }[]).find(
      (one) => one.slug === slug,
    );
    expect(entry, `${slug} should be in the registry`).toBeDefined();
    const received = await request.post('/api/v1/pantry', {
      data: {
        ingredient_id: entry!.id,
        magnitude: '1',
        unit: 'kg',
        // The sugar is the one about to go off, so the recipe using it should lead.
        ...(slug === 'caster-sugar' ? { expires_on: inDays(1) } : {}),
      },
      headers,
    });
    expect(received.ok(), await received.text()).toBe(true);
  }
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
  // Signing in lands on Home; this file is about the recipes.
  await page.goto('/recipes');
  await page.getByRole('button', { name: 'Worth cooking' }).click();
});

test.describe('what the kitchen makes worth cooking', () => {
  /**
   * Every title, in the order shown.
   *
   * Waited for twice, and both waits earn their place. `allTextContents` does not auto-wait
   * the way a locator assertion does — and the list is *replaced* when the suggestions
   * arrive, so waiting for a title alone can catch the alphabetical one on its way out and
   * read a torn-down list. A reason chip only exists in the suggested order, so its
   * appearance is the signal that the swap has happened.
   */
  async function shownTitles(page: import('@playwright/test').Page): Promise<string[]> {
    await expect(page.locator('.recipes__reason').first()).toBeVisible();
    await expect(page.locator('.recipes__title').first()).toBeVisible();
    return (await page.locator('.recipes__title').allTextContents()).map((one) => one.trim());
  }

  /** One row, by its exact title: earlier specs leave a "Plain Shortbread" behind too. */
  function row(page: import('@playwright/test').Page, title: string) {
    return page
      .locator('.recipes__item')
      .filter({ has: page.locator('.recipes__title', { hasText: new RegExp(`^${title}$`) }) });
  }

  test('a recipe the cupboard covers says so', async ({ page }) => {
    await expect(row(page, 'Shortbread').locator('.recipes__reason')).toContainText([
      /uses something up/,
      /you have everything/,
    ]);
  });

  test('something that needs eating leads, and is named', async ({ page }) => {
    /* The reason the whole feature exists: a full cupboard gives a cook options, and the
       sugar going off tomorrow is the one that costs money if it is ignored. */
    const first = page.locator('.recipes__item').first();
    await expect(first.locator('.recipes__title')).toHaveText('Shortbread');
    await expect(first).toContainText('uses something up');
    await expect(first.locator('.recipes__pressing')).toContainText('caster sugar');
  });

  test('among recipes that all save something, the cupboard breaks the tie', async ({ page }) => {
    /* Both use the sugar that is going off. The shortbread needs no shopping trip and the
       pancakes do, so the shortbread leads. */
    const titles = await shownTitles(page);
    expect(titles).toContain('Shortbread');
    expect(titles).toContain('Buttermilk Pancakes');
    expect(titles.indexOf('Shortbread')).toBeLessThan(titles.indexOf('Buttermilk Pancakes'));
  });

  test('the alphabet is one tap away again', async ({ page }) => {
    await page.getByRole('button', { name: 'A–Z' }).click();
    // No reasons is how the alphabetical order announces itself, and waiting for that is
    // what stops the read landing on the list being replaced.
    await expect(page.locator('.recipes__reason')).toHaveCount(0);
    await expect(page.locator('.recipes__title').first()).toBeVisible();

    const titles = (await page.locator('.recipes__title').allTextContents()).map((one) =>
      one.trim(),
    );
    expect([...titles].sort()).toEqual(titles);
  });

  test('has no accessibility violations', async ({ page }) => {
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.screenshot({ path: 'e2e/screenshots/recipe-discovery.png', fullPage: true });
  });
});
