import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The household screens, on a phone, against a real instance.
 *
 * This is where a cook types in an allergy, so the tests are less about the shape of the
 * page than about whether what was typed survives: recorded, listed, edited, and — the
 * one that matters — actually removed when it is removed.
 */

const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
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

test.describe('finding the household', () => {
  test('is reachable from anywhere in the app', async ({ page }) => {
    // Under Settings now, not in the bar: it is set once and then left alone.
    await page.getByRole('link', { name: 'Settings and account' }).click();
    await page.getByRole('link', { name: 'Who you cook for' }).click();
    await expect(page).toHaveURL(/\/household$/);
    await expect(page.getByRole('heading', { name: 'Household' })).toBeVisible();
  });

  test('explains an empty household instead of showing a blank page', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByText(/Nobody here yet/)).toBeVisible();
  });

  test('has no accessibility violations when empty', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByRole('link', { name: 'Add someone' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this when empty', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByRole('link', { name: 'Add someone' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/household-empty.png', fullPage: true });
  });
});

test.describe('recording somebody', () => {
  test('takes a name, an age, and a portion size', async ({ page }) => {
    await page.goto('/household/new');
    await page.getByLabel('Name', { exact: true }).fill('Jonas');
    await page.getByLabel('Age', { exact: true }).selectOption('adult');
    await page.getByLabel('Portion size', { exact: true }).fill('1.4');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page).toHaveURL(/\/household$/);
    await expect(page.getByText('Jonas')).toBeVisible();
  });

  test('shows the portion size back, not a head count', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByText('1.4').first()).toBeVisible();
  });

  test('records an allergy with its severity', async ({ page }) => {
    await page.goto('/household/new');
    await page.getByLabel('Name', { exact: true }).fill('Mira');
    await page.getByLabel('Age', { exact: true }).selectOption('child');
    await page.getByLabel('Portion size', { exact: true }).fill('0.6');
    await page.getByLabel('What', { exact: true }).selectOption('peanuts');
    await page.getByLabel('How serious', { exact: true }).selectOption('medical');
    await page.getByRole('button', { name: 'Add' }).click();
    // The chip, not the option of the same name still sitting in the picker.
    await expect(page.locator('.chip').filter({ hasText: 'Peanuts' })).toBeVisible();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page).toHaveURL(/\/household$/);
    await expect(page.locator('.chip').filter({ hasText: 'Peanuts' })).toBeVisible();
  });

  test('says what a warning means in words, not only in colour', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByText('never').first()).toBeVisible();
  });

  test('adds the servings up rather than counting heads', async ({ page }) => {
    // 1.4 + 0.6 = 2 servings for two people.
    await page.goto('/household');
    await expect(page.getByText('Cooking for')).toBeVisible();
    await expect(page.getByText('2', { exact: true }).first()).toBeVisible();
  });

  test('has no accessibility violations with people in it', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByText('Mira')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/household');
    await expect(page.getByText('Mira')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/household.png', fullPage: true });
  });
});

test.describe('the form itself', () => {
  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/household/new');
    await expect(page.getByLabel('Name', { exact: true })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('makes every touch target large enough to hit', async ({ page }) => {
    await page.goto('/household/new');
    await expect(page.getByLabel('Name', { exact: true })).toBeVisible();
    const undersized = await page.evaluate(() => {
      const MINIMUM = 44;
      return (
        [...document.querySelectorAll('input, button, select, a')]
          .map((node) => ({ node, box: node.getBoundingClientRect() }))
          // Off-screen affordances — the skip link until it is focused — are reached by
          // keyboard, not by thumb, and are not touch targets.
          .filter(({ box }) => box.x >= 0 && box.y >= 0 && box.width > 0)
          .filter(({ box }) => box.height < MINIMUM)
          .map(({ node, box }) => `${node.tagName.toLowerCase()} ${box.height.toFixed(1)}px`)
      );
    });
    expect(undersized).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/household/new');
    await expect(page.getByLabel('Name', { exact: true })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/eater-form.png', fullPage: true });
  });

  test('refuses an ingredient the registry has never heard of', async ({ page }) => {
    await page.goto('/household/new');
    await page.getByLabel('Name', { exact: true }).fill('Ana');
    await page.getByLabel('What', { exact: true }).selectOption('ingredient');
    await page.getByLabel('Ingredient', { exact: true }).fill('unicorn tears');
    await page.getByRole('button', { name: 'Add' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
  });

  test('takes an ingredient it does know', async ({ page }) => {
    await page.goto('/household/new');
    await page.getByLabel('Name', { exact: true }).fill('Ana');
    await page.getByLabel('What', { exact: true }).selectOption('ingredient');
    await page.getByLabel('Ingredient', { exact: true }).fill('caster sugar');
    await page.getByLabel('How serious', { exact: true }).selectOption('preference');
    await page.getByRole('button', { name: 'Add' }).click();
    await expect(page.locator('.chip').filter({ hasText: 'caster sugar' })).toBeVisible();
  });
});

test.describe('correcting somebody', () => {
  test('opens filled in with what is already known', async ({ page }) => {
    await page.goto('/household');
    await page.getByRole('link', { name: /Mira/ }).click();
    await expect(page.getByLabel('Name', { exact: true })).toHaveValue('Mira');
    await expect(page.getByLabel('Portion size', { exact: true })).toHaveValue('0.6');
    await expect(page.locator('.chip').filter({ hasText: 'Peanuts' })).toBeVisible();
  });

  test('really removes an allergy that was removed', async ({ page }) => {
    /*
     * The one that matters. An allergy deleted in the form and still stored is a warning
     * a cook believes they have turned off — and the next screen would agree with them.
     */
    await page.goto('/household');
    await page.getByRole('link', { name: /Mira/ }).click();
    await page.getByRole('button', { name: /Remove Peanuts/ }).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page).toHaveURL(/\/household$/);
    await page.reload();
    await expect(page.getByText('Mira')).toBeVisible();
    await expect(page.locator('.chip')).toHaveCount(0);
  });

  test('takes somebody out of the household', async ({ page }) => {
    await page.goto('/household');
    await page.getByRole('link', { name: /Jonas/ }).click();
    await page.getByRole('button', { name: 'Remove from household' }).click();
    await expect(page).toHaveURL(/\/household$/);
    await expect(page.getByText('Jonas')).toHaveCount(0);
  });
});
