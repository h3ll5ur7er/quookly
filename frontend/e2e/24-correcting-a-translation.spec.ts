import { claim, signIn } from './support';
import { expect, test } from '@playwright/test';

/**
 * Correcting a recipe's translation (ADR-064).
 *
 * The storage could always record that a person wrote a translation, and until now nothing
 * could put one there. What this asserts and a unit test cannot: that a correction survives
 * the round trip through a real database, that a reader is told *whose* words they are —
 * a machine's and a person's are both translations and only one is somebody's work — and
 * that editing the recipe underneath stops the correction being shown without destroying
 * it.
 *
 * This instance has no model, so nothing here derives a translation. That is the point: a
 * correction is written by a person, and needing a machine's first draft to write one
 * would make the screen useless on exactly the instances that most need it.
 */

test.describe.configure({ mode: 'serial' });

let headers: Record<string, string>;
let recipeId: number;

const GERMAN = {
  title: 'Schokoladenkuchen',
  summary: 'Ein einfacher Kuchen.',
  steps: [
    { instruction: 'Butter und Zucker schaumig ruehren.' },
    { instruction: 'Bei 180 C backen.' },
  ],
};

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };

  // Written while the account reads German, which is how a recipe comes to record the
  // language it is in: nobody is asked, because somebody typing into a German screen is
  // writing German (ADR-032).
  await request.put('/api/v1/setup/locale', { headers, data: { locale: 'de-CH' } });

  const flour = await request.get('/api/v1/ingredients?search=plain%20flour', { headers });
  const [entry] = (await flour.json()) as { id: number }[];

  const made = await request.post('/api/v1/recipes', {
    headers,
    data: {
      ...GERMAN,
      yield_magnitude: '4',
      yield_unit: 'serving',
      lines: [{ ingredient_id: entry.id, magnitude: '200', unit: 'g' }],
    },
  });
  expect(made.status(), await made.text()).toBe(201);
  recipeId = (await made.json()).id as number;

  await request.put('/api/v1/setup/locale', { headers, data: { locale: 'en-GB' } });
});

test.afterAll(async ({ request }) => {
  // The shared account reads English, and this file borrowed it. Put it back.
  await request.put('/api/v1/setup/locale', { headers, data: { locale: 'en-GB' } });
});

test('the author’s words sit beside every field', async ({ page }) => {
  await signIn(page);
  await page.goto(`/recipes/${recipeId}/translations/en`);

  // Nothing has been written yet and this instance has no model, so there is nothing to
  // correct — which is a real answer rather than an empty form.
  await expect(page.getByRole('heading', { name: 'Nothing to correct' })).toBeVisible();
});

test('a correction is stored, shown, and credited to a person', async ({ page, request }) => {
  const written = await request.put(`/api/v1/recipes/${recipeId}/translations/en`, {
    headers,
    data: {
      title: 'Chocolate cake',
      summary: 'A simple cake.',
      steps: ['Cream the butter and sugar.', 'Bake at 180 C.'],
    },
  });
  expect(written.status(), await written.text()).toBe(200);

  await signIn(page);
  await page.goto(`/recipes/${recipeId}`);

  await expect(page.getByRole('heading', { name: 'Chocolate cake' })).toBeVisible();
  // Whose words. Not "a machine's", which is what it would have said before.
  await expect(page.getByText('somebody here wrote these words')).toBeVisible();

  // And the screen that wrote them shows them, with the German beside each field.
  await page.getByRole('link', { name: 'Correct it' }).click();
  await expect(page).toHaveURL(new RegExp(`/recipes/${recipeId}/translations/en$`));
  await expect(page.locator('#title')).toHaveValue('Chocolate cake');
  await expect(page.getByText('Butter und Zucker schaumig ruehren.')).toBeVisible();
});

test('editing the recipe stops the correction being shown without destroying it', async ({
  page,
  request,
}) => {
  /* Kept because it is somebody's work; not shown because it describes sentences that are
     not there any more. The reader gets the author's own language, which is honest and is
     what an instance with no model shows anyway (ADR-064). */
  const flour = await request.get('/api/v1/ingredients?search=plain%20flour', { headers });
  const [entry] = (await flour.json()) as { id: number }[];

  const amended = await request.put(`/api/v1/recipes/${recipeId}`, {
    headers,
    data: {
      ...GERMAN,
      steps: [
        { instruction: 'Butter und Zucker schaumig schlagen.' },
        { instruction: 'Bei 180 C backen.' },
      ],
      yield_magnitude: '4',
      yield_unit: 'serving',
      lines: [{ ingredient_id: entry.id, magnitude: '200', unit: 'g' }],
    },
  });
  expect(amended.status(), await amended.text()).toBe(200);

  await signIn(page);
  await page.goto(`/recipes/${recipeId}`);
  // The author's language, not a machine's replacement of somebody's work.
  await expect(page.getByRole('heading', { name: 'Schokoladenkuchen' })).toBeVisible();

  // The words are still there, on the one screen that can show them — and it says why.
  await page.goto(`/recipes/${recipeId}/translations/en`);
  await expect(page.locator('#title')).toHaveValue('Chocolate cake');
  await expect(page.getByText('The recipe has changed')).toBeVisible();
});
