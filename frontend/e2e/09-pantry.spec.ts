import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The pantry, on a phone, against a real instance.
 *
 * Less about the shape of the page than about whether the pantry keeps telling the
 * truth: that a packet keeps its own date, that correcting a number is not recorded as
 * waste, and that a warning names the bag going off rather than the ingredient.
 */

const COOK = {
  email: 'chef@example.com',
  password: 'a-sufficiently-long-password',
};

/** Far enough out that it never falls inside the "use soon" window as the suite ages. */
const DISTANT = '2099-12-01';

test.describe.configure({ mode: 'serial' });

/** The date input takes an ISO value regardless of how the locale displays it. */
async function fillDate(page: import('@playwright/test').Page, value: string): Promise<void> {
  await page.locator('#expires_on').fill(value);
}

async function receive(
  page: import('@playwright/test').Page,
  what: string,
  amount: string,
  options: { readonly unit?: string; readonly on?: string; readonly note?: string } = {},
): Promise<void> {
  await page.goto('/pantry/add');
  await page.getByLabel('What is it').fill(what);
  // The picker resolves against the registry as the cook types; the unit follows.
  await expect(page.locator('#pantryMatches option').first()).toBeAttached();
  await page.getByLabel('How much').fill(amount);
  if (options.unit !== undefined) {
    await page.getByLabel('Unit').selectOption(options.unit);
  }
  if (options.on !== undefined) {
    await fillDate(page, options.on);
  }
  if (options.note !== undefined) {
    await page.getByLabel('Note').fill(options.note);
  }
  await page.getByRole('button', { name: 'Add to pantry' }).click();
  await expect(page).toHaveURL(/\/pantry$/);
}

/**
 * Open one packet from the shelf.
 *
 * Scoped to its ingredient's card, because "500 g" is a thing a cook can have two of.
 */
async function openLot(
  page: import('@playwright/test').Page,
  ingredient: string,
  quantity: RegExp,
): Promise<void> {
  await page.goto('/pantry');
  const card = page.locator('.pantry__entry').filter({ hasText: ingredient });
  await card.getByRole('link', { name: quantity }).click();
  await expect(page).toHaveURL(/\/pantry\/lots\/\d+$/);
}

/** Today plus `days`, as the date input wants it. */
function inDays(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() + days);
  return when.toISOString().slice(0, 10);
}

test.beforeEach(async ({ page }) => {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(COOK.email);
  await page.getByLabel('Password').fill(COOK.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/recipes$/);
});

test.describe('an empty pantry', () => {
  test('is reachable from anywhere in the app', async ({ page }) => {
    await page.getByRole('link', { name: 'Pantry' }).click();
    await expect(page).toHaveURL(/\/pantry$/);
    await expect(page.getByRole('heading', { name: 'Pantry' })).toBeVisible();
  });

  test('explains itself instead of showing a blank page', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByText(/Nothing in your pantry yet/)).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByRole('link', { name: 'Add stock' })).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByRole('link', { name: 'Add stock' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/pantry-empty.png', fullPage: true });
  });
});

test.describe('putting the shopping away', () => {
  test('offers the units the ingredient is actually measured in', async ({ page }) => {
    await page.goto('/pantry/add');
    await page.getByLabel('What is it').fill('whole milk');
    await expect(page.locator('#pantryMatches option').first()).toBeAttached();
    const offered = await page.locator('#unit option').allTextContents();
    expect(offered).toContain('ml');
    expect(offered).not.toContain('g');
  });

  test('starts on the unit this cook reads that kind in', async ({ page }) => {
    // This cook chose decilitres for liquids during setup. The pantry starts there
    // rather than at the shipped default: a form that argues with a preference the cook
    // has already stated is a form they stop trusting.
    await page.goto('/pantry/add');
    await page.getByLabel('What is it').fill('whole milk');
    await expect(page.locator('#pantryMatches option').first()).toBeAttached();
    await expect(page.getByLabel('Unit')).toHaveValue('dl');
  });

  test('refuses a name the registry has never heard of', async ({ page }) => {
    await page.goto('/pantry/add');
    await page.getByLabel('What is it').fill('unicorn tears');
    await page.getByLabel('How much').fill('500');
    await page.getByRole('button', { name: 'Add to pantry' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page).toHaveURL(/\/pantry\/add$/);
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/pantry/add');
    await expect(page.getByLabel('What is it')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('makes every touch target large enough to hit', async ({ page }) => {
    await page.goto('/pantry/add');
    await expect(page.getByLabel('What is it')).toBeVisible();
    const undersized = await page.evaluate(() => {
      const MINIMUM = 44;
      return [...document.querySelectorAll('input, button, select, a')]
        .map((node) => ({ node, box: node.getBoundingClientRect() }))
        .filter(({ box }) => box.x >= 0 && box.y >= 0 && box.width > 0)
        .filter(({ box }) => box.height < MINIMUM)
        .map(({ node, box }) => `${node.tagName.toLowerCase()} ${box.height.toFixed(1)}px`);
    });
    expect(undersized).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/pantry/add');
    await expect(page.getByLabel('What is it')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/pantry-add.png', fullPage: true });
  });

  test('records a packet with the date that is on it', async ({ page }) => {
    await receive(page, 'plain flour', '1', { unit: 'kg', on: DISTANT, note: 'Coop' });
    await expect(page.getByText('plain flour')).toBeVisible();
    await expect(page.getByText('Coop')).toBeVisible();
  });

  test('keeps two packets apart rather than adding them into one', async ({ page }) => {
    await receive(page, 'plain flour', '500', { unit: 'g', on: inDays(2) });
    await page.goto('/pantry');
    // Two lots, one total. The total is the sum; the lots keep their own dates.
    await expect(page.locator('.pantry__lot')).toHaveCount(2);
    await expect(page.locator('.pantry__total')).toHaveText('1.5 kg');
  });
});

test.describe('what wants using', () => {
  test('names the packet going off, not the ingredient in general', async ({ page }) => {
    await page.goto('/pantry');
    const soon = page.locator('[aria-labelledby="usingSoon"]');
    await expect(soon).toBeVisible();
    await expect(soon.getByText('500 g')).toBeVisible();
    await expect(soon.getByText('1 kg')).toHaveCount(0);
  });

  test('says how soon in words rather than in a count of days', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByText(/Use within|Use by tomorrow|Use today/).first()).toBeVisible();
  });

  test('has no accessibility violations with stock in it', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByText('plain flour').first()).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/pantry');
    await expect(page.getByText('plain flour').first()).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/pantry.png', fullPage: true });
  });
});

test.describe('one packet', () => {
  test('opens filled in with what is recorded', async ({ page }) => {
    await openLot(page, 'plain flour', /1 kg/);
    await expect(page.getByLabel('How much is left')).toHaveValue('1');
    await expect(page.getByText('kg').first()).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await openLot(page, 'plain flour', /1 kg/);
    await expect(page.getByLabel('How much is left')).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('offers exactly one filled action', async ({ page }) => {
    await openLot(page, 'plain flour', /1 kg/);
    await expect(page.getByLabel('How much is left')).toBeVisible();
    const filled = await page.evaluate(() => {
      const ground = getComputedStyle(document.body).getPropertyValue('--primary').trim();
      return [...document.querySelectorAll('button')].filter(
        (one) => getComputedStyle(one).backgroundColor === ground,
      ).length;
    });
    expect(filled).toBeLessThanOrEqual(1);
  });

  test('looks like this', async ({ page }) => {
    await openLot(page, 'plain flour', /1 kg/);
    await expect(page.getByLabel('How much is left')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/pantry-lot.png', fullPage: true });
  });

  test('restates what is left rather than subtracting what has gone', async ({ page }) => {
    await openLot(page, 'plain flour', /1 kg/);
    await page.getByLabel('How much is left').fill('0.5');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page).toHaveURL(/\/pantry$/);
    await expect(page.locator('.pantry__total')).toHaveText('1 kg');
  });

  test('asks why before recording waste', async ({ page }) => {
    await openLot(page, 'plain flour', /0\.5 kg/);
    await page.getByRole('button', { name: 'I threw some away' }).click();
    await expect(page.getByLabel('Why')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/pantry-waste.png', fullPage: true });
  });

  test('records waste without pretending it was a correction', async ({ page }) => {
    await openLot(page, 'plain flour', /0\.5 kg/);
    await page.getByRole('button', { name: 'I threw some away' }).click();
    await page.getByLabel('How much was thrown away').fill('0.2');
    await page.getByLabel('Why').selectOption('expired');
    await page.getByRole('button', { name: 'Record waste' }).click();
    await expect(page).toHaveURL(/\/pantry$/);
    await expect(page.locator('.pantry__total')).toHaveText('800 g');
  });

  test('refuses to delete a packet with waste recorded against it', async ({ page }) => {
    /*
     * The record would be left pointing at nothing, and the figure the cook is trying to
     * bring down would quietly shrink. Refused in words, with what to do instead.
     */
    await openLot(page, 'plain flour', /0\.3 kg/);
    await page.getByRole('button', { name: /never here/ }).click();
    await expect(page.getByRole('alert')).toContainText(/already recorded waste/);
    await expect(page).toHaveURL(/\/pantry\/lots\/\d+$/);
  });

  test('removes a packet that was never here', async ({ page }) => {
    await receive(page, 'caster sugar', '500', { unit: 'g' });
    await openLot(page, 'caster sugar', /500 g/);
    await page.getByRole('button', { name: /never here/ }).click();
    await expect(page).toHaveURL(/\/pantry$/);
    await expect(page.getByText('caster sugar')).toHaveCount(0);
  });

  test('says so when the packet is not there', async ({ page }) => {
    await page.goto('/pantry/lots/99999');
    await expect(page.getByRole('heading', { name: 'No such stock' })).toBeVisible();
  });
});
