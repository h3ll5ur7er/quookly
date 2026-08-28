import { claim, signIn } from './support';
import { expect, test } from '@playwright/test';

/**
 * The food tree, end to end, against the registry this instance really ships (ADR-067).
 *
 * The unit tests use two categories somebody made up. This one asks the running instance,
 * which is seeded from the Swiss Food Composition Database — so it is also the test that
 * says the *seeding* worked: a tree that is built but never recorded looks exactly like no
 * tree at all, and every screen below falls back to flat without complaining.
 */

let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test('the registry knows where nine hundred foods sit', async ({ request }) => {
  const answered = await request.get('/api/v1/registry/categories', { headers });
  expect(answered.status(), await answered.text()).toBe(200);

  const tree = (await answered.json()) as { slug: string; name: string; parent_slug: string }[];
  const sections = tree.filter((one) => one.parent_slug === null);

  // Nineteen sections and a hundred groups, from the published table. The exact count is
  // not the point — that the tree arrived is.
  expect(sections.length).toBeGreaterThan(10);
  expect(tree.length).toBeGreaterThan(sections.length);

  const vegetables = tree.find((one) => one.slug === 'vegetables');
  expect(vegetables?.name).toBe('Vegetables');
  expect(tree.find((one) => one.slug === 'vegetables-fresh-vegetables')?.parent_slug).toBe(
    'vegetables',
  );
});

test('a section takes the food in the groups under it', async ({ request }) => {
  /* No food sits *on* a section — every leaf the table publishes is a group — so a cook
     asking about "Vegetables" and getting nothing back would be the wrong answer. */
  const listed = await request.get('/api/v1/registry?category=vegetables&limit=200', { headers });
  const page = (await listed.json()) as { entries: { name: string }[]; total: number };

  expect(page.total).toBeGreaterThan(50);
  expect(page.entries.map((one) => one.name)).toContain('carrot');
});

test('the tree is named in the language the cook reads', async ({ browser, request }) => {
  /* Free, and the reason this taxonomy was worth taking from the published table rather
     than inventing: the three editions carry the same categories against identical row
     ids, so nobody translated a word of it (FR-10). */
  // On the account, because that is what decides the language now (ADR-066). A German
  // browser would not: this instance's account says English, and the account wins.
  await request.put('/api/v1/setup/locale', { headers, data: { locale: 'de-CH' } });
  const context = await browser.newContext({ ...test.info().project.use });
  try {
    const page = await context.newPage();
    await page.goto('/sign-in');
    await page.locator('#email').fill('chef@example.com');
    await page.locator('#password').fill('a-sufficiently-long-password');
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'de-CH');

    await page.goto('/settings/registry');
    const picker = page.locator('#registry-category');
    await expect(picker).toBeVisible();
    await expect(picker.locator('option', { hasText: 'Gemüse' }).first()).toBeAttached();
  } finally {
    await context.close();
    await request.put('/api/v1/setup/locale', { headers, data: { locale: 'en-GB' } });
  }
});

test('the registry can be narrowed to one part of the shelf', async ({ page }) => {
  await page.goto('/settings/registry');
  await page.locator('#registry-category').selectOption('vegetables-fresh-vegetables');

  await expect(page.getByText('carrot', { exact: true }).first()).toBeVisible();
  // The count is the whole answer, not the page: it is what says the narrowing happened
  // on the server rather than in the browser.
  await expect(page.locator('.registry__count')).not.toContainText('896');
});

test('an admin can file a food where the seed could not', async ({ page }) => {
  /* The half seeding cannot do. The published table places what it shipped; an import
     creates an entry for a line that resolved to nothing, and nothing places that — so the
     person correcting it is the only one who can (ADR-067). */
  await page.goto('/settings/registry/carrot');
  await expect(page.locator('#category')).toHaveValue('vegetables-fresh-vegetables');

  await page.locator('#category').selectOption('vegetables-dried-vegetables');
  // Awaited on the response rather than on the click: the click resolves the moment it is
  // dispatched, and reloading on top of an in-flight PUT cancels it.
  const saved = page.waitForResponse(
    (one) => one.url().endsWith('/registry/carrot') && one.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save corrections' }).click();
  expect((await saved).status()).toBe(200);

  await page.reload();
  await expect(page.locator('#category')).toHaveValue('vegetables-dried-vegetables');

  // Put it back, so this file leaves the shared registry as it found it.
  await page.locator('#category').selectOption('vegetables-fresh-vegetables');
  const restored = page.waitForResponse(
    (one) => one.url().endsWith('/registry/carrot') && one.request().method() === 'PUT',
  );
  await page.getByRole('button', { name: 'Save corrections' }).click();
  expect((await restored).status()).toBe(200);
});

test('the Academy reads as Ingredients > Vegetables > Carrot', async ({ page, request }) => {
  const written = await request.post('/api/v1/academy', {
    headers,
    data: {
      slug: 'about-carrot',
      kind: 'ingredient',
      about: 'carrot',
      name: 'carrot',
      spellings: [],
      summary: 'Sweet, and better raw than most people think.',
      explanation: 'Roots. They keep for weeks somewhere cold and dark.',
      caution: null,
      name_matches: false,
    },
  });
  expect([201, 409], await written.text()).toContain(written.status());
  // Read, so it leaves the "waiting to be read" list and joins the Academy proper. An
  // unreviewed page is readable but is not what anybody browsing the shelves sees
  // (ADR-060).
  await request.post('/api/v1/academy/about-carrot/approved', { headers });

  await page.goto('/academy');
  await page.getByRole('button', { name: 'Ingredients' }).click();

  // The shelf the registry puts the carrot on, above the letter it starts with.
  await expect(page.locator('.academy__shelf', { hasText: 'Fresh vegetables' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'carrot', exact: true })).toBeVisible();
});
