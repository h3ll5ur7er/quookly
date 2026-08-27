import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { claim } from './support';

/**
 * The front door (UC-10.6).
 *
 * A visitor arrives, reads what this is, applies, is told to wait, and is let in by an
 * administrator. Every step of that exists in a unit test somewhere; what only this can
 * check is that the steps join up — and that somebody refused at sign-in is told which of
 * the three refusals it was.
 */

const ADMIN = {
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

/** A fresh applicant per run, so a second run does not collide with the first. */
const APPLICANT = {
  name: 'Ana',
  email: `ana-${Date.now()}@example.com`,
  password: 'a-sufficiently-long-password',
};

test.describe.configure({ mode: 'serial' });

// The landing page is what a *claimed* instance shows a visitor; an unclaimed one asks
// for its first administrator instead. Claimed here so the file can be run on its own,
// and because the administrator below has to exist for the queue half of it.
test.beforeAll(async ({ request }) => {
  await claim(request, {
    email: ADMIN.email,
    display_name: 'Emanuel',
    password: ADMIN.password,
  });
});

test('a visitor is told what this is before being asked for anything', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('The recipe');
  await expect(page.locator('input')).toHaveCount(0);
});

test('the landing page has no accessibility violations', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  const scan = await new AxeBuilder({ page }).analyze();
  expect(scan.violations).toEqual([]);
});

test('looks like this to somebody who has just arrived', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/landing-phone.png', fullPage: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/landing-laptop.png', fullPage: true });
});

test('a visitor can apply, and is told what happens next', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Ask for an account' }).click();
  await expect(page).toHaveURL(/\/apply$/);

  await page.getByLabel('Your name').fill(APPLICANT.name);
  await page.getByLabel('Email').fill(APPLICANT.email);
  await page.getByLabel('Password').fill(APPLICANT.password);
  await page.getByRole('button', { name: 'Ask to be let in' }).click();

  await expect(page.getByRole('heading', { name: 'Your application is in' })).toBeVisible();
});

test('signing in before being let in says so, rather than blaming the password', async ({
  page,
}) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(APPLICANT.email);
  await page.getByLabel('Password').fill(APPLICANT.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByRole('alert')).toContainText('waiting');
  await expect(page.getByRole('alert')).not.toContainText('did not match');
});

test('an admin finds the queue from settings and lets them in', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(ADMIN.email);
  await page.getByLabel('Password').fill(ADMIN.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto('/settings');
  await page.getByRole('link', { name: 'See who is waiting' }).click();
  await expect(page).toHaveURL(/\/settings\/applications$/);

  const row = page.locator('.applications__row').filter({ hasText: APPLICANT.email });
  await expect(row).toHaveCount(1);
  await row.getByRole('button', { name: 'Let them in' }).click();

  await expect(page.getByRole('status')).toContainText('can now sign in');
  await expect(page.locator('.applications__row').filter({ hasText: APPLICANT.email })).toHaveCount(
    0,
  );
});

test('and then they can sign in, onto a kitchen with something in it', async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(APPLICANT.email);
  await page.getByLabel('Password').fill(APPLICANT.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/$/);
  await page.goto('/recipes');
  await expect(page.locator('.recipes__link').first()).toBeVisible();
});

test('an ordinary cook is not offered the queue', async ({ page }) => {
  // The queue is a list of email addresses of people who wanted in here.
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(APPLICANT.email);
  await page.getByLabel('Password').fill(APPLICANT.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto('/settings');
  await expect(page.getByRole('link', { name: 'See who is waiting' })).toHaveCount(0);
});
