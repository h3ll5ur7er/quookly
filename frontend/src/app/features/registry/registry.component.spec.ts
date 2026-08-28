import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { RegistryComponent } from './registry.component';

/** Somebody chose to add this one, and somebody checked what is in it. */
const BUTTER = {
  id: 1,
  slug: 'unsalted-butter',
  name: 'unsalted butter',
  kind: 'solid',
  density: '0.9110',
  piece_grams: null,
  origin: 'seed',
  allergens: ['milk'],
  classified: true,
  approved: true,
};

/** Checked, and there is nothing in it. Different from BUTTERMILK below. */
const WATER = {
  id: 2,
  slug: 'water',
  name: 'water',
  kind: 'liquid',
  density: '1.0000',
  piece_grams: null,
  origin: 'seed',
  allergens: [],
  classified: true,
  approved: true,
};

/** What an import invented: a guessed kind, no density, and nobody has looked. */
const CREME = {
  id: 3,
  slug: 'creme-fraiche',
  name: 'crème fraîche',
  kind: 'solid',
  density: null,
  piece_grams: null,
  origin: 'user',
  allergens: [],
  classified: false,
  approved: false,
};

function page(entries: unknown[], total = entries.length) {
  return { entries, total };
}

describe('RegistryComponent', () => {
  let fixture: ComponentFixture<RegistryComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function asked() {
    return backend.expectOne((request) => request.url === '/api/v1/registry');
  }

  /** The food tree, which the screen asks for alongside the list. */
  function tree(nodes: object[] = []) {
    backend.expectOne('/api/v1/registry/categories').flush(nodes);
  }

  /** Driven through the screen rather than the class: the buttons are part of the answer. */
  function click(label: string): void {
    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    const wanted = buttons.find((button) => button.textContent?.trim() === label);
    if (!wanted) {
      throw new Error(`No button reading "${label}"`);
    }
    wanted.click();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RegistryComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(RegistryComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    // The screen asks for the food tree alongside the list. Answered with nothing here so
    // that every test which is not about the tree sees the screen it always was; the ones
    // that are about it answer again with `tree(...)` (ADR-067).
    tree();
  });

  afterEach(() => backend.verify());

  it('asks for the registry on arrival', () => {
    asked().flush(page([]));
  });

  it('lists what came back', async () => {
    asked().flush(page([BUTTER, WATER]));
    await fixture.whenStable();
    expect(text()).toContain('unsalted butter');
    expect(text()).toContain('water');
  });

  it('says how much of the registry is being shown', async () => {
    asked().flush(page([BUTTER], 912));
    await fixture.whenStable();
    expect(text()).toContain('1');
    expect(text()).toContain('912');
  });

  it('tells an empty registry from a failed request', async () => {
    asked().flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    expect(text()).toContain('Could not load');
  });

  describe('an entry nobody has looked at', () => {
    it('does not read as having no allergens', async () => {
      // The safety rule at the last place it can be broken (ADR-006). Water and crème
      // fraîche both have an empty list; only one of them has been checked, and crème
      // fraîche is milk.
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).toContain('Not checked');
      expect(text()).not.toContain('No allergens');
    });

    it('is not confused with one that carries none', async () => {
      asked().flush(page([WATER]));
      await fixture.whenStable();
      expect(text()).toContain('None of the fourteen');
      expect(text()).not.toContain('Not checked');
    });

    it('marks the two states differently, not just words them differently', async () => {
      /* Both were a grey chip with a sentence in it. On a screenful of entries the
         published table cannot answer for — spirits, wines — every row read the same, so
         "not checked" looked like the only answer the registry ever gives (G5). */
      asked().flush(page([WATER, CREME]));
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelector('.chip--clear')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('.chip--unknown')).not.toBeNull();
    });

    it('does not spend a line of the row saying what is not known', async () => {
      /* "No density" was on eight rows out of ten, in the same weight as the name, in a
         list where most of what was written was what was absent. It is still on the
         entry's own page, where it is worth reading (G4, X8). */
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).not.toContain('No density');
    });

    it('files each entry under the letter it begins with', async () => {
      // Nine hundred entries in one flat column is nothing to navigate by (G2, X6).
      asked().flush(page([CREME, WATER]));
      await fixture.whenStable();
      const letters = [...fixture.nativeElement.querySelectorAll('.registry__letter')].map(
        (node: Element) => node.textContent!.trim(),
      );
      // Crème fraîche files under C, not under a heading of its own.
      expect(letters).toEqual(['C', 'W']);
    });

    it('is marked as something an import invented', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).toContain('Added by an import');
    });
  });

  describe('narrowing the list', () => {
    it('asks only for what imports invented', async () => {
      asked().flush(page([BUTTER, CREME]));
      await fixture.whenStable();

      click('From imports');
      await fixture.whenStable();

      const request = asked();
      expect(request.request.params.get('origin')).toBe('user');
      request.flush(page([CREME]));
    });

    it('goes back to the whole registry', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();

      click('From imports');
      await fixture.whenStable();
      asked().flush(page([CREME]));
      await fixture.whenStable();

      click('All');
      await fixture.whenStable();

      const request = asked();
      expect(request.request.params.has('origin')).toBe(false);
      request.flush(page([BUTTER, CREME]));
    });

    it('says when nothing matches, rather than looking empty', async () => {
      asked().flush(page([]));
      await fixture.whenStable();
      expect(text()).toContain('Nothing here');
    });
  });

  describe('paging', () => {
    it('offers more when there is more', async () => {
      asked().flush(page([BUTTER], 912));
      await fixture.whenStable();
      expect(text()).toContain('Show more');
    });

    it('offers nothing more when the page is the whole list', async () => {
      asked().flush(page([BUTTER], 1));
      await fixture.whenStable();
      expect(text()).not.toContain('Show more');
    });

    it('appends the next page rather than replacing the first', async () => {
      asked().flush(page([BUTTER], 2));
      await fixture.whenStable();

      click('Show more');
      await fixture.whenStable();

      const request = asked();
      expect(request.request.params.get('offset')).toBe('1');
      request.flush(page([WATER], 2));
      await fixture.whenStable();

      expect(text()).toContain('unsalted butter');
      expect(text()).toContain('water');
    });

    it('starts again from the top when the list is narrowed', async () => {
      asked().flush(page([BUTTER], 2));
      await fixture.whenStable();
      click('Show more');
      await fixture.whenStable();
      asked().flush(page([WATER], 2));
      await fixture.whenStable();

      click('From imports');
      await fixture.whenStable();

      const request = asked();
      expect(request.request.params.get('offset')).toBe('0');
      request.flush(page([CREME]));
      await fixture.whenStable();

      // The old page is gone, not appended to.
      expect(text()).not.toContain('unsalted butter');
    });
  });

  describe('reviewing an entry', () => {
    it('marks what nobody has looked at', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).toContain('Needs a look');
    });

    it('says nothing about entries that have been looked at', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      expect(text()).not.toContain('Needs a look');
    });

    it('does not confuse review with what is inside the ingredient', async () => {
      // Wine is seeded, so approved, and the Swiss table could not answer for it, so
      // unclassified. More than half the shipped registry looks like this — a screen that
      // conflated the two would flag four hundred rows that need nothing (ADR-051).
      asked().flush(page([{ ...WATER, classified: false, approved: true }]));
      await fixture.whenStable();
      expect(text()).toContain('Not checked');
      expect(text()).not.toContain('Needs a look');
    });

    it('asks only for the queue when narrowed to it', async () => {
      asked().flush(page([BUTTER, CREME]));
      await fixture.whenStable();

      click('Needs review');
      await fixture.whenStable();

      const request = asked();
      expect(request.request.params.get('approved')).toBe('false');
      request.flush(page([CREME]));
    });

    it('offers an admin the button, and nobody else', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).not.toContain('Approve');
    });
  });

  describe('when an admin is looking', () => {
    beforeEach(async () => {
      TestBed.resetTestingModule();
      TestBed.configureTestingModule({
        imports: [RegistryComponent],
        providers: [
          provideZonelessChangeDetection(),
          provideRouter([]),
          provideHttpClient(),
          provideHttpClientTesting(),
          provideApi(''),
          { provide: AuthStore, useValue: { isAdmin: signal(true) } },
        ],
      });
      fixture = TestBed.createComponent(RegistryComponent);
      backend = TestBed.inject(HttpTestingController);
      await fixture.whenStable();
      tree();
    });

    it('offers to approve what needs a look', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).toContain('Approve');
    });

    it('does not offer to approve what is already settled', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      expect(text()).not.toContain('Approve');
    });

    it('records the approval and stops asking', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/registry/creme-fraiche/approved')
        .flush({ ...CREME, approved: true });
      await fixture.whenStable();

      expect(text()).not.toContain('Needs a look');
      expect(text()).toContain('crème fraîche');
    });

    it('keeps the entry when approving fails, rather than pretending', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/registry/creme-fraiche/approved')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain('Needs a look');
    });

    it('does not clear an approved entry from a queue it is no longer in', async () => {
      // Narrowed to the queue, approving removes the row: it stopped matching what is on
      // screen. Leaving it there would show an entry the filter says is not there.
      asked().flush(page([BUTTER, CREME]));
      await fixture.whenStable();
      click('Needs review');
      await fixture.whenStable();
      asked().flush(page([CREME], 1));
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();
      backend
        .expectOne('/api/v1/registry/creme-fraiche/approved')
        .flush({ ...CREME, approved: true });
      await fixture.whenStable();

      expect(text()).not.toContain('crème fraîche');
    });
  });

  describe('sweeping for duplicates', () => {
    it('does not sweep until asked', async () => {
      // It compares every entry with every other. On demand, because nobody arriving at
      // the registry asked that question.
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      backend.expectNone('/api/v1/registry/duplicates');
    });

    it('reports the pairs it found', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();

      click('Find possible duplicates');
      await fixture.whenStable();

      backend.expectOne('/api/v1/registry/duplicates').flush([
        {
          slug: 'brown-sugar',
          other: 'sugar-brown',
          name: 'brown sugar',
          other_name: 'sugar, brown',
          confidence: '1',
          reason: 'same_words',
        },
      ]);
      await fixture.whenStable();

      expect(text()).toContain('brown sugar');
      expect(text()).toContain('sugar, brown');
    });

    it('says why each pair is there', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      click('Find possible duplicates');
      await fixture.whenStable();
      backend.expectOne('/api/v1/registry/duplicates').flush([
        {
          slug: 'a',
          other: 'b',
          name: 'pizza dough',
          other_name: 'pizza doug',
          confidence: '1',
          reason: 'spelling',
        },
      ]);
      await fixture.whenStable();
      expect(text()).toContain('a close spelling');
    });

    it('says plainly when it found none, rather than showing nothing', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      click('Find possible duplicates');
      await fixture.whenStable();
      backend.expectOne('/api/v1/registry/duplicates').flush([]);
      await fixture.whenStable();
      expect(text()).toContain('No likely duplicates');
    });

    it('keeps the registry list when the sweep fails', async () => {
      asked().flush(page([BUTTER]));
      await fixture.whenStable();
      click('Find possible duplicates');
      await fixture.whenStable();
      backend
        .expectOne('/api/v1/registry/duplicates')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain('unsalted butter');
    });
  });
});
