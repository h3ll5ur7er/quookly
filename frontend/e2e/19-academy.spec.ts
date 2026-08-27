import { claim, signIn } from './support';
import { expect, test } from '@playwright/test';

/**
 * Looking a word up from a recipe (UC-2.5) and from the hob (UC-9.5).
 *
 * Nothing is tagged and nothing is stored linking a step to a page: the terms are read out
 * of the step's own words when it is displayed (ADR-040, ADR-055). This recipe is written
 * here, in this file, and gains its links because the Academy happens to explain the words
 * it uses — which is the whole claim.
 */

test.describe.configure({ mode: 'serial' });

// Claimed here rather than inherited from whichever file ran first, so this one can
// be run on its own.
test.beforeAll(async ({ request }) => {
  await claim(request);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test('the Academy can be browsed and a page read', async ({ page }) => {
  await page.goto('/academy');
  await expect(page.getByRole('heading', { name: 'Academy' })).toBeVisible();

  await page.getByRole('link', { name: 'deep-fry', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'deep-fry' })).toBeVisible();
  await expect(page.getByText('Cook submerged in hot fat.')).toBeVisible();
  // The one place a definition is not enough on its own.
  await expect(page.getByText(/never move a burning pan/)).toBeVisible();
});

test('a recipe marks the words it uses, and they lead to the Academy', async ({ page }) => {
  await page.goto('/recipes/new');
  await page.getByLabel('Title').fill('Marked Loaf');
  await page.getByLabel('Makes').fill('1');
  await page.getByRole('button', { name: 'Choose an ingredient' }).click();
  await page.getByPlaceholder('An ingredient name').fill('plain flour');
  await page.getByRole('button', { name: 'plain flour', exact: true }).click();
  await page.getByLabel('How much').fill('500');
  await page.getByLabel('Step').fill('Gently fold in the whites, then blanch the beans.');
  await page.getByRole('button', { name: 'Save recipe' }).click();

  await expect(page.getByRole('heading', { name: 'Marked Loaf' })).toBeVisible();

  // The step reads as written; two of its words are now links.
  await expect(page.getByText('Gently fold in the whites, then blanch the beans.')).toBeVisible();
  await page.getByRole('link', { name: 'Gently fold' }).click();

  await expect(page).toHaveURL(/\/academy\/fold$/);
  await expect(page.getByRole('heading', { name: 'fold' })).toBeVisible();
  await expect(page.getByText('Combine without knocking out the air.')).toBeVisible();
});

test('an administrator can correct a page and illustrate it', async ({ page }) => {
  await page.goto('/academy/julienne');
  await expect(page.getByRole('heading', { name: 'julienne' })).toBeVisible();

  // --- correcting one language -----------------------------------------------------
  await page.getByRole('button', { name: 'Correct this page' }).click();
  await page.getByLabel('In one line').fill('Thin matchsticks, about 2 mm square.');
  await page.getByRole('button', { name: 'Save the page' }).click();
  await expect(page.getByText('Thin matchsticks, about 2 mm square.')).toBeVisible();

  // --- and putting a picture on it -------------------------------------------------
  await page.getByRole('button', { name: 'Add a picture' }).click();
  // A one-pixel PNG is enough: this is about the round trip, and the re-encoding is
  // covered where it can be inspected rather than through a browser.
  await page.getByLabel('The picture').setInputFiles({
    name: 'julienne.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
      'base64',
    ),
  });
  await page.getByLabel('What it shows').fill('Carrot cut into fine matchsticks.');
  await page.getByRole('button', { name: 'Add it' }).click();

  // The alt text is the picture, for a reader who cannot see it.
  await expect(page.getByAltText('Carrot cut into fine matchsticks.')).toBeVisible();
});

test('a cook writes a page, and it is not in recipes until somebody reads it', async ({ page }) => {
  /* The whole of ADR-060, end to end. The page is readable the moment it is written and
     does not attach itself to anybody's recipe until an administrator has read it —
     marking works when the reader has come to the page, and does nothing when the page
     arrives underlined inside a recipe three screens away. */
  await page.goto('/academy');
  await page.getByRole('link', { name: 'Write a page' }).click();
  await expect(page.getByRole('heading', { name: 'Write a page' })).toBeVisible();

  await page.getByLabel('What it is called').fill('spatchcock');
  // The short name fills itself in from the name, so nobody has to invent a URL fragment.
  await expect(page.locator('#slug')).toHaveValue('spatchcock');
  await page.getByLabel('In one line').fill('Flatten a bird so it cooks evenly.');
  await page
    .getByLabel('The explanation')
    .fill('Cut out the backbone and press down on the breastbone.');
  await page.getByLabel('The ways a step writes it').fill('spatchcocked\nbutterflied');
  await page.getByRole('button', { name: 'Write the page' }).click();

  // It lands on the page it just wrote, which says plainly where it stands.
  await expect(page.getByRole('heading', { name: 'spatchcock' })).toBeVisible();
  await expect(page.getByText('nobody has read it yet')).toBeVisible();

  // Listed under what is waiting, so its author can see it is waiting rather than lost.
  await page.goto('/academy');
  await expect(page.getByRole('heading', { name: 'Waiting to be read' })).toBeVisible();

  // And not yet a word in anybody's recipe.
  await page.goto('/academy/terms/spatchcocked');
  await expect(page.getByText('Nobody has explained that yet')).toBeVisible();

  // --- read, and now it is ----------------------------------------------------------
  await page.goto('/academy/spatchcock');
  await page.getByRole('button', { name: 'Approve' }).click();
  await expect(page.getByText('nobody has read it yet')).toHaveCount(0);

  await page.goto('/academy/terms/spatchcocked');
  await expect(page.getByRole('heading', { name: 'spatchcock' })).toBeVisible();
});

test('an administrator can put a page away', async ({ page }) => {
  await page.goto('/academy/spatchcock');
  await page.getByRole('button', { name: 'Put this page away' }).click();
  await page.getByRole('button', { name: 'Yes, put it away' }).click();
  await expect(page).toHaveURL(/\/academy$/);

  // Gone from the Academy, and gone from the words a step is matched against.
  await expect(page.getByRole('link', { name: 'spatchcock', exact: true })).toHaveCount(0);
  await page.goto('/academy/terms/spatchcocked');
  await expect(page.getByText('Nobody has explained that yet')).toBeVisible();
});

test('a page about a food shows what the kitchen knows, and never invents it', async ({ page }) => {
  /* ADR-061 end to end. The facts are the registry's, read rather than copied — so a page
     about a food nobody has examined says "nobody has looked", and says something
     different the moment somebody has, without the page being touched.

     Carrot juice because it is one of the seven hundred shipped entries that carry no
     allergen classification: the published table this registry was built from could not
     answer, and unexamined is the honest state (ADR-051). */
  await page.goto('/academy/new');
  await page.getByLabel('What it is called').fill('carrot juice');
  await page.locator('#kind').selectOption('ingredient');

  await page.getByLabel('Which food').fill('carrot juice');
  await page.getByRole('button', { name: 'carrot juice', exact: true }).click();

  await page.getByLabel('In one line').fill('Sweeter than the carrot it came from.');
  await page.getByLabel('The explanation').fill('Pressed, not cooked, so the sugars stay bright.');
  await page.getByRole('button', { name: 'Write the page' }).click();

  await expect(page.getByRole('heading', { name: 'What the kitchen knows' })).toBeVisible();
  // Never an empty list on a food nobody has examined: a reader would take that for
  // "contains none", which is the one thing ADR-006 exists to prevent.
  await expect(page.getByText('Nobody has classified this yet')).toBeVisible();

  // --- the registry leads back to the prose -----------------------------------------
  await page.getByRole('link', { name: 'carrot juice in the registry' }).click();
  await expect(page.getByRole('heading', { name: 'Written about this' })).toBeVisible();
  await expect(page.getByText('not read yet')).toBeVisible();

  // --- classify it here, and the page follows without being edited ------------------
  await page.locator('input[type="checkbox"][value="celery"]').check();
  await page.getByRole('button', { name: 'Record what is in it' }).click();
  await expect(page.getByText('Celery')).toBeVisible();

  await page.getByRole('link', { name: 'carrot juice', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'What the kitchen knows' })).toBeVisible();
  // Nobody edited the page. There is no copy on it, so there was nothing to update —
  // which is the whole of the decision.
  await expect(page.getByText('Celery')).toBeVisible();
  await expect(page.getByText('Nobody has classified this yet')).toHaveCount(0);
});

test('a word nobody has explained offers to ask, and says so when there is nothing to ask', async ({
  page,
}) => {
  /* This harness runs without a model on purpose, which makes this the spec for the
     honest failure — the same thing 13-invent does for writing a recipe. That the offer
     is reachable at all is the other half: a word nobody has explained is a word no
     recipe underlines, so the lookup is the only way to that screen (ADR-062). */
  await page.goto('/academy');
  await page.getByLabel('Look a word up').fill('spatchcock');
  await page.getByRole('button', { name: 'Look it up' }).click();

  await expect(page.getByRole('heading', { name: 'Which did you mean?' })).toBeVisible();
  await expect(page.getByText('Nobody has explained that yet.')).toBeVisible();

  // Said before it is pressed, not after: this is the one thing here that can be wrong.
  await expect(page.getByText('written by a model')).toBeVisible();

  await page.getByRole('button', { name: 'Ask for an explanation' }).click();
  // An operator reading this knows what to go and configure. Not "that did not work".
  await expect(page.getByText('no model to ask')).toBeVisible();
});

test('a visitor with no account can read the Academy, and nothing else', async ({ browser }) => {
  /* ADR-063, from the outside. A context of its own rather than the shared page: the
     signed-in session is in storage, and this is a test about not having one. */
  const context = await browser.newContext();
  try {
    const visitor = await context.newPage();
    await visitor.goto('/');

    // The only way a visitor finds it. Without the link the public Academy is reachable
    // by typing a URL, which is not reachable.
    await visitor.getByRole('link', { name: 'Read the Academy' }).click();
    await expect(visitor.getByRole('heading', { name: 'Academy' })).toBeVisible();

    await visitor.getByRole('link', { name: 'blanch', exact: true }).click();
    await expect(visitor.getByRole('heading', { name: 'blanch' })).toBeVisible();
    await expect(visitor.getByText('Boil briefly')).toBeVisible();

    // Nothing that leads where they cannot go.
    await expect(visitor.getByRole('link', { name: 'Write a page' })).toHaveCount(0);
    await expect(visitor.getByRole('button', { name: 'Correct this page' })).toHaveCount(0);

    // And a word nobody has explained is a dead end rather than an offer to spend the
    // operator's money.
    await visitor.goto('/academy/terms/spatchcock');
    await expect(visitor.getByText('Nobody has explained that yet')).toBeVisible();
    await expect(visitor.getByRole('button', { name: 'Ask for an explanation' })).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('a page nobody here has read is not published', async ({ page, browser }) => {
  /* The load-bearing half of ADR-063. Anyone let through the door could otherwise publish
     to the open internet under this instance's name. */
  await page.goto('/academy/new');
  await page.getByLabel('What it is called').fill('spatchcock');
  await page.getByLabel('In one line').fill('Flatten a bird so it cooks evenly.');
  await page.getByLabel('The explanation').fill('Cut out the backbone and press down.');
  await page.getByRole('button', { name: 'Write the page' }).click();
  await expect(page.getByText('nobody has read it yet')).toBeVisible();

  const context = await browser.newContext();
  try {
    const visitor = await context.newPage();
    await visitor.goto('/academy/spatchcock');
    await expect(visitor.getByText('Nobody has explained that yet')).toBeVisible();

    await visitor.goto('/academy');
    await expect(visitor.getByRole('link', { name: 'spatchcock', exact: true })).toHaveCount(0);
  } finally {
    await context.close();
  }
});
