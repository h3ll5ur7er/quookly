import { claim, letIn, signIn } from './support';
import { expect, test } from '@playwright/test';

/**
 * Pictures of the screens that had none.
 *
 * The suite takes screenshots as it goes, wherever a test is already standing in front of
 * something worth looking at. The screens built in Phases 6b and 7 arrived without that
 * habit, and a screen nobody has a picture of is a screen nobody reviews.
 *
 * These assert almost nothing on purpose. What they are for is the picture.
 */

test.describe.configure({ mode: 'serial' });

let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test('the Academy', async ({ page }) => {
  await page.goto('/academy');
  await expect(page.getByRole('heading', { name: 'Academy' })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/academy-list.png', fullPage: true });
});

test('a page in the Academy', async ({ page }) => {
  await page.goto('/academy/blanch');
  await expect(page.getByRole('heading', { name: 'blanch' })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/academy-page.png', fullPage: true });
});

test('writing one', async ({ page }) => {
  await page.goto('/academy/new');
  await expect(page.getByRole('heading', { name: 'Write a page' })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/academy-write.png', fullPage: true });
});

test('a term several pages claim', async ({ page }) => {
  await page.goto('/academy/terms/spatchcock');
  await expect(page.getByText('Nobody has explained that yet')).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/academy-term.png', fullPage: true });
});

test('the ingredient registry', async ({ page }) => {
  await page.goto('/settings/registry');
  await expect(page.getByRole('heading', { name: 'Ingredient registry' })).toBeVisible();
  // Waited for, or the picture is of the word "Loading…" rather than of the screen.
  await expect(page.locator('.registry__entry').first()).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/registry.png', fullPage: true });
});

test('one entry in it', async ({ page }) => {
  await page.goto('/settings/registry/plain-flour');
  await expect(page.getByRole('heading', { name: 'plain flour' })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/registry-entry.png', fullPage: true });
});

test('the queue of people asking to be let in', async ({ page, request }) => {
  await letIn(request, headers.Authorization.replace('Bearer ', ''), {
    email: `hopeful-${Date.now()}@example.com`,
    display_name: 'Someone',
    password: 'a-sufficiently-long-password',
  });
  await page.goto('/settings/applications');
  await page.screenshot({ path: 'e2e/screenshots/applications.png', fullPage: true });
});

test('the form somebody applies with', async ({ browser }) => {
  // Its own context: the shared page is signed in, and this screen is for somebody who is
  // not. The signed-in session in storage would send them somewhere else.
  const context = await browser.newContext({ ...test.info().project.use });
  try {
    const visitor = await context.newPage();
    await visitor.goto('/apply');
    await expect(visitor.getByRole('heading', { name: 'Apply for an account' })).toBeVisible();
    await visitor.screenshot({ path: 'e2e/screenshots/apply.png', fullPage: true });

    await visitor.goto('/');
    await visitor.screenshot({ path: 'e2e/screenshots/landing-visitor.png', fullPage: true });
  } finally {
    await context.close();
  }
});
