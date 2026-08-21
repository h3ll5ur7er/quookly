import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Planning a week, on a phone, against a real instance.
 *
 * The payoff of everything before it: a recipe, a household, a pantry and a plan produce
 * a shopping list. So the tests are mostly about that list being right — net of stock,
 * added up across the week, and back to nothing when the plan goes away.
 */

const COOK = {
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

/** A week far enough out that no other spec's dates collide with it. */
const MONDAY = '2027-03-01';
const TUESDAY = '2027-03-02';
const SUNDAY = '2027-03-07';

test.describe.configure({ mode: 'serial' });

/**
 * Somebody to cook for, made here rather than relied on from an earlier spec.
 *
 * The household specs add and remove people as they go, and a plan that depended on what
 * they happened to leave behind would fail for a reason that has nothing to do with
 * planning.
 */
test.beforeAll(async ({ request }) => {
  const signIn = await request.post('/api/v1/accounts/sign-in', { data: COOK });
  const token = (await signIn.json()).token;
  await request.post('/api/v1/eaters', {
    data: { name: 'Robin', age_band: 'adult', appetite: '1.2', constraints: [] },
    headers: { Authorization: `Bearer ${token}` },
  });
});

/** One line of the shopping list, by what it names. */
function line(page: import('@playwright/test').Page, ingredient: string) {
  return page.locator('.shopping__line').filter({ hasText: ingredient });
}

/** The row for one person in the guest list. The row is the target, not the box. */
function guest(page: import('@playwright/test').Page, name: string) {
  return page.locator('.meal__person').filter({ hasText: name }).locator('input');
}

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/recipes$/);
});

/** The one plan these tests build up, opened from the list each time. */
async function week(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/plans');
  await page.getByRole('link', { name: /2027/ }).first().click();
  await expect(page).toHaveURL(/\/plans\/\d+$/);
}

test.describe('starting a week', () => {
  test('is reachable from anywhere in the app', async ({ page }) => {
    await page.getByRole('link', { name: 'Plan', exact: true }).click();
    await expect(page).toHaveURL(/\/plans$/);
    await expect(page.getByRole('heading', { name: 'Plans' })).toBeVisible();
  });

  test('explains an empty list instead of showing a blank page', async ({ page }) => {
    await page.goto('/plans');
    await expect(page.getByText(/Nothing planned yet/)).toBeVisible();
  });

  test('offers a week already filled in', async ({ page }) => {
    await page.goto('/plans');
    await expect(page.locator('#starts_on')).not.toHaveValue('');
  });

  test('has no accessibility violations when empty', async ({ page }) => {
    await page.goto('/plans');
    await expect(page.getByRole('button', { name: 'Start planning' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this when empty', async ({ page }) => {
    await page.goto('/plans');
    await expect(page.getByRole('button', { name: 'Start planning' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/plans-empty.png', fullPage: true });
  });

  test('opens the week it just started', async ({ page }) => {
    await page.goto('/plans');
    await page.locator('#starts_on').fill(MONDAY);
    await page.locator('#ends_on').fill(SUNDAY);
    await page.getByRole('button', { name: 'Start planning' }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await expect(page.getByText('Nothing to buy')).toBeVisible();
  });

  test('lays out every day, gaps included', async ({ page }) => {
    /* The gaps are the point: a row per day shows a cook where Thursday still is. */
    await week(page);
    await expect(page.locator('.week__day')).toHaveCount(7);
  });
});

test.describe('putting a meal down', () => {
  test('an empty day is the way to fill it', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await expect(page).toHaveURL(/\/plans\/\d+\/meal\?on=2027-03-01/);
    await expect(page.locator('#on_date')).toHaveValue(MONDAY);
  });

  test('takes a dish and the people at it', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await page.locator('#meal').selectOption('dinner');
    await page.locator('#recipe_id').selectOption({ label: 'Buttermilk Pancakes' });
    await guest(page, 'Robin').check();
    await page.getByRole('button', { name: 'Save this meal' }).click();

    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await expect(page.getByText('Buttermilk Pancakes')).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await expect(page.locator('#recipe_id')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('makes every touch target large enough to hit', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await expect(page.locator('#recipe_id')).toBeVisible();
    const undersized = await page.evaluate(() => {
      const MINIMUM = 44;
      return (
        [...document.querySelectorAll('input, button, select, a, label.meal__person')]
          .map((node) => ({ node, box: node.getBoundingClientRect() }))
          // The checkbox inside a row is not the target; the row around it is.
          .filter((one) => !(one.node as HTMLElement).matches('.meal__person input'))
          .filter(({ box }) => box.x >= 0 && box.y >= 0 && box.width > 0)
          .filter(({ box }) => box.height < MINIMUM)
          .map(({ node, box }) => `${node.tagName.toLowerCase()} ${box.height.toFixed(1)}px`)
      );
    });
    expect(undersized).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await expect(page.locator('#recipe_id')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/plan-meal.png', fullPage: true });
  });

  test('opens an existing meal filled in', async ({ page }) => {
    await week(page);
    await page.getByRole('link', { name: /Buttermilk Pancakes/ }).click();
    await expect(page.locator('#recipe_id')).not.toHaveValue('');
    await expect(guest(page, 'Robin')).toBeChecked();
  });
});

test.describe('what it comes to', () => {
  test('the list is what the week needs and the kitchen has not got', async ({ page }) => {
    await week(page);
    await expect(page.getByRole('heading', { name: 'Shopping list' })).toBeVisible();
    // Baking powder is not in the pantry, so it is on the list.
    await expect(line(page, 'baking powder')).toHaveCount(1);
    // Flour is, so it is not. Net of stock is the whole point (FR-7).
    await expect(line(page, 'plain flour')).toHaveCount(0);
  });

  test('asks for a whole egg rather than six tenths of one', async ({ page }) => {
    /* One small appetite against a recipe for four wants 0.6 eggs. A list that asks for
       that has stopped being a list somebody can act on. */
    await week(page);
    await expect(line(page, 'egg')).toContainText('1');
    await expect(line(page, 'egg')).not.toContainText('0.6');
  });

  test('planning holds stock rather than spending it', async ({ page }) => {
    /* The flour is still in the cupboard — the whole of ADR-004. The plan has claimed
       some of it, and the pantry says exactly what it said before: nothing was deducted,
       the shopping list is simply short by what the cupboard covers. */
    await page.goto('/pantry');
    const flour = page.locator('.pantry__entry').filter({ hasText: 'plain flour' });
    await expect(flour.locator('.pantry__total')).toHaveText('800 g');
    // And says so: some of that 800 g is spoken for by Monday's dinner.
    await expect(flour.locator('.pantry__claimed')).toContainText('is planned for a meal');
  });

  test('adds the week up rather than listing it meal by meal', async ({ page }) => {
    await week(page);
    await page.locator('.week__empty').first().click();
    await page.locator('#on_date').fill(TUESDAY);
    await page.locator('#recipe_id').selectOption({ label: 'Buttermilk Pancakes' });
    await page.getByRole('button', { name: 'Save this meal' }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    // Two meals, both carrying the dish that was chosen for them.
    await expect(page.getByRole('link', { name: /Buttermilk Pancakes/ })).toHaveCount(2);

    // One line for baking powder, not one per meal (FR-7).
    await expect(line(page, 'baking powder')).toHaveCount(1);
  });

  test('has no accessibility violations with a week in it', async ({ page }) => {
    await week(page);
    await expect(page.getByRole('heading', { name: 'Shopping list' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await week(page);
    await expect(page.getByRole('heading', { name: 'Shopping list' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/plan.png', fullPage: true });
  });
});

test.describe('cooking it', () => {
  test('takes what the meal was holding out of the pantry', async ({ page }) => {
    /* UC-4.5 through the whole stack. The plan states that a meal was cooked; the pantry
       hears it and consumes. Neither screen knows about the other. */
    await page.goto('/pantry');
    const before = await page
      .locator('.pantry__entry')
      .filter({ hasText: 'plain flour' })
      .locator('.pantry__total')
      .textContent();

    await week(page);
    await page
      .getByRole('link', { name: /Buttermilk Pancakes/ })
      .first()
      .click();
    await page.getByRole('button', { name: 'I cooked this' }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await expect(page.locator('.week__meal--cooked')).toHaveCount(1);

    await page.goto('/pantry');
    const after = page
      .locator('.pantry__entry')
      .filter({ hasText: 'plain flour' })
      .locator('.pantry__total');
    await expect(after).not.toHaveText(before ?? '');
  });

  test('is a record afterwards, not a plan', async ({ page }) => {
    await week(page);
    await page.locator('.week__meal--cooked').click();
    await expect(page.getByText('You cooked this')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save this meal' })).toHaveCount(0);
    await expect(page.locator('#recipe_id')).toBeDisabled();
    await page.screenshot({ path: 'e2e/screenshots/plan-cooked.png', fullPage: true });
  });

  test('drops out of the shopping list', async ({ page }) => {
    /* The food is eaten. A cooked meal is out of the sizing and out of the list — the
       week still needs shopping for the meal that has not happened yet.

       Two eggs for Tuesday, where before it was three for both meals together. */
    await week(page);
    await expect(line(page, 'egg')).toContainText('2');
    await expect(line(page, 'egg')).not.toContainText('3');
  });
});

test.describe('changing your mind', () => {
  test('takes a meal off the plan', async ({ page }) => {
    await week(page);
    await page
      .getByRole('link', { name: /Buttermilk Pancakes/ })
      .last()
      .click();
    await page.getByRole('button', { name: /Take this meal off/ }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await expect(page.getByRole('link', { name: /Buttermilk Pancakes/ })).toHaveCount(1);
  });

  test('deletes the plan, and the shopping list with it', async ({ page }) => {
    await week(page);
    await page.getByRole('button', { name: 'Delete this plan' }).click();
    await expect(page).toHaveURL(/\/plans$/);
    await expect(page.getByRole('link', { name: /2027/ })).toHaveCount(0);
  });

  test('gives back the stock it was holding', async ({ page }) => {
    /* A missed release is stock that is invisible forever, which is the waste this
       product exists to reduce. Visible here: the flour card said some of it was planned
       for a meal, and now says nothing, because nothing is claiming it. The cooked meal
       claims nothing either — it consumed what it held. */
    await page.goto('/pantry');
    const flour = page.locator('.pantry__entry').filter({ hasText: 'plain flour' });
    await expect(flour.locator('.pantry__claimed')).toHaveCount(0);
  });
});

test.describe('the bar that carries the sections', () => {
  test('the section bar fits the narrowest phone it has to', async ({ page }) => {
    /*
     * Measured, because an overflowing sticky bar looks fine until the last word is cut
     * off the edge — and the bar grows a section every time the app does. Planning made
     * it four, and four fixed-width links did not fit.
     *
     * 360px is the width NFR-11 names as the target.
     */
    await page.setViewportSize({ width: 360, height: 720 });
    await page.goto('/recipes');
    await expect(page.getByRole('navigation', { name: 'Sections' })).toBeVisible();

    const overflow = await page.evaluate(() => {
      const nav = document.querySelector('.shell__nav') as HTMLElement;
      return nav.scrollWidth - nav.clientWidth;
    });

    expect(overflow).toBeLessThanOrEqual(0);
  });
});
