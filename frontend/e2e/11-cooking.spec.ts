import { claim, emptyKitchen, noSessionOpen, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Cooking mode, on a phone, against a real instance.
 *
 * Phase 5's promise end to end: start a session, prep from the list, run a timer, put the
 * phone down, pick it up again, finish, and find the pantry updated. Which means these
 * tests care about two things the unit tests cannot see — that the screen is legible with
 * hands full, and that leaving is not the same as stopping.
 */

/** A week of its own, so nothing here collides with the planning spec's dates. */
const MONDAY = '2027-06-07';
const SUNDAY = '2027-06-13';

test.describe.configure({ mode: 'serial' });

/** Held from `beforeAll` so the per-test reset below does not sign in seven more times. */
let headers: Record<string, string>;

/** Enough butter and flour that the meal has something to take. */
test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };
  // Before stocking: this file finds its meal on the plan, and a plan an earlier file left
  // behind is a different meal with the same buttons.
  await emptyKitchen(request, headers);

  const registry = await request.get('/api/v1/ingredients?search=unsalted%20butter', { headers });
  const entries = (await registry.json()) as { id: number; slug: string }[];
  const butter = entries.find((entry) => entry.slug === 'unsalted-butter')!;

  await request.post('/api/v1/pantry', {
    data: { ingredient_id: butter.id, magnitude: '500', unit: 'g' },
    headers,
  });
});

/**
 * Put down anything a previous test left cooking.
 *
 * Sessions are resumable on purpose, which means one test's half-finished recipe is the
 * next one's starting position unless something says otherwise. Abandoning through the API
 * rather than walking backwards through the UI: the walk is what is being tested elsewhere,
 * and a test that sets itself up by exercising the feature cannot fail cleanly.
 */
test.beforeEach(async ({ request }) => {
  // Every test in this file starts from no session, whatever the one before it left.
  await noSessionOpen(request, headers);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

/**
 * The one meal these tests cook, put on the plan once and reopened from the week.
 *
 * Navigated to by date rather than clicked through, because "the first empty day" moves
 * as soon as one of them is filled — and a helper that placed a second Shortbread would
 * be testing a week nobody planned.
 */
async function meal(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/plans');
  // Waited for, because counting the list before it has arrived reads as "no such week"
  // — and then this helper quietly opens a second plan for the same days, and every test
  // after it is cooking a meal nobody planned.
  await expect(page.locator('.plans__loading')).toHaveCount(0);

  const existing = page.getByRole('link', { name: /Jun 2027/ });
  if ((await existing.count()) === 0) {
    await page.locator('#starts_on').fill(MONDAY);
    await page.locator('#ends_on').fill(SUNDAY);
    await page.getByRole('button', { name: 'Start planning' }).click();
  } else {
    await existing.first().click();
  }
  await expect(page).toHaveURL(/\/plans\/\d+$/);

  const planId = page.url().split('/').pop();
  await page.goto(`/plans/${planId}/meal?on=${MONDAY}&meal=dinner`);
  await expect(page.locator('#recipe_id')).toBeVisible();

  if ((await page.locator('#recipe_id').inputValue()) === '') {
    await page.locator('#recipe_id').selectOption({ label: 'Shortbread' });
    await page.getByRole('button', { name: 'Save this meal' }).click();
    await expect(page).toHaveURL(/\/plans\/\d+$/);
    await page.goto(`/plans/${planId}/meal?on=${MONDAY}&meal=dinner`);
    await expect(page.locator('#recipe_id')).toBeVisible();
  }
}

/** In the kitchen, on the meal planned above, at the prep list where a session begins. */
async function cooking(page: import('@playwright/test').Page): Promise<void> {
  await meal(page);
  await page.getByRole('button', { name: 'Cook this now' }).click();
  await expect(page).toHaveURL(/\/cook\/\d+$/);
  await expect(page.getByRole('heading', { name: 'Get everything ready' })).toBeVisible();
}

test.describe('getting ready', () => {
  test('cooking mode opens from the meal on the plan', async ({ page }) => {
    await cooking(page);
    await expect(page.getByRole('heading', { name: 'Shortbread' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Get everything ready' })).toBeVisible();
  });

  test('the app’s furniture gets out of the way', async ({ page }) => {
    /* A navigation bar under a recipe somebody is halfway through is an invitation to
       leave in the middle of it, and a thing to knock with a wet thumb. */
    await cooking(page);
    await expect(page.getByRole('navigation', { name: 'Sections' })).toHaveCount(0);
    await expect(page.getByLabel('Language')).toHaveCount(0);
  });

  test('the prep list groups the work and leaves the weighing last', async ({ page }) => {
    await cooking(page);
    const titles = page.locator('.cook__group-title');
    await expect(titles.first()).toHaveText('softened');
    await expect(titles.last()).toHaveText('Weigh out');
  });

  test('the prep list carries the amounts', async ({ page }) => {
    await cooking(page);
    const row = page.locator('.cook__tick').filter({ hasText: 'plain flour' });
    await expect(row.locator('.cook__amount')).toHaveText('340 g');
  });

  test('something ticked off stays ticked', async ({ page }) => {
    await cooking(page);
    const row = page.locator('.cook__tick').filter({ hasText: 'plain flour' });
    await row.click();
    await expect(row).toHaveClass(/cook__tick--done/);
  });

  test('has no accessibility violations', async ({ page }) => {
    await cooking(page);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await cooking(page);
    await page.screenshot({ path: 'e2e/screenshots/cook-prep.png', fullPage: true });
  });
});

test.describe('a step at a time', () => {
  test('starting puts the first instruction on the screen', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await expect(page.locator('.cook__instruction')).toHaveText(
      'Cream the butter and sugar until pale.',
    );
  });

  test('the step carries the amounts it asks for', async ({ page }) => {
    /* No scrolling back to the ingredient list with your hands in a bowl (ADR-040). */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await expect(page.locator('.cook__lines')).toContainText('225 g');
    await expect(page.locator('.cook__lines')).toContainText('unsalted butter');
  });

  test('the instruction is legible from a metre away', async ({ page }) => {
    /* Measured rather than asserted about a class: cooking mode raises the density, and a
       step set at reading size is the failure this mode exists to prevent (NFR-12). */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    const size = await page
      .locator('.cook__instruction')
      .evaluate((node) => parseFloat(getComputedStyle(node).fontSize));
    expect(size).toBeGreaterThanOrEqual(24);
  });

  test('every control is large enough for a knuckle', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    const undersized = await page.evaluate(() => {
      const MINIMUM = 48;
      return (
        [...document.querySelectorAll('button, a')]
          // The skip link is a keyboard affordance that appears on focus, not something
          // anybody aims a knuckle at.
          .filter((node) => !node.matches('.skip'))
          .map((node) => ({ node, box: node.getBoundingClientRect() }))
          .filter(({ box }) => box.width > 0 && box.height > 0)
          .filter(({ box }) => box.height < MINIMUM)
          .map(({ node, box }) => `${node.textContent?.trim()} ${box.height.toFixed(1)}px`)
      );
    });
    expect(undersized).toEqual([]);
  });

  test('the page never scrolls sideways', async ({ page }) => {
    /* Cooking mode raises the density, which is exactly the setting in which something
       overflows a phone and nobody notices until the last word is off the edge. */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await expect(page.locator('.cook__instruction')).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test('the cook goes on and comes back', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');
    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.locator('.cook__instruction')).toContainText('Cream the butter');
  });

  test('going back from the first step returns to the prep list', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Back' }).click();
    await expect(page.getByRole('heading', { name: 'Get everything ready' })).toBeVisible();
  });

  test('a step a cook can walk away from says so', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    for (let i = 0; i < 3; i++) {
      await page.getByRole('button', { name: 'Next' }).click();
    }
    await expect(page.locator('.cook__instruction')).toContainText('Chill until firm');
    await expect(page.locator('.cook__asks')).toHaveText('you can walk away');
  });

  test('looks like this', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.locator('.cook__instruction')).toContainText('Bake');
    await page.screenshot({ path: 'e2e/screenshots/cook-step.png', fullPage: true });
  });
});

test.describe('a timer', () => {
  test('shows the step’s whole duration before anybody starts it', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await expect(page.locator('.timer__clock')).toHaveText('5:00');
  });

  test('runs, and is still running when the cook comes back', async ({ page }) => {
    /* The whole reason the session lives on the server. Reloading is the closest a browser
       gets to the phone locking and the tab being thrown away (UC-9.7, ADR-013). */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible();
    await expect(page.locator('.timer__clock')).not.toHaveText('5:00');
  });

  test('pausing holds the clock still, and it is still still after a reload', async ({ page }) => {
    /* Two readings a second apart rather than one exact value: comparing against a number
       taken before the pause is a race with the real clock, and the property that matters
       is that the thing has stopped. */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Start', exact: true }).click();
    await expect(page.locator('.timer__clock')).not.toHaveText('5:00');

    await page.getByRole('button', { name: 'Pause' }).click();
    await page.reload();
    await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();

    const held = await page.locator('.timer__clock').textContent();
    await page.waitForTimeout(1500);
    await expect(page.locator('.timer__clock')).toHaveText(held!.trim());
    // And it did not go back to the top: what it counted is still counted.
    expect(held!.trim()).not.toBe('5:00');
  });

  test('resetting puts it back', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Start', exact: true }).click();
    await page.getByRole('button', { name: 'Reset' }).click();
    await expect(page.locator('.timer__clock')).toHaveText('5:00');
  });
});

test.describe('when the connection drops', () => {
  /* The kitchen is often the furthest room from the router (NFR-13). What must not happen
     is the screen going blank halfway through a recipe. */

  test('the cook keeps turning the page', async ({ page, context }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await expect(page.locator('.cook__instruction')).toContainText('Cream the butter');

    await context.setOffline(true);
    await page.getByRole('button', { name: 'Next' }).click();

    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');
    await expect(page.getByText('No connection')).toBeVisible();
    await context.setOffline(false);
  });

  test('a timer says why it will not start rather than losing the time', async ({
    page,
    context,
  }) => {
    /* The instant is the server's, and one stamped on the way back would quietly lose
       however long the connection was down (ADR-013). */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();

    await context.setOffline(true);
    await page.getByRole('button', { name: 'Start', exact: true }).click();

    await expect(page.getByText('Timers need the connection')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeDisabled();
    await context.setOffline(false);
  });

  test('where the cook got to catches up when the network returns', async ({ page, context }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();

    await context.setOffline(true);
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');

    await context.setOffline(false);
    await expect(page.getByText('No connection')).toHaveCount(0);

    // Read back cold, as the tablet in the other room would.
    await page.reload();
    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');
  });
});

test.describe('leaving and coming back', () => {
  test('walking away keeps the session where it was', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    // Confirmed before walking away, or the test would be asserting that a step it never
    // reached was remembered.
    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');

    await page.getByRole('link', { name: 'Leave' }).click();
    await expect(page).toHaveURL(/\/plans$/);

    await meal(page);
    await page.getByRole('button', { name: 'Cook this now' }).click();
    // Waited for, because the assertion below reads the step the session resumed at, and
    // reading it while the previous page is still on screen asserts nothing.
    await expect(page).toHaveURL(/\/cook\/\d+$/);
    await expect(page.locator('.cook__instruction')).toContainText('Work in the flour');
  });
});

test.describe('finishing', () => {
  test('the last step offers to finish rather than to go on', async ({ page }) => {
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    for (let i = 0; i < 5; i++) {
      await page.getByRole('button', { name: 'Next' }).click();
    }
    await expect(page.getByRole('button', { name: 'I am done' })).toBeVisible();
  });

  test('finishing takes what the meal was holding out of the pantry', async ({ page }) => {
    /* Phase 5's "done when", on screen: 500 g of butter, a meal that wanted 225 g, and
       375 g left once it is cooked — no, 275 g. The arithmetic is the pantry's; what is
       checked here is that cooking reached it at all. */
    await cooking(page);
    await page.getByRole('button', { name: 'Start cooking' }).click();
    for (let i = 0; i < 5; i++) {
      await page.getByRole('button', { name: 'Next' }).click();
    }
    await page.getByRole('button', { name: 'I am done' }).click();
    await expect(page.getByRole('heading', { name: 'That is dinner' })).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/cook-done.png', fullPage: true });

    await page.goto('/pantry');
    const butter = page.locator('.pantry__entry').filter({ hasText: 'unsalted butter' });
    await expect(butter.locator('.pantry__total')).toHaveText('275 g');
  });

  test('the meal is a record on the plan afterwards', async ({ page }) => {
    await meal(page);
    await expect(page.getByText('You cooked this')).toBeVisible();
  });
});
