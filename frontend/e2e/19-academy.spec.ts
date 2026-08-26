import { expect, test } from '@playwright/test';

/**
 * Looking a word up from a recipe (UC-2.5) and from the hob (UC-9.5).
 *
 * Nothing is tagged and nothing is stored linking a step to a page: the terms are read out
 * of the step's own words when it is displayed (ADR-040, ADR-055). This recipe is written
 * here, in this file, and gains its links because the Academy happens to explain the words
 * it uses — which is the whole claim.
 */

const COOK = {
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

test.describe.configure({ mode: 'serial' });

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
});

test('the Academy can be browsed and a page read', async ({ page }) => {
  await page.goto('/academy');
  await expect(page.getByRole('heading', { name: 'Academy' })).toBeVisible();

  await page.getByRole('link', { name: 'deep-fry', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'deep-fry' })).toBeVisible();
  await expect(page.getByText('Cook submerged in hot fat.')).toBeVisible();
  // The one place a definition is not enough on its own.
  await expect(page.getByText(/never move a burning pan/)).toBeVisible();
});

test('a recipe marks the words it uses, and they lead to the Academy', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Title').fill('Marked Loaf');
  await page.getByLabel('Makes').fill('1');
  await page.getByRole('button', { name: 'Choose an ingredient' }).click();
  await page.getByPlaceholder('An ingredient name').fill('plain flour');
  await page.getByRole('button', { name: 'plain flour', exact: true }).click();
  await page.getByLabel('How much').fill('500');
  await page.getByLabel('Step').fill('Gently fold in the whites, then blanch the beans.');
  await page.getByRole('button', { name: 'Save recipe' }).click();

  await expect(page.getByRole('heading', { name: 'Marked Loaf' })).toBeVisible();

  // The step reads as written; two of its words are now links.
  await expect(page.getByText('Gently fold in the whites, then blanch the beans.')).toBeVisible();
  await page.getByRole('link', { name: 'Gently fold' }).click();

  await expect(page).toHaveURL(/\/academy\/fold$/);
  await expect(page.getByRole('heading', { name: 'fold' })).toBeVisible();
  await expect(page.getByText('Combine without knocking out the air.')).toBeVisible();
});
