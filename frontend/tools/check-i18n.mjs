#!/usr/bin/env node
/**
 * Every translatable message must be answered by every catalogue (FR-10, ADR-025).
 *
 * Sources are scanned directly rather than the extracted messages.xlf, so a string added
 * without re-running extraction is still caught. An untranslated message is not a crash —
 * $localize falls back to the English source — which is exactly why it needs a check: it
 * fails silently, in a language the author does not read.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const SOURCE_LOCALE = 'en-GB';
const TARGET_LOCALES = ['de-CH', 'fr-CH'];

function sourceFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return entry.name === 'api' ? [] : sourceFiles(path);
    }
    return /\.(ts|html)$/.test(entry.name) && !entry.name.endsWith('.spec.ts') ? [path] : [];
  });
}

/** Message ids used in templates (`i18n="@@id"`, `i18n-attr="@@id"`) and in TypeScript. */
function usedMessageIds() {
  const found = new Map();
  for (const file of sourceFiles(join(root, 'src', 'app'))) {
    const text = readFileSync(file, 'utf8');
    for (const pattern of [/i18n(?:-[\w-]+)?="@@([\w]+)"/g, /\$localize`:@@([\w]+):/g]) {
      for (const [, id] of text.matchAll(pattern)) {
        found.set(id, file.slice(root.length + 1));
      }
    }
  }
  return found;
}

function catalogue(locale) {
  const path = join(root, 'public', 'i18n', `${locale}.json`);
  try {
    return JSON.parse(readFileSync(path, 'utf8')).translations ?? {};
  } catch {
    throw new Error(`catalogue for ${locale} is missing or unreadable: ${path}`);
  }
}

const used = usedMessageIds();
const failures = [];

if (used.size === 0) {
  failures.push('no translatable messages found — is the scan still matching the markup?');
}

// The source catalogue stays empty: $localize uses the source text for English.
const source = catalogue(SOURCE_LOCALE);
if (Object.keys(source).length > 0) {
  failures.push(`${SOURCE_LOCALE} is the source language; its catalogue should stay empty`);
}

for (const locale of TARGET_LOCALES) {
  const translations = catalogue(locale);
  for (const [id, file] of used) {
    if (typeof translations[id] !== 'string' || translations[id].trim() === '') {
      failures.push(`${locale}: "${id}" is untranslated (used in ${file})`);
    }
  }
  for (const id of Object.keys(translations)) {
    if (!used.has(id)) {
      failures.push(`${locale}: "${id}" is translated but no longer used`);
    }
  }
}

// Swiss German writes ss, never ß.
const german = catalogue('de-CH');
for (const [id, text] of Object.entries(german)) {
  if (text.includes('ß')) {
    failures.push(`de-CH: "${id}" contains ß, which Swiss German does not use`);
  }
}

if (failures.length > 0) {
  console.error(`Translation check failed (${failures.length}):\n`);
  for (const failure of failures) {
    console.error(`  ${failure}`);
  }
  process.exit(1);
}

console.log(`Translations: ${used.size} messages, complete in ${TARGET_LOCALES.join(' and ')}.`);
