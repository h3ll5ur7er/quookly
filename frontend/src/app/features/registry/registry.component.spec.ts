import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
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
      expect(text()).toContain('No allergens');
      expect(text()).not.toContain('Not checked');
    });

    it('shows that its density is missing', async () => {
      asked().flush(page([CREME]));
      await fixture.whenStable();
      expect(text()).toContain('No density');
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
});
