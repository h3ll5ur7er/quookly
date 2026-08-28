#!/usr/bin/env node
/**
 * Every template that uses a shared class imports the partial that defines it.
 *
 * Angular scopes component styles. A template that says `class="action"` in a component
 * whose stylesheet does not `@use` the partial defining `.action` gets **nothing** — a
 * browser-default grey button, no page padding, a caution rendered as bold text. It fails
 * silently, and it looks like a design decision rather than a mistake.
 *
 * It had happened in eight components before anybody noticed: the whole Academy, the whole
 * registry, the manual recipe form, the apply screen and sign-in. Eight times without
 * failing anything is the definition of a check worth writing (X1, X2 in
 * `doc/12-visual-review.md`).
 *
 * In Node rather than as a unit test, for the same reason `check-contrast.mjs` is: this is
 * a fact about files, and the browser test environment has no filesystem. `just frontend
 * check` runs it.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const app = join(here, '..', 'src', 'app');

/** Which partial defines which class. */
const DEFINED_BY = {
  page: ['page', 'action', 'notice'],
  form: ['field'],
  chips: ['chip'],
};

function stylesheets(directory) {
  const found = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) found.push(...stylesheets(path));
    else if (entry.endsWith('.component.scss')) found.push(path);
  }
  return found;
}

/**
 * Whether the stylesheet really imports the partial.
 *
 * Matched as an `@use` statement rather than as text anywhere in the file. Substring
 * matching passed a file whose *comment* mentioned the partial it had stopped importing —
 * found by removing an import and watching this check stay green, which is the only way
 * anybody finds out whether a check works.
 */
function imports(styles, partial) {
  return new RegExp(`^\\s*@use\\s+['"][^'"]*styles/${partial}['"]`, 'm').test(styles);
}

const missing = [];
let checked = 0;

for (const stylesheet of stylesheets(app)) {
  let markup;
  try {
    markup = readFileSync(stylesheet.replace(/\.scss$/, '.html'), 'utf8');
  } catch {
    // An inline template. Its classes live in the .ts and this does not read them — a gap
    // worth closing the day an inline template reaches for a shared class.
    continue;
  }
  checked += 1;
  const styles = readFileSync(stylesheet, 'utf8');

  for (const [partial, classes] of Object.entries(DEFINED_BY)) {
    const used = classes.filter((one) => new RegExp(`class="[^"]*\\b${one}\\b`).test(markup));
    if (used.length > 0 && !imports(styles, partial)) {
      missing.push(
        `${relative(join(here, '..'), stylesheet)}\n` +
          `    uses .${used.join(', .')} but does not @use '.../styles/${partial}'`,
      );
    }
  }
}

if (missing.length > 0) {
  console.error(`Shared styles: ${missing.length} component(s) use a class they never import.\n`);
  for (const one of missing) console.error(`  ${one}\n`);
  console.error('  Those classes silently do nothing. Add the @use line.\n');
  process.exit(1);
}

console.log(`Shared styles: ${checked} components import every shared class they use.`);
