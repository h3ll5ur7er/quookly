import { expect, test } from '@playwright/test';

/**
 * Screenshots for human review. These do not assert an appearance — they produce one to
 * be looked at, because a suite that passes is not the same as a screen that is good.
 */

const THEMES = ['light', 'dark', 'playful', 'decorative'] as const;

test.describe('how it looks', () => {
  // Make the file stand on its own: the sign-in screen only exists once an instance has
  // been claimed, and a fresh database is created for every run.
  test.beforeAll(async ({ request }) => {
    const response = await request.post('/api/v1/accounts/bootstrap', {
      data: {
        email: 'chef@example.com',
        display_name: 'Emanuel',
        password: 'a-sufficiently-long-password',
      },
    });
    expect([201, 409], 'the instance should be claimed or already claimed').toContain(
      response.status(),
    );
  });

  for (const theme of THEMES) {
    test(`sign-in in ${theme}`, async ({ page }) => {
      await page.goto('/sign-in');
      await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();
      await page.getByLabel('Colour theme').selectOption(theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);

      // Fill the form so the primary action is shown enabled. An empty form disables it,
      // and a screenshot of the disabled state hides what the theme actually looks like.
      await page.getByLabel('Email').fill('chef@example.com');
      await page.getByLabel('Password').fill('a-sufficiently-long-password');
      await page.locator('body').click({ position: { x: 5, y: 5 } });

      await page.screenshot({ path: `e2e/screenshots/sign-in-${theme}.png`, fullPage: true });
    });
  }

  test('sign-in with an error showing', async ({ page }) => {
    await page.goto('/sign-in');
    await page.getByLabel('Email').fill('chef@example.com');
    await page.getByLabel('Password').fill('wrong-password-entirely');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/sign-in-error.png', fullPage: true });
  });

  test('sign-in on a desktop width', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/sign-in-desktop.png', fullPage: true });
  });

  test('sign-in in German', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'de-CH', ...test.info().project.use });
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Bei Quookly anmelden' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/sign-in-de-CH.png', fullPage: true });
    await context.close();
  });
});
