import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Asking for a recipe that does not exist (UC-1.4, UC-1.5).
 *
 * This instance has no model configured — the e2e harness runs without one on purpose, so
 * that every other feature is proved to work without one. That makes this the spec for the
 * *honest failure*: the screen is reachable, it knows what the cook has, and when there is
 * nothing to ask it says so in words rather than spinning.
 *
 * Whether a real model writes a usable recipe is covered live, against one.
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
  await expect(page).toHaveURL(/\/recipes$/);
});

test.describe('asking for a recipe', () => {
  test('is reachable from the recipe list', async ({ page }) => {
    await page.getByRole('link', { name: 'Write me a recipe' }).click();
    await expect(page).toHaveURL(/\/recipes\/invent$/);
    await expect(page.getByRole('heading', { name: 'Write me a recipe' })).toBeVisible();
  });

  test('will not ask with nothing to go on', async ({ page }) => {
    /* "Write me a recipe" with no constraints is a question with too many answers. */
    await page.goto('/recipes/invent');
    await expect(page.getByRole('button', { name: 'Write it' })).toBeDisabled();
  });

  test('a description is enough', async ({ page }) => {
    await page.goto('/recipes/invent');
    await page.getByLabel('What do you feel like').fill('something quick with chicken');
    await expect(page.getByRole('button', { name: 'Write it' })).toBeEnabled();
  });

  test('what is on the shelf is a tap rather than a spelling test', async ({ page }) => {
    await page.goto('/recipes/invent');
    const chip = page.locator('.invent__pick').filter({ hasText: 'plain flour' });
    await expect(chip).toBeVisible();

    await chip.click();
    await expect(chip).toHaveClass(/invent__pick--on/);
    await expect(page.getByRole('button', { name: 'Write it' })).toBeEnabled();
  });

  test('says plainly that this instance has no model', async ({ page }) => {
    /* Not "that did not work". An operator reading this knows what to go and configure. */
    await page.goto('/recipes/invent');
    await page.getByLabel('What do you feel like').fill('a pie');
    await page.getByRole('button', { name: 'Write it' }).click();

    await expect(page.getByRole('alert')).toContainText('none configured');
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/recipes/invent');
    await expect(page.getByRole('button', { name: 'Write it' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/recipes/invent');
    await page.getByLabel('What do you feel like').fill('something quick with the leftover rice');
    await page.locator('.invent__pick').filter({ hasText: 'plain flour' }).click();
    await expect(page.getByRole('button', { name: 'Write it' })).toBeEnabled();

    /* Frozen, because the button crossing from disabled to enabled is a 120 ms fade and a
       screenshot caught halfway through it shows a washed-out primary — the one thing the
       design language says a live button must never look like. */
    await page.screenshot({
      path: 'e2e/screenshots/recipe-invent.png',
      fullPage: true,
      animations: 'disabled',
    });
  });
});

test.describe('making a version of a recipe', () => {
  /* Same story as above: no model here, so what is proved is that the way in exists on the
     recipe it belongs to, and that the refusal is a sentence somebody can act on. */

  test('is offered on the recipe it would be a version of', async ({ page }) => {
    await page.getByText('Shortbread').first().click();
    await expect(page.getByRole('heading', { name: 'Make a version of this' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Make it' })).toBeDisabled();
  });

  test('says plainly that this instance has no model', async ({ page }) => {
    await page.getByText('Shortbread').first().click();
    await page.getByPlaceholder('Dairy-free').fill('make it dairy-free');
    await page.getByRole('button', { name: 'Make it' }).click();

    await expect(page.getByRole('alert')).toContainText('none configured');
  });

  test('an ordinary recipe does not claim to be a version of anything', async ({ page }) => {
    await page.getByText('Shortbread').first().click();
    await expect(page.locator('.recipe__derived')).toHaveCount(0);
  });
});
