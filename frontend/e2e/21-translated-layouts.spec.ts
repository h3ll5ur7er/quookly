import { claim } from './support';
import { expect, test } from '@playwright/test';

/**
 * The layouts, in the languages they were not designed in.
 *
 * German and French labels run two to three times longer than the English — *Reset*
 * becomes *Réinitialiser*, *Add* becomes *Hinzufügen* — and nobody had ever looked at this
 * application in either language. There was one non-English screenshot in the whole suite.
 *
 * Measured rather than photographed. A picture shows one moment to whoever looks at it; a
 * measurement fails the build the day somebody writes a longer German string, which is the
 * only way this stays true.
 */

// Not serial: a failure in one language should not hide the other two, which is the
// whole question this file exists to answer.

let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = { Authorization: `Bearer ${await claim(request)}` };
});

/** Where a cook actually spends time, plus the two screens with the densest tables. */
const SCREENS = ['/', '/recipes', '/recipes/1', '/pantry', '/shopping', '/academy', '/settings'];

for (const locale of ['en-GB', 'de-CH', 'fr-CH'] as const) {
  test(`nothing runs off the side of the screen in ${locale}`, async ({ browser }) => {
    // The spread first: the project carries a locale of its own.
    const context = await browser.newContext({ ...test.info().project.use, locale });
    try {
      const page = await context.newPage();
      await page.goto('/sign-in');
      await page.locator('#email').fill('chef@example.com');
      await page.locator('#password').fill('a-sufficiently-long-password');
      await page.locator('button[type="submit"]').click();
      await expect(page).toHaveURL(/\/$/);

      const spilling: string[] = [];
      for (const path of SCREENS) {
        await page.goto(path);
        await page.waitForLoadState('networkidle');

        /* The page itself, and then every element on it. A page that scrolls sideways is
           the symptom; the element sticking out is the cause, and reporting only the first
           is what makes the failure readable. */
        const overflow = await page.evaluate(() => {
          const room = document.documentElement.clientWidth;
          const out: string[] = [];
          for (const el of Array.from(document.querySelectorAll('body *'))) {
            const box = el.getBoundingClientRect();
            if (box.width === 0 || box.height === 0) continue;
            if (box.right > room + 1) {
              const what =
                el.className && typeof el.className === 'string'
                  ? `.${el.className.trim().split(/\s+/).join('.')}`
                  : el.tagName.toLowerCase();
              out.push(`${what} ends at ${Math.round(box.right)} of ${room}`);
            }
          }
          return out.slice(0, 4);
        });
        for (const one of overflow) spilling.push(`${path}  ${one}`);
      }

      expect(
        spilling,
        `content runs off the side of the screen:\n  ${spilling.join('\n  ')}`,
      ).toEqual([]);
    } finally {
      await context.close();
    }
  });
}
