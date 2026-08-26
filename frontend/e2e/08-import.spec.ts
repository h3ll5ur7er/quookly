import { claim, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Importing a recipe from a link (UC-1.3), on a phone, against a real instance.
 *
 * The instance under test has no inference provider configured, which is a realistic
 * self-hosted setup and makes the two paths distinguishable without a model: a page that
 * publishes its recipe data imports, and one that does not is refused with a reason.
 *
 * The pages being imported are served by a second local server and really fetched. They
 * cannot be stubbed in the browser: the fetch happens on the *server*, so intercepting it
 * in the page would intercept nothing. Nor can they be real recipe sites — a suite that
 * depends on one staying up fails for reasons that are nobody's fault.
 */

/** Where the fixture pages are served from. See `playwright.config.ts`. */
const PAGES = 'http://127.0.0.1:8182';

/**
 * Paste a link and wait for the answer.
 *
 * Every test that needs a result does the import itself: each test gets a fresh page, so
 * one that assumed the previous test's outcome were still on screen would be asserting
 * against an empty form.
 */
async function importing(page: import('@playwright/test').Page, path: string): Promise<void> {
  await page.goto('/recipes/import');
  await page.getByLabel('Address of the recipe').fill(`${PAGES}/${path}`);
  await page.getByRole('button', { name: 'Import' }).click();
}

test.describe.configure({ mode: 'serial' });

// Claimed here rather than inherited from whichever file ran first, so this one can
// be run on its own.
test.beforeAll(async ({ request }) => {
  await claim(request);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
  // Signing in lands on Home; this file is about the recipes.
  await page.goto('/recipes');
});

test.describe('finding it', () => {
  test('the recipe list offers a way to add one', async ({ page }) => {
    await page.getByRole('link', { name: 'Import from a link' }).click();
    await expect(page).toHaveURL(/\/recipes\/import$/);
    await expect(page.getByRole('heading', { name: 'Import from a link' })).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/recipes/import');
    await expect(page.getByLabel('Address of the recipe')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('makes every touch target large enough to hit', async ({ page }) => {
    await page.goto('/recipes/import');
    await expect(page.getByLabel('Address of the recipe')).toBeVisible();
    const undersized = await page.evaluate(() => {
      const MINIMUM = 44;
      return [...document.querySelectorAll('input, button, select, a')]
        .map((node) => ({ node, box: node.getBoundingClientRect() }))
        .filter(({ box }) => box.x >= 0 && box.y >= 0 && box.width > 0)
        .filter(({ box }) => box.height < MINIMUM)
        .map(({ node }) => node.outerHTML.slice(0, 60));
    });
    expect(undersized).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/recipes/import');
    await expect(page.getByLabel('Address of the recipe')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/import.png', fullPage: true });
  });
});

test.describe('what it refuses before asking', () => {
  test('an empty box cannot be submitted', async ({ page }) => {
    await page.goto('/recipes/import');
    await expect(page.getByRole('button', { name: 'Import' })).toBeDisabled();
  });

  test('something that is not a web address cannot be submitted', async ({ page }) => {
    /* The API refuses it too, but a round trip to be told so is a wasted wait. */
    await page.goto('/recipes/import');
    await page.getByLabel('Address of the recipe').fill('my pancake recipe');
    await expect(page.getByRole('button', { name: 'Import' })).toBeDisabled();
  });
});

test.describe('a page that publishes its recipe', () => {
  test('imports, and says what it got', async ({ page }) => {
    await importing(page, 'waffles.html');
    await expect(page.getByRole('heading', { name: 'Buttermilk Waffles' })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText('Imported.')).toBeVisible();
  });

  test('leaves the life story behind', async ({ page }) => {
    /* The founding use case. None of the radiator, none of the newsletter. */
    await importing(page, 'waffles.html');
    await expect(page.getByText('Imported.')).toBeVisible({ timeout: 30_000 });
    const shown = await page.locator('main').innerText();
    expect(shown).not.toContain('1998');
    expect(shown).not.toContain('newsletter');
  });

  test('names an ingredient it had never seen', async ({ page }) => {
    /*
     * Nothing is known about a new entry's allergens, so a recipe using one reads as
     * unknown until somebody looks. Saying so is what stops that being silent.
     *
     * Its own page, with an ingredient nothing else uses: an entry is new only once, and
     * asserting this against a page another test has already imported would pass or fail
     * on the order the suite happened to run in.
     */
    await importing(page, 'oddments.html');
    await expect(page.getByText('nothing is known about what they contain')).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator('.import__new')).toContainText('yuzu kosho');
  });

  test('says nothing about ingredients it already knew', async ({ page }) => {
    /* The other half. A page of staples should not ask a cook to check anything. */
    await importing(page, 'staples.html');
    await expect(page.getByText('Imported.')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('nothing is known about what they contain')).toHaveCount(0);
  });

  test('does not claim a model read a page that published its own data', async ({ page }) => {
    await importing(page, 'waffles.html');
    await expect(page.getByText('Imported.')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('read through by a model')).toHaveCount(0);
  });

  test('looks like this', async ({ page }) => {
    await importing(page, 'waffles.html');
    await expect(page.getByText('Imported.')).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: 'e2e/screenshots/import-done.png', fullPage: true });
  });

  test('leads into the recipe, which is now in the list', async ({ page }) => {
    await importing(page, 'waffles.html');
    await expect(page.getByText('Imported.')).toBeVisible({ timeout: 30_000 });
    await page.getByRole('link', { name: 'Open the recipe' }).click();
    await expect(page.getByRole('heading', { name: 'Buttermilk Waffles' })).toBeVisible();
    await page.goto('/recipes');
    await expect(page.getByText('Buttermilk Waffles').first()).toBeVisible();
  });
});

test.describe('when it cannot be read', () => {
  test('a page that is not there says so', async ({ page }) => {
    await page.goto('/recipes/import');
    await page.getByLabel('Address of the recipe').fill(`${PAGES}/no-such-page.html`);
    await page.getByRole('button', { name: 'Import' }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 30_000 });
  });

  test('a page with no recipe data and no model says exactly that', async ({ page }) => {
    /* The instance under test has no provider configured. "Reading it needs a model, and
       this instance has none" is something an operator can act on, and it is the honest
       answer rather than a generic failure. */
    await page.goto('/recipes/import');
    await page.getByLabel('Address of the recipe').fill(`${PAGES}/story.html`);
    await page.getByRole('button', { name: 'Import' }).click();
    await expect(page.getByRole('alert')).toContainText(/model/i, { timeout: 30_000 });
  });

  test('looks like this when it fails', async ({ page }) => {
    await importing(page, 'story.html');
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: 'e2e/screenshots/import-failed.png', fullPage: true });
  });

  test('and the cook can try again', async ({ page }) => {
    await importing(page, 'story.html');
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: 'Import' })).toBeEnabled();
    await expect(page.getByText('Reading the page')).toHaveCount(0);
  });
});
