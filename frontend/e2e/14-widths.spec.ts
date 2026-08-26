import { claim, signIn } from './support';
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * The same screens at the widths people actually use (NFR-11, ADR-015).
 *
 * The design language has named four breakpoints since Phase 0 and the application had
 * **one media query in it**, so every page was the phone's 44rem column centred in whatever
 * space there was. On a laptop more of the screen was empty than not.
 *
 * These are screenshots for human review — a suite that passes is not the same as a screen
 * that is good — plus the two things worth asserting mechanically: nothing overflows
 * sideways, and the navigation is where it belongs at each width.
 */

const WIDTHS = [
  { name: 'phone', width: 390, height: 844 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'laptop', width: 1440, height: 900 },
] as const;

test.describe.configure({ mode: 'serial' });

// Claimed here rather than inherited from whichever file ran first, so this one can
// be run on its own.
test.beforeAll(async ({ request }) => {
  await claim(request);
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

for (const { name, width, height } of WIDTHS) {
  test.describe(`on a ${name}`, () => {
    test.use({ viewport: { width, height } });

    test('the page never scrolls sideways', async ({ page }) => {
      for (const where of ['/', '/recipes', '/plans', '/shopping', '/pantry', '/settings']) {
        await page.goto(where);
        await expect(page.locator('main')).toBeVisible();
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${where} at ${width}px`).toBeLessThanOrEqual(0);
      }
    });

    test('the navigation is where a hand can reach it', async ({ page }) => {
      /* Bottom bar on a phone and a tablet held in two hands; a column beside the content
         once the screen is one nobody holds. Measured rather than asserted about a class:
         which side of the content it sits on is the whole of the difference. */
      const bar = page.locator('.shell__top');
      const box = await bar.boundingBox();
      expect(box).not.toBeNull();

      if (width >= 1024) {
        expect(box!.x, 'a sidebar starts at the left edge').toBeLessThan(10);
        expect(box!.height, 'a sidebar is full height').toBeGreaterThan(height / 2);
      } else {
        expect(box!.y, 'a bar sits at the bottom').toBeGreaterThan(height / 2);
        expect(box!.height, 'a bar is one row').toBeLessThan(120);
      }
    });

    test('has no accessibility violations', async ({ page }) => {
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });

    test('looks like this', async ({ page }) => {
      for (const [where, shot] of [
        ['/', 'home'],
        ['/recipes', 'recipes'],
        ['/shopping', 'shopping'],
        ['/settings', 'settings'],
      ] as const) {
        await page.goto(where);
        await expect(page.locator('main')).toBeVisible();
        await page.screenshot({
          path: `e2e/screenshots/${shot}-${name}.png`,
          fullPage: true,
          animations: 'disabled',
        });
      }
    });
  });
}
