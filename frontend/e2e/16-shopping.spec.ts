import { claim, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The shopping list, in a shop (UC-4.4).
 *
 * Its own screen and its own spec because of where it is used: one hand, poor signal, and
 * thirty seconds. What these check that a unit test cannot is that the list opens on
 * itself without choosing a week first, and that a tick survives the phone going away and
 * coming back — which is the whole reason the tick is on the server and not in a browser.
 */

test.describe.configure({ mode: 'serial' });

/** A day of its own, containing today, so `/shopping` opens on this week and not another. */
function today(): string {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('-');
}

let planId: number;
let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };

  const plans = await request.get('/api/v1/plans/current', { headers });
  const running = (await plans.json()) as { id: number; starts_on: string } | null;
  if (running !== null && running.starts_on <= today()) {
    planId = running.id;
  } else {
    const made = await request.post('/api/v1/plans', {
      data: { starts_on: today(), ends_on: today() },
      headers,
    });
    planId = (await made.json()).id;
  }

  // A dish of its own, asking for more flour than any kitchen in this suite has. A seeded
  // recipe would do until an earlier spec happened to stock enough to cover it, and then
  // this spec would fail for a reason that has nothing to do with shopping.
  const registry = await request.get('/api/v1/ingredients?search=plain%20flour', { headers });
  const flour = ((await registry.json()) as { id: number; slug: string }[]).find(
    (entry) => entry.slug === 'plain-flour',
  )!;
  const written = await request.post('/api/v1/recipes', {
    data: {
      title: 'A Very Large Loaf',
      yield_magnitude: '4',
      yield_unit: 'serving',
      lines: [{ ingredient_id: flour.id, magnitude: '9', unit: 'kg' }],
      steps: [{ instruction: 'Bake.' }],
    },
    headers,
  });
  await request.put(`/api/v1/plans/${planId}/slots`, {
    data: {
      on_date: today(),
      meal: 'lunch',
      recipe_id: (await written.json()).id,
      attendee_ids: [],
    },
    headers,
  });
});

test.beforeEach(async ({ page, request }) => {
  // Every test starts from an untouched basket, whatever the last one ticked.
  const plan = await request.get(`/api/v1/plans/${planId}`, { headers });
  for (const line of (await plan.json()).shopping as { ingredient_id: number }[]) {
    await request.put(`/api/v1/plans/${planId}/shopping/${line.ingredient_id}`, {
      data: { bought: false },
      headers,
    });
  }

  await signIn(page);
});

test('opens on the list, without choosing a week first', async ({ page }) => {
  await page.goto('/shopping');
  await expect(page.locator('.shopping__line').first()).toBeVisible();
});

test('a line ticks off and stays on the list', async ({ page }) => {
  await page.goto('/shopping');
  const first = page.locator('.shopping__line').first();
  // Counted after the list is on screen. Counting first counts nothing, and "the list did
  // not shrink" is trivially true of a list that was never there.
  await expect(first).toBeVisible();
  const before = await page.locator('.shopping__line').count();

  await first.click();

  await expect(first.locator('.shopping__tick')).toBeChecked();
  await expect(first).toHaveClass(/shopping__line--got/);
  await expect(page.locator('.shopping__line')).toHaveCount(before);
});

test('what was ticked is still ticked when the phone comes back', async ({ page }) => {
  // The reason the tick lives on the server: a shop is where a phone locks itself, and a
  // list that forgot would send a cook round the aisles twice.
  await page.goto('/shopping');
  await page.locator('.shopping__line').first().click();
  await expect(page.locator('.shopping__line').first().locator('.shopping__tick')).toBeChecked();

  await page.reload();
  await expect(page.locator('.shopping__line').first().locator('.shopping__tick')).toBeChecked();
});

test('says how far through the shop the cook is', async ({ page }) => {
  await page.goto('/shopping');
  await expect(page.locator('.shopping__progress')).toContainText('0');
  await page.locator('.shopping__line').first().click();
  await expect(page.locator('.shopping__progress')).toContainText('1');
});

test('has no accessibility violations', async ({ page }) => {
  await page.goto('/shopping');
  await expect(page.locator('.shopping__line').first()).toBeVisible();
  const scan = await new AxeBuilder({ page }).analyze();
  expect(scan.violations).toEqual([]);
});

test('looks like this in a shop', async ({ page }) => {
  await page.goto('/shopping');
  await page.locator('.shopping__line').first().click();
  await expect(page.locator('.shopping__line').first()).toHaveClass(/shopping__line--got/);
  await page.screenshot({ path: 'e2e/screenshots/shopping-ticked.png', fullPage: true });
});
