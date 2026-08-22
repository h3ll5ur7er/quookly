import { expect, test } from '@playwright/test';

/**
 * The paths between the screens (UC-9.1b, UC-4.2).
 *
 * Every screen here already worked. What did not exist was any way to get from one to the
 * next: a recipe you had decided to cook, with no way to cook it; a plan naming a dish it
 * would not show you. These are the joins, and a join is exactly the thing a unit test
 * cannot see — each half passes on its own while the seam between them is missing.
 */

const COOK = {
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

test.describe.configure({ mode: 'serial' });

/** Today, as the cook's own clock reads it — which is the clock the backend uses too. */
function today(): string {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('-');
}

/**
 * A week containing today, because "add to plan" and "cook this now" both mean *this*
 * week and neither can mean a week in 2027. Made once: opening a second one every test
 * would leave the screen ambiguous about which of them is current.
 */
let planId: number;

test.beforeEach(async ({ page, request }) => {
  const signIn = await request.post('/api/v1/accounts/sign-in', { data: COOK });
  const headers = { Authorization: `Bearer ${(await signIn.json()).token}` };

  // Anything left cooking would be resumed instead of started, and this spec is about
  // starting.
  const open = await request.get('/api/v1/cooking/sessions', { headers });
  for (const session of (await open.json()) as { id: number }[]) {
    await request.post(`/api/v1/cooking/sessions/${session.id}/abandoned`, { headers });
  }

  if (planId === undefined) {
    const made = await request.post('/api/v1/plans', {
      data: { starts_on: today(), ends_on: today() },
      headers,
    });
    planId = (await made.json()).id;
  }

  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
});

/**
 * Open the seeded Shortbread, whichever id it was given.
 *
 * Matched on the card's title rather than the link's accessible name: the whole card is
 * one anchor, so its name is the title *and* the summary *and* the yield, and "Plain
 * Shortbread" sorts ahead of it under any looser match.
 */
async function shortbread(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/recipes');
  await page
    .locator('.recipes__link')
    .filter({ has: page.locator('.recipes__title', { hasText: /^Shortbread$/ }) })
    .first()
    .click();
  await expect(page).toHaveURL(/\/recipes\/\d+$/);
}

test('a cook who has decided can start cooking from the recipe itself', async ({ page }) => {
  await shortbread(page);
  await page.getByRole('button', { name: 'Start cooking now' }).click();

  await expect(page).toHaveURL(/\/cook\/\d+$/);
  await expect(page.getByRole('heading', { name: 'Shortbread' })).toBeVisible();
});

test('what was cooked on a whim is on the plan afterwards', async ({ page }) => {
  // The reason cooking goes through the plan at all: a week's record should include what
  // was improvised in it, not only what was intended.
  await shortbread(page);
  await page.getByRole('button', { name: 'Start cooking now' }).click();
  await expect(page).toHaveURL(/\/cook\/\d+$/);

  await page.goto(`/plans/${planId}`);
  await expect(page.locator('.week__recipe').filter({ hasText: 'Shortbread' })).toHaveCount(1);
});

test('a recipe can be put on the plan with the dish already chosen', async ({ page }) => {
  await shortbread(page);
  await page.getByRole('button', { name: 'Add to plan' }).click();

  await expect(page).toHaveURL(/\/plans\/\d+\/meal\?recipe=\d+$/);
  await expect(page.locator('#recipe_id')).not.toHaveValue('');
});

test('a planned meal leads back to the recipe it names', async ({ page }) => {
  await shortbread(page);
  const recipeUrl = page.url();
  await page.getByRole('button', { name: 'Add to plan' }).click();
  await page.locator('#on_date').fill(today());
  await page.getByRole('button', { name: 'Save this meal' }).click();
  await expect(page).toHaveURL(/\/plans\/\d+$/);

  await page.getByRole('link', { name: 'Show recipe' }).first().click();
  await expect(page).toHaveURL(recipeUrl);
});
