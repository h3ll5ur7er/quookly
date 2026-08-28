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
const partials = join(here, '..', 'src', 'styles');

/**
 * Which partial defines which class, read off the partials themselves.
 *
 * It used to be a hand-written list of three, and a hand-written list is a list that goes
 * stale: `.visually-hidden` is defined in `_a11y.scss` and was never on it, so three
 * components printed their screen-reader-only labels across the page and this check said
 * they were fine. Deriving it means a class added to a partial is covered the day it is
 * written.
 */
function definedByPartial() {
  const map = new Map();
  for (const entry of readdirSync(partials)) {
    if (!entry.startsWith('_') || !entry.endsWith('.scss')) continue;
    const name = entry.slice(1, -5);
    const text = readFileSync(join(partials, entry), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
    for (const [, one] of text.matchAll(/(?:^|[\s,>+~(])\.(-?[_a-zA-Z][\w-]*)/g)) {
      // First definition wins. A class two partials both mention belongs to whichever
      // declares it first, and naming it twice is its own problem.
      if (!map.has(one)) map.set(one, name);
    }
  }
  return map;
}

const DEFINED_BY = definedByPartial();

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

  // Every class the markup puts on an element, static or bound.
  const used = new Set();
  for (const [, value] of markup.matchAll(/\sclass="([^"]*)"/g)) {
    for (const token of value.replace(/\{\{[^}]*\}\}/g, ' ').split(/\s+/)) {
      if (token) used.add(token);
    }
  }
  for (const [, name] of markup.matchAll(/\[class\.([\w-]+)\]/g)) used.add(name);

  const wanted = new Map();
  for (const one of used) {
    const partial = DEFINED_BY.get(one);
    if (partial !== undefined && !imports(styles, partial)) {
      wanted.set(partial, [...(wanted.get(partial) ?? []), one]);
    }
  }
  for (const [partial, classes] of wanted) {
    missing.push(
      `${relative(join(here, '..'), stylesheet)}\n` +
        `    uses .${classes.join(', .')} but does not @use '.../styles/${partial}'`,
    );
  }
}

if (missing.length > 0) {
  console.error(`Shared styles: ${missing.length} component(s) use a class they never import.\n`);
  for (const one of missing) console.error(`  ${one}\n`);
  console.error('  Those classes silently do nothing. Add the @use line.\n');
  process.exit(1);
}

console.log(
  `Shared styles: ${checked} components import every shared class they use ` +
    `(${DEFINED_BY.size} classes across the partials).`,
);
