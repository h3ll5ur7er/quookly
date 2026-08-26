import { expect, test } from '@playwright/test';

/**
 * Writing a recipe by hand, correcting it, and putting it away (ADR-059).
 *
 * Until this existed a recipe could be created and never changed, and the only ways in
 * were an import or a model. The manual form is the one screen where a cook types a whole
 * recipe, and a form is exactly what a unit test under-verifies: it can prove the request
 * body is right and say nothing about whether the fields can be reached.
 */

// The account the rest of the suite shares. Not one of its own: accounts are applied for
// and approved (ADR-049), so a spec that invents a cook needs an administrator to let them
// in — and which spec claimed the instance depends on what else is running.
const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
  password: 'a-sufficiently-long-password',
};

test.describe.configure({ mode: 'serial' });

// No `beforeAll`. Files run in parallel, so claiming the instance from here races the spec
// that claims it properly — and this one only needs an account to exist, which a sibling
// has already made. The cost is that this file cannot run on its own, which is true of
// most of them.

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto('/recipes');
});

test('a recipe can be written, corrected and put away', async ({ page }) => {
  await page.getByRole('link', { name: 'Write one yourself' }).click();
  await expect(page.getByRole('heading', { name: 'Write a recipe' })).toBeVisible();

  await page.getByLabel('Title').fill('Hand-written Loaf');
  await page.getByLabel('Makes').fill('1');

  // The ingredient comes from the registry rather than from typed text, which is what
  // makes the line convertible, shoppable and judgeable at all.
  await page.getByRole('button', { name: 'Choose an ingredient' }).click();
  await page.getByPlaceholder('An ingredient name').fill('plain flour');
  await page.getByRole('button', { name: 'plain flour', exact: true }).click();
  await expect(page.getByText('plain flour')).toBeVisible();

  await page.getByLabel('How much').fill('500');
  await page.getByLabel('Step').fill('Mix, prove, bake.');
  await page.getByRole('button', { name: 'Save recipe' }).click();

  // Saving lands on the recipe it just wrote.
  await expect(page.getByRole('heading', { name: 'Hand-written Loaf' })).toBeVisible();
  await expect(page.getByText('500 g')).toBeVisible();

  // --- correcting it ---------------------------------------------------------------
  await page.getByRole('link', { name: 'Correct this recipe' }).click();
  await expect(page.getByRole('heading', { name: 'Correct this recipe' })).toBeVisible();
  // It arrives filled in: the line remembers the entry it points at, not just its name.
  await expect(page.getByLabel('Title')).toHaveValue('Hand-written Loaf');
  await expect(page.getByText('plain flour')).toBeVisible();

  await page.getByLabel('Title').fill('Sourdough');
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page.getByRole('heading', { name: 'Sourdough' })).toBeVisible();

  // --- putting it away -------------------------------------------------------------
  await page.getByRole('button', { name: 'Put it away' }).click();
  await page.getByRole('button', { name: 'Yes, put it away' }).click();
  await expect(page).toHaveURL(/\/recipes$/);
  await expect(page.getByRole('link', { name: /Sourdough/ })).toHaveCount(0);

  // Put away, not lost.
  await page.getByRole('button', { name: 'Put away' }).click();
  await expect(page.getByRole('link', { name: /Sourdough/ })).toBeVisible();
});
