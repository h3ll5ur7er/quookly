import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The journey a first-time operator makes: an unclaimed instance, an admin account, a
 * dashboard. Serial and in this order, because claiming an instance cannot be undone.
 */

const ADMIN = {
  name: 'Emanuel',
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

test.describe.configure({ mode: 'serial' });

test.describe('an unclaimed instance', () => {
  test('sends a visitor to the bootstrap form', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/bootstrap$/);
    await expect(page.getByRole('heading', { name: 'Welcome to Quookly' })).toBeVisible();
  });

  test('explains what claiming means before asking for anything', async ({ page }) => {
    await page.goto('/bootstrap');
    await expect(page.getByText(/no accounts yet/i)).toBeVisible();
    await expect(page.getByText(/administrator/i).first()).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/bootstrap');
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks the way it should on first run', async ({ page }) => {
    await page.goto('/bootstrap');
    await expect(page.getByRole('button', { name: 'Create administrator' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/bootstrap-light.png', fullPage: true });
  });

  test('will not submit a password the API would reject', async ({ page }) => {
    await page.goto('/bootstrap');
    await page.getByLabel('Your name').fill(ADMIN.name);
    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel('Password').fill('short');
    await expect(page.getByRole('button', { name: 'Create administrator' })).toBeDisabled();
  });

  test('makes every touch target large enough to hit', async ({ page }) => {
    await page.goto('/bootstrap');
    // Wait for the lazily loaded route: measuring before it renders would pass by
    // finding nothing to measure.
    await expect(page.getByRole('button', { name: 'Create administrator' })).toBeVisible();

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

  test('fits the phone without sideways scrolling', async ({ page }) => {
    await page.goto('/bootstrap');
    await expect(page.getByRole('button', { name: 'Create administrator' })).toBeVisible();
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflows, 'the page body must never scroll horizontally').toBe(false);
  });
});

test.describe('claiming the instance', () => {
  test('creates the administrator and walks them into setup', async ({ page }) => {
    /*
     * Not the recipe list. A fresh instance has nobody to cook for, so nothing there
     * would be checked against anybody, and an empty kitchen teaches nothing about what
     * to do next (UC-10.2).
     */
    await page.goto('/bootstrap');
    await page.getByLabel('Your name').fill(ADMIN.name);
    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel('Password').fill(ADMIN.password);
    await page.getByRole('button', { name: 'Create administrator' }).click();

    await expect(page).toHaveURL(/\/setup$/);
    await expect(page.getByRole('heading', { name: 'Set up your kitchen' })).toBeVisible();
  });

  test('the instance is now claimed, so the bootstrap form is gone', async ({ page }) => {
    await page.context().clearCookies();
    await page.goto('/bootstrap');
    await expect(page).toHaveURL(/\/sign-in/);
  });
});

test.describe('a claimed instance', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/sign-in');
  });

  test('offers sign-in and has no accessibility violations', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('refuses a wrong password without saying whether the account exists', async ({ page }) => {
    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel('Password').fill('wrong-password-entirely');
    await page.getByRole('button', { name: 'Sign in' }).click();

    const refusal = page.getByRole('alert');
    await expect(refusal).toBeVisible();
    await expect(refusal).toHaveText(/did not match an account/i);

    await page.getByLabel('Email').fill('nobody@example.com');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toHaveText(/did not match an account/i);
  });

  test('signs a returning cook in', async ({ page }) => {
    await page.getByLabel('Email').fill(ADMIN.email);
    await page.getByLabel('Password').fill(ADMIN.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/recipes$/);
  });

  test('keeps a stranger out of the recipes and remembers where they were going', async ({
    page,
  }) => {
    await page.context().clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.goto('/recipes');
    await expect(page).toHaveURL(/\/sign-in\?returnUrl=%2Frecipes$/);
  });

  test('is operable by keyboard alone', async ({ page }) => {
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.textContent?.trim());
    expect(focused, 'the first stop should be the skip link').toBe('Skip to content');

    const ring = await page.evaluate(() => {
      const style = getComputedStyle(document.activeElement as Element);
      return { width: style.outlineWidth, style: style.outlineStyle };
    });
    expect(ring.style, 'focus must be visible').not.toBe('none');
    expect(Number.parseFloat(ring.width)).toBeGreaterThan(0);
  });
});
