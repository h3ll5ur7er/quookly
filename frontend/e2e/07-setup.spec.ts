import { claim, emptyKitchen, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Guided setup (UC-10.2, UC-10.3), against a real instance.
 *
 * The property worth proving here is that nothing stores progress: the checklist is
 * worked out from the profile every time it is asked for (ADR-014). So these tests change
 * the profile through other screens and check that setup notices — including noticing
 * that something has been undone.
 */

let token: string;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ request }) => {
  token = await claim(request);

  // Earlier files leave a kitchen behind; setup is about a profile that has none.
  await emptyKitchen(request, { Authorization: `Bearer ${token}` });
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

function stepFor(page: import('@playwright/test').Page, title: string) {
  return page.locator('.setup__step').filter({ hasText: title });
}

test.describe('the checklist', () => {
  test('shows the whole road rather than one door at a time', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.locator('.setup__step')).toHaveCount(4);
  });

  test('says why each step is worth doing', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.getByText(/scaled to the people at your table/)).toBeVisible();
  });

  test('has no accessibility violations', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.locator('.setup__step').first()).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });

  test('looks like this', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.locator('.setup__step').first()).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/setup.png', fullPage: true });
  });
});

test.describe('doing the work settles a step', () => {
  test('recording somebody settles the household', async ({ page }) => {
    await page.goto('/setup');
    await expect(stepFor(page, 'Who you cook for')).not.toHaveClass(/setup__step--done/);

    await stepFor(page, 'Who you cook for').getByRole('link', { name: 'Add someone' }).click();
    await page.getByLabel('Name', { exact: true }).fill('Ada');
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page).toHaveURL(/\/household$/);

    await page.goto('/setup');
    await expect(stepFor(page, 'Who you cook for')).toHaveClass(/setup__step--done/);
  });

  test('a household with nobody restricted is still asked about constraints', async ({ page }) => {
    /* The distinction the design rests on: silence could mean either thing. */
    await page.goto('/setup');
    await expect(stepFor(page, 'What they avoid')).not.toHaveClass(/setup__step--done/);
  });

  test('the operator can see what the instance is pointed at', async ({ page }) => {
    /* UC-8.2. The e2e instance has no provider configured, which is a realistic
       self-hosted setup and the state most worth reporting clearly. */
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Recipe reading' })).toBeVisible();
    await expect(page.getByText('No model is configured')).toBeVisible();
    await expect(page.getByText('QUOOKLY_INFERENCE_BASE_URL')).toBeVisible();
  });

  test('choosing a unit settles the units step', async ({ page }) => {
    await page.goto('/settings');
    await page.getByLabel('Liquids').selectOption('dl');
    await page.goto('/setup');
    await expect(stepFor(page, 'How you measure')).toHaveClass(/setup__step--done/);
  });
});

test.describe('answering with nothing', () => {
  test('settles the step, and says which answer settled it', async ({ page }) => {
    await page.goto('/setup');
    await stepFor(page, 'What they avoid')
      .getByRole('button', { name: 'Nobody avoids anything' })
      .click();
    await expect(stepFor(page, 'What they avoid')).toHaveClass(/setup__step--done/);
    await expect(page.getByText('You said nobody avoids anything')).toBeVisible();
  });

  test('survives a reload, because it was recorded rather than remembered', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.getByText('You said nobody avoids anything')).toBeVisible();
  });
});

test.describe('finishing', () => {
  test('never asks about the language, because signing in already answered it', async ({
    page,
  }) => {
    /* The language a cook reads in is settled at sign-in and written to the account there
       (ADR-066), so by the time setup is reached it is not outstanding — it is recorded,
       and this list is of what is still to do. It used to be a question with a "the
       current language suits me" button under it. */
    await page.goto('/setup');
    await expect(stepFor(page, 'Your language')).toHaveClass(/setup__step--done/);
    await expect(
      stepFor(page, 'Your language').getByRole('button', {
        name: 'The current language suits me',
      }),
    ).toHaveCount(0);
  });

  test('says so once nothing is outstanding, and points somewhere useful', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.getByText('Everything is set')).toBeVisible();
    await page.getByRole('link', { name: 'See your recipes' }).click();
    await expect(page).toHaveURL(/\/recipes$/);
  });

  test('looks like this when it is done', async ({ page }) => {
    await page.goto('/setup');
    await expect(page.getByText('Everything is set')).toBeVisible();
    await page.screenshot({ path: 'e2e/screenshots/setup-complete.png', fullPage: true });
  });
});

test.describe('it stays true', () => {
  test('removing everybody reopens the household step', async ({ page, request }) => {
    /*
     * The whole reason nothing is stored. A completion flag would still say the household
     * was set up, and setup would be lying about a profile it could simply have read.
     */
    const auth = { Authorization: `Bearer ${token}` };
    for (const person of await (await request.get('/api/v1/eaters', { headers: auth })).json()) {
      await request.delete(`/api/v1/eaters/${person.id}`, { headers: auth });
    }
    await page.goto('/setup');
    await expect(stepFor(page, 'Who you cook for')).not.toHaveClass(/setup__step--done/);
    await expect(page.getByText('Everything is set')).toHaveCount(0);
  });

  test('but a question that was answered stays answered', async ({ page }) => {
    /* They were asked and they answered. Emptying the household does not unask it. */
    await page.goto('/setup');
    await expect(stepFor(page, 'What they avoid')).toHaveClass(/setup__step--done/);
  });
});
