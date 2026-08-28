import { claim, letIn, noSessionOpen, signIn } from './support';
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

test('the same recipe in English, as the control', async ({ page }) => {
  // The German and French captures below are of *this* recipe. Without an English one at
  // the same width, a broken table there cannot be blamed on the translation.
  await page.goto('/recipes/1');
  await expect(page.getByRole('heading', { name: 'Buttermilk Pancakes' })).toBeVisible();
  await page.screenshot({ path: 'e2e/screenshots/recipe-en.png', fullPage: true });
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

/**
 * The app in the other two languages.
 *
 * There was exactly one non-English picture in this suite — the sign-in screen in German —
 * and none in French, while German and French labels run two to three times longer than
 * the English. Nobody had seen the cooking-mode timer buttons say *Réinitialiser*.
 *
 * Signed in inside a context of its own, because the language a cook reads in comes from
 * the browser and the shared page's is English.
 */
for (const [locale, tag] of [
  ['de-CH', 'de'],
  ['fr-CH', 'fr'],
] as const) {
  test(`the screens a cook lives in, in ${locale}`, async ({ browser }) => {
    // The spread first: the project carries a locale of its own, and spreading it
    // afterwards would put these pages back into English.
    const context = await browser.newContext({ ...test.info().project.use, locale });
    try {
      const page = await context.newPage();
      await page.goto('/sign-in');
      // Labelled in the language under test, so found by position rather than by name.
      await page.locator('#email').fill('chef@example.com');
      await page.locator('#password').fill('a-sufficiently-long-password');
      await page.locator('button[type="submit"]').click();
      await expect(page).toHaveURL(/\/$/);

      for (const [path, name] of [
        ['/', 'home'],
        ['/recipes', 'recipes'],
        ['/recipes/1', 'recipe'],
        ['/pantry', 'pantry'],
        ['/shopping', 'shopping'],
        ['/academy', 'academy'],
        ['/settings', 'settings'],
      ] as const) {
        await page.goto(path);
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: `e2e/screenshots/${name}-${tag}.png`, fullPage: true });
      }
    } finally {
      await context.close();
    }
  });
}

/**
 * The dark theme, on the screens a cook lives in.
 *
 * It is the only one of the four that is genuinely a second theme — it inverts the ground
 * rather than tinting it — and the only one whose appearance nobody had ever looked at.
 * Its contrast was checked and passed; a passing check is not a screen anybody has seen
 * (T5). Signed in through a device that asks for dark, so this is the state most of its
 * readers will actually get.
 */
test('the screens a cook lives in, in the dark', async ({ browser }) => {
  const context = await browser.newContext({ ...test.info().project.use, colorScheme: 'dark' });
  try {
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByLabel('Email').fill('chef@example.com');
    await page.getByLabel('Password').fill('a-sufficiently-long-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/$/);

    for (const [path, name] of [
      ['/', 'home'],
      ['/recipes', 'recipes'],
      ['/recipes/1', 'recipe'],
      ['/pantry', 'pantry'],
      ['/plans', 'plans'],
      ['/academy', 'academy'],
      ['/settings/registry', 'registry'],
    ] as const) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `e2e/screenshots/${name}-dark.png`, fullPage: true });
    }
  } finally {
    await context.close();
  }
});

/*
 * Cooking mode in German and French was captured here once and reviewed — the prediction
 * that the timer buttons would wrap was wrong, and `cook-step-de.png` and `cook-step-fr.png`
 * are the evidence. The test itself is gone.
 *
 * It needed a plan, a meal and a session set up through the API, and in a full run it kept
 * arriving at a prep screen whose start button never enabled. Chasing that cost several
 * seven-minute suite runs for two pictures that had already served their purpose, and a
 * screenshot is not worth a flaky test.
 *
 * What that screen actually needs guarding is its width, and that is
 * `21-translated-layouts.spec.ts`, which measures rather than photographs. Adding `/cook`
 * to it is worth doing when the session setup can be made reliable.
 */
