#!/usr/bin/env node
/**
 * Contrast is a property of a token pair, so it is checked once per theme rather than
 * argued about per screen (NFR-15, ADR-023). A theme that fails this is a bug, not a
 * style choice.
 *
 * This runs in Node rather than as a unit test because the Angular builder treats a CSS
 * import as a stylesheet to bundle, not as text. `just frontend check` runs it.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const AA_TEXT = 4.5;
const AA_LARGE_OR_NON_TEXT = 3;

/** Foreground token, the surface it is meant to sit on, and the ratio it must clear. */
const PAIRS = [
  ['--on-surface', '--surface', AA_TEXT],
  ['--on-surface', '--surface-raised', AA_TEXT],
  ['--on-surface', '--surface-sunken', AA_TEXT],
  ['--on-surface-muted', '--surface', AA_TEXT],
  ['--on-surface-muted', '--surface-raised', AA_TEXT],
  // A disabled button: neutral rather than a faded accent, so it has its own pair.
  ['--on-surface-muted', '--surface-sunken', AA_TEXT],
  ['--on-surface-subtle', '--surface', AA_LARGE_OR_NON_TEXT],
  // WCAG 1.4.11 applies to the visible boundary of a control, not to decorative
  // dividers — which is why --border and --border-strong are separate tokens.
  ['--border-strong', '--surface', AA_LARGE_OR_NON_TEXT],
  ['--border-strong', '--surface-raised', AA_LARGE_OR_NON_TEXT],
  ['--on-primary', '--primary', AA_TEXT],
  ['--on-accent', '--accent', AA_TEXT],
  ['--on-success', '--success', AA_TEXT],
  ['--on-warning', '--warning', AA_TEXT],
  ['--on-danger', '--danger', AA_TEXT],
  ['--on-danger-surface', '--danger-surface', AA_TEXT],
  ['--on-info', '--info', AA_TEXT],
  // Status colours used as *text* rather than as fills. These tokens were defined as
  // backgrounds, with an --on- partner for what sits on them; a badge that puts one on
  // the page ground is a different pair, and one theme lightening a fill for its own
  // background use would silently make that text unreadable.
  ['--danger', '--surface', AA_TEXT],
  ['--danger', '--surface-raised', AA_TEXT],
  ['--warning', '--surface', AA_TEXT],
  ['--warning', '--surface-raised', AA_TEXT],
  ['--info', '--surface', AA_TEXT],
  ['--info', '--surface-raised', AA_TEXT],
  ['--success', '--surface-raised', AA_TEXT],
];

const THEMES = ['light', 'dark', 'playful', 'decorative'];

const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, '..', 'src', 'styles', 'themes.css'), 'utf8');

function blockFor(theme) {
  const selector = theme === 'light' ? ':root' : `\\[data-theme='${theme}'\\]`;
  const match = new RegExp(`${selector}\\s*\\{([^}]*)\\}`).exec(css);
  if (match === null) {
    throw new Error(`no token block found for theme "${theme}"`);
  }
  return match[1];
}

/** Tokens for a theme, with the light block as the base every other theme overrides. */
function tokensFor(theme) {
  const tokens = new Map();
  const blocks = theme === 'light' ? [blockFor('light')] : [blockFor('light'), blockFor(theme)];
  for (const block of blocks) {
    for (const [, name, value] of block.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      tokens.set(name, value.trim());
    }
  }
  return tokens;
}

function relativeLuminance(hex) {
  const full = hex.length === 4 ? `#${hex.slice(1).replace(/./g, (c) => c + c)}` : hex;
  const value = Number.parseInt(full.slice(1), 16);
  const linear = [(value >> 16) & 255, (value >> 8) & 255, value & 255]
    .map((channel) => channel / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(foreground, background) {
  const [lighter, darker] = [relativeLuminance(foreground), relativeLuminance(background)].sort(
    (a, b) => b - a,
  );
  return (lighter + 0.05) / (darker + 0.05);
}

const failures = [];
let checked = 0;

for (const theme of THEMES) {
  const tokens = tokensFor(theme);
  if (!blockFor(theme).includes('color-scheme')) {
    failures.push(`${theme}: no color-scheme declared, so form controls will not match`);
  }
  for (const [foreground, background, minimum] of PAIRS) {
    const fg = tokens.get(foreground);
    const bg = tokens.get(background);
    if (fg === undefined || bg === undefined) {
      failures.push(`${theme}: ${foreground} or ${background} is not defined`);
      continue;
    }
    if (!fg.startsWith('#') || !bg.startsWith('#')) {
      failures.push(`${theme}: ${foreground}/${background} must be hex so contrast is checkable`);
      continue;
    }
    checked += 1;
    const ratio = contrastRatio(fg, bg);
    if (ratio < minimum) {
      failures.push(
        `${theme}: ${foreground} (${fg}) on ${background} (${bg}) is ` +
          `${ratio.toFixed(2)}:1, needs ${minimum}:1`,
      );
    }
  }
}

if (failures.length > 0) {
  console.error(`Contrast check failed (${failures.length} of ${checked} pairs):\n`);
  for (const failure of failures) {
    console.error(`  ${failure}`);
  }
  process.exit(1);
}

console.log(`Contrast: ${checked} token pairs across ${THEMES.length} themes meet WCAG AA.`);
