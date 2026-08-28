import { claim } from './support';
import { expect, test } from '@playwright/test';

/**
 * The language a cook reads in is the one on their account (L6, ADR-066).
 *
 * A household shares a device and usually a browser. If the operating system is English
 * because it belongs to somebody else, the German-speaking cook in the house must still be
 * able to sign in and read German — without reconfiguring a machine that is not theirs.
 *
 * The failure this exists to catch is not "the interface is in the wrong language". It is
 * the *disagreement*: the interface followed the browser and the server resolved ingredient
 * names from the account, so a German screen said "caster sugar" and a German cooking step
 * gave the amounts in a language nobody had chosen. Both halves are asserted here, because
 * either one alone passes while the product still contradicts itself.
 */

let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };
});

test.afterAll(async ({ request }) => {
  /* Put the shared account back in English. The suite runs one worker against one
     database, so a file that leaves the account in German hands every file after it a
     German screen — which, now that the account decides the language, is exactly what it
     should do and exactly what nobody after this asked for. */
  await request.put('/api/v1/setup/locale', { headers, data: { locale: 'en-GB' } });
});

/** An English browser, always. That is the whole point of the test. */
const ENGLISH_DEVICE = { locale: 'en-GB' } as const;

test('a German account reads German on an English browser', async ({ browser, request }) => {
  // The account says German. Nothing else in this test does.
  const chosen = await request.put('/api/v1/setup/locale', {
    headers,
    data: { locale: 'de-CH' },
  });
  expect(chosen.ok(), await chosen.text()).toBe(true);

  const context = await browser.newContext({ ...test.info().project.use, ...ENGLISH_DEVICE });
  try {
    const page = await context.newPage();
    await page.goto('/sign-in');
    // Signed out, this is the device's language: English, as the browser asks.
    await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();

    await page.locator('#email').fill('chef@example.com');
    await page.locator('#password').fill('a-sufficiently-long-password');
    await page.locator('button[type="submit"]').click();

    // Signed in, it is the account's. The reload is the adoption happening.
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'de-CH');

    // And the other half: the food is named in the same language as the furniture around
    // it. This is the assertion that fails when only one of the two follows the account.
    await page.goto('/pantry');
    await expect(page.getByText('Vorrat').first()).toBeVisible();
    await expect(page.getByText('plain flour')).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('signing out gives the device its own language back', async ({ browser }) => {
  /* The language belonged to the person, not to the box. Leaving it behind hands the next
     cook at this device somebody else's language — and hands their account that language
     the first time they sign in without one of their own. */
  const context = await browser.newContext({ ...test.info().project.use, ...ENGLISH_DEVICE });
  try {
    const page = await context.newPage();
    await page.goto('/sign-in');
    await page.locator('#email').fill('chef@example.com');
    await page.locator('#password').fill('a-sufficiently-long-password');
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'de-CH');

    await page.goto('/settings');
    await page.getByRole('button', { name: /Abmelden|Sign out/ }).click();

    await expect(page.locator('html')).toHaveAttribute('lang', 'en-GB');
  } finally {
    await context.close();
  }
});
