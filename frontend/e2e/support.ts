import { APIRequestContext, Page, expect } from '@playwright/test';

/**
 * What every end-to-end file needs before it can say anything.
 *
 * These exist because the suite grew a shape nobody chose. Files depended on a *sibling*
 * having claimed the instance, so none of them could run alone and a run that started
 * anywhere else failed at sign-in. And several waited for nothing: a form was filled and
 * submitted in the same breath as the lookup it depends on, which passes while the server
 * is quick and fails the week it is not.
 *
 * The suite runs in one worker, in file order, against one server and one database — that
 * was always true and is not the problem. What was missing is that each file should
 * *establish* what it needs rather than inherit it.
 */

/** The account the suite shares. The first to run claims the instance with it. */
export const COOK = {
  email: 'chef@example.com',
  display_name: 'Emanuel',
  password: 'a-sufficiently-long-password',
};

/**
 * Make sure this instance is claimed and this account exists, and hand back its token.
 *
 * Idempotent, and safe to call from every file: the bootstrap is a one-way door, so
 * whichever file runs first opens it and the rest sign in. That is what lets any file be
 * run on its own — `npx playwright test e2e/09-pantry.spec.ts` is a thing somebody
 * debugging should be able to do.
 */
export async function claim(
  request: APIRequestContext,
  cook: { email: string; display_name: string; password: string } = COOK,
): Promise<string> {
  const claimed = await request.post('/api/v1/accounts/bootstrap', { data: cook });
  if (claimed.ok()) {
    return (await claimed.json()).token as string;
  }
  const signedIn = await request.post('/api/v1/accounts/sign-in', {
    data: { email: cook.email, password: cook.password },
  });
  expect(signedIn.ok(), `neither bootstrap nor sign-in worked: ${await signedIn.text()}`).toBe(
    true,
  );
  return (await signedIn.json()).token as string;
}

/**
 * An account that is not the administrator's, let in the way a real one is.
 *
 * Applies, then approves with the admin's token — the door ADR-049 built, used rather
 * than bypassed.
 */
export async function letIn(
  request: APIRequestContext,
  adminToken: string,
  cook: { email: string; display_name: string; password: string },
): Promise<string> {
  const applied = await request.post('/api/v1/accounts/applications', { data: cook });
  if (applied.ok()) {
    const { id } = await applied.json();
    await request.post(`/api/v1/accounts/applications/${id}/approved`, {
      headers: { Authorization: `Bearer ${adminToken}` },
    });
  }
  const signedIn = await request.post('/api/v1/accounts/sign-in', {
    data: { email: cook.email, password: cook.password },
  });
  expect(signedIn.ok(), await signedIn.text()).toBe(true);
  return (await signedIn.json()).token as string;
}

/** Sign in through the screens, and wait until the app says it worked. */
export async function signIn(
  page: Page,
  cook: { email: string; password: string } = COOK,
): Promise<void> {
  await page.goto('/sign-in');
  await page.getByLabel('Email').fill(cook.email);
  await page.getByLabel('Password').fill(cook.password);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/$/);
}

/**
 * Type an ingredient name and wait for the registry to answer before going on.
 *
 * The form will not accept a name it has not resolved — a constraint that matched nothing
 * would silently never fire, which reads on screen as protection. So a test that types and
 * submits in the same breath is racing the lookup, and passes only while the server is
 * quick. This waits for the answer instead.
 */
export async function typeIngredient(page: Page, label: string, name: string): Promise<void> {
  const answered = page.waitForResponse(
    (response) => response.url().includes('/api/v1/ingredients') && response.ok(),
  );
  await page.getByLabel(label, { exact: true }).fill(name);
  await answered;
}

/**
 * Change a recipe's yield and wait for the recipe that comes back.
 *
 * Each tap re-asks the server, because the arithmetic lives there. Tapping twelve times
 * without waiting is twelve requests racing, and the screen shows whichever lands last.
 */
export async function changeYield(page: Page, taps: number): Promise<void> {
  const button = page.getByRole('button', { name: taps > 0 ? 'More' : 'Less' });
  for (let i = 0; i < Math.abs(taps); i++) {
    const answered = page.waitForResponse(
      (response) => response.url().includes('/api/v1/recipes/') && response.ok(),
    );
    await button.click();
    await answered;
  }
}

/** Open a recipe from the list, and wait until its page is really there. */
export async function openRecipe(page: Page, title: RegExp | string): Promise<void> {
  await page.goto('/recipes');
  await page.getByRole('link', { name: title }).click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}

/**
 * Put the kitchen back to empty for one cook.
 *
 * The suite runs in one worker against one database, so what an earlier file leaves behind
 * is what a later one starts from. That was worked around by ordering — one file runs last
 * *because* it stocks a pantry, and another empties the household in its own setup — which
 * works until somebody adds a file in the middle.
 *
 * Sessions first, then plans, then the shelf, then the people: a plan holds stock and a
 * session holds a plan, so the other order leaves things claimed by something that is gone.
 *
 * Recipes are left alone. They are archived rather than deleted (ADR-059), the seeded ones
 * belong to the instance, and every file that imports one imports the same document twice
 * without harm.
 */
export async function emptyKitchen(
  request: APIRequestContext,
  headers: Record<string, string>,
): Promise<void> {
  const open = await request.get('/api/v1/cooking/sessions', { headers });
  for (const session of (await open.json()) as { id: number }[]) {
    await request.post(`/api/v1/cooking/sessions/${session.id}/abandoned`, { headers });
  }

  const plans = await request.get('/api/v1/plans', { headers });
  for (const plan of (await plans.json()) as { id: number }[]) {
    await request.delete(`/api/v1/plans/${plan.id}`, { headers });
  }

  // The shelf lists an entry per ingredient, each holding its lots — stock is kept as lots
  // rather than as a total (ADR-034), and it is the lots that are removed.
  const shelf = await request.get('/api/v1/pantry', { headers });
  for (const entry of (await shelf.json()) as { lots: { id: number }[] }[]) {
    for (const lot of entry.lots) {
      await request.delete(`/api/v1/pantry/lots/${lot.id}`, { headers });
    }
  }

  const household = await request.get('/api/v1/eaters', { headers });
  for (const person of (await household.json()) as { id: number }[]) {
    await request.delete(`/api/v1/eaters/${person.id}`, { headers });
  }
}
