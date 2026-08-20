import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

/**
 * Appearance, in a real browser: the themes as rendered rather than as token values, the
 * locale as read rather than as a catalogue, and the manifest a phone would install from.
 *
 * Runs after the journey, against a claimed instance.
 */

const THEMES = ['light', 'dark', 'playful', 'decorative'] as const;

async function chooseTheme(page: import('@playwright/test').Page, theme: string): Promise<void> {
  await page.getByLabel('Colour theme').selectOption(theme);
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

test.describe('themes', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();
  });

  test('follows the device until a choice is made', async ({ page }) => {
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });

  test('respects a device that asks for dark', async ({ browser }) => {
    const context = await browser.newContext({ colorScheme: 'dark' });
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await context.close();
  });

  for (const theme of THEMES) {
    test(`${theme} renders without accessibility violations`, async ({ page }) => {
      await chooseTheme(page, theme);
      const results = await new AxeBuilder({ page }).analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test('a chosen theme survives a reload', async ({ page }) => {
    await chooseTheme(page, 'decorative');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'decorative');
  });

  test('the browser chrome follows the theme', async ({ page }) => {
    await chooseTheme(page, 'dark');
    const chrome = await page.locator('meta[name="theme-color"]').getAttribute('content');
    const surface = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--surface').trim(),
    );
    expect(chrome).toBe(surface);
  });

  test('each theme actually looks different', async ({ page }) => {
    const surfaces = new Set<string>();
    for (const theme of THEMES) {
      await chooseTheme(page, theme);
      surfaces.add(
        await page.evaluate(() =>
          getComputedStyle(document.body).getPropertyValue('background-color'),
        ),
      );
    }
    expect(surfaces.size, 'themes should not share a surface colour').toBe(THEMES.length);
  });
});

test.describe('language', () => {
  test('follows the browser preference', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'de-CH' });
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Bei Quookly anmelden' })).toBeVisible();
    await context.close();
  });

  test('serves Swiss French to a French browser', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'fr-FR' });
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Se connecter à Quookly' })).toBeVisible();
    await context.close();
  });

  test('a chosen language survives a reload', async ({ page }) => {
    await page.goto('/sign-in');
    await page.getByLabel('Language').selectOption('de-CH');
    await expect(page.getByRole('heading', { name: 'Bei Quookly anmelden' })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Bei Quookly anmelden' })).toBeVisible();
  });

  test('translates the whole screen, not only the heading', async ({ browser }) => {
    const context = await browser.newContext({ locale: 'de-CH' });
    const page = await context.newPage();
    await page.goto('/sign-in');
    await expect(page.getByText('Passwort')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Anmelden' })).toBeVisible();
    // Nothing should be left in English on a translated screen.
    await expect(page.getByText('Sign in', { exact: true })).toHaveCount(0);
    await context.close();
  });
});

test.describe('installable', () => {
  test('the page links a manifest a phone can install from', async ({ page, request }) => {
    await page.goto('/sign-in');
    const href = await page.locator('link[rel="manifest"]').getAttribute('href');
    expect(href).toBeTruthy();

    const manifest = await (await request.get(`/${href}`)).json();
    expect(manifest.name).toBe('Quookly');
    expect(manifest.display).toBe('standalone');
    expect(manifest.icons.length).toBeGreaterThanOrEqual(2);
    expect(
      manifest.icons.some((icon: { purpose: string }) => icon.purpose === 'maskable'),
      'a maskable icon keeps the mark inside the safe zone platforms crop to',
    ).toBe(true);
  });

  test('every icon the manifest promises is actually served', async ({ request }) => {
    const manifest = await (await request.get('/manifest.webmanifest')).json();
    for (const icon of manifest.icons as { src: string }[]) {
      const response = await request.get(icon.src);
      expect(response.status(), `${icon.src} is missing`).toBe(200);
      expect(response.headers()['content-type']).toContain('image/png');
    }
  });

  test('ships a service worker so the shell works offline', async ({ request }) => {
    expect((await request.get('/ngsw-worker.js')).status()).toBe(200);
    const config = await (await request.get('/ngsw.json')).json();
    expect(config.assetGroups.length).toBeGreaterThan(0);
  });

  test('asks the browser for nothing from anywhere else', async ({ page }) => {
    const external: string[] = [];
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.hostname !== '127.0.0.1' && url.protocol !== 'data:') {
        external.push(request.url());
      }
    });
    await page.goto('/sign-in');
    await expect(page.getByRole('heading', { name: 'Sign in to Quookly' })).toBeVisible();
    expect(external, 'an instance with no outbound internet must render identically').toEqual([]);
  });
});
