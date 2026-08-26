import { claim, signIn } from './support';
import { expect, test } from '@playwright/test';

/**
 * Writing a recipe by hand, correcting it, and putting it away (ADR-059).
 *
 * Until this existed a recipe could be created and never changed, and the only ways in
 * were an import or a model. The manual form is the one screen where a cook types a whole
 * recipe, and a form is exactly what a unit test under-verifies: it can prove the request
 * body is right and say nothing about whether the fields can be reached.
 */

test.describe.configure({ mode: 'serial' });

// Claimed here rather than inherited from whichever file ran first, so this one can
// be run on its own.
test.beforeAll(async ({ request }) => {
  await claim(request);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
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

test('a cook can link a word in a step, and the link survives an edit', async ({ page }) => {
  await page.goto('/recipes/new');

  await page.getByLabel('Title').fill('Linked Pancakes');
  await page.getByLabel('Makes').fill('12');
  await page.getByRole('button', { name: 'Choose an ingredient' }).click();
  await page.getByPlaceholder('An ingredient name').fill('plain flour');
  await page.getByRole('button', { name: 'plain flour', exact: true }).click();
  await page.getByLabel('How much').fill('250');

  // The author says which entry this word means, rather than leaving it to be recognised.
  await page.getByLabel('Step').fill('Sift the [[plain-flour|flour]] into a bowl.');
  await page.getByRole('button', { name: 'Save recipe' }).click();
  await expect(page.getByRole('heading', { name: 'Linked Pancakes' })).toBeVisible();

  // The brackets are markup, not words: a cook reads the sentence, and the linked word is
  // a link.
  const step = page.getByRole('listitem').filter({ hasText: 'Sift the' });
  await expect(step).toContainText('Sift the flour into a bowl.');
  await expect(step).not.toContainText('[[');
  await expect(step.getByRole('link', { name: 'flour', exact: true })).toBeVisible();

  // --- and it is still there after an unrelated correction --------------------------
  await page.getByRole('link', { name: 'Correct this recipe' }).click();
  // The form shows the markup, because that is what an author edits.
  await expect(page.getByLabel('Step')).toHaveValue('Sift the [[plain-flour|flour]] into a bowl.');

  await page.getByLabel('Title').fill('Linked Blini');
  await page.getByRole('button', { name: 'Save recipe' }).click();

  await expect(page.getByRole('heading', { name: 'Linked Blini' })).toBeVisible();
  const again = page.getByRole('listitem').filter({ hasText: 'Sift the' });
  await expect(again.getByRole('link', { name: 'flour', exact: true })).toBeVisible();
});
