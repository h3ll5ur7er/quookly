import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { IngredientComponent } from './ingredient.component';

/** What an import leaves behind: a guessed kind, no density, nobody has looked. */
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

function detail(entry: Record<string, unknown> = CREME, names?: Record<string, string[]>) {
  return { entry, names: names ?? { 'en-GB': ['crème fraîche'] } };
}

describe('IngredientComponent', () => {
  let fixture: ComponentFixture<IngredientComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

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

  function set(selector: string, value: string): void {
    const field: HTMLInputElement | HTMLSelectElement =
      fixture.nativeElement.querySelector(selector);
    field.value = value;
    field.dispatchEvent(new Event('change'));
    field.dispatchEvent(new Event('input'));
  }

  function tick(value: string): void {
    const box: HTMLInputElement = fixture.nativeElement.querySelector(
      `input[type="checkbox"][value="${value}"]`,
    );
    box.click();
  }

  async function arrive({ admin = false } = {}): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [IngredientComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: AuthStore, useValue: { isAdmin: signal(admin) } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => 'creme-fraiche' } } },
        },
      ],
    });
    fixture = TestBed.createComponent(IngredientComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  }

  function asked() {
    return backend.expectOne('/api/v1/registry/creme-fraiche');
  }

  afterEach(() => backend.verify());

  describe('reading it', () => {
    beforeEach(() => arrive());

    it('asks for the entry named in the address', () => {
      asked().flush(detail());
    });

    it('shows what it is called', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      expect(text()).toContain('crème fraîche');
    });

    it('shows the languages it answers to', async () => {
      asked().flush(
        detail(CREME, { 'en-GB': ['crème fraîche'], 'de-CH': ['Crème fraîche', 'Sauerrahm'] }),
      );
      await fixture.whenStable();
      expect(text()).toContain('Sauerrahm');
    });

    it('says when it only knows one language', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      expect(text()).toContain('Only known in one language');
    });

    it('tells a missing entry from a broken request', async () => {
      asked().flush({}, { status: 404, statusText: 'Not Found' });
      await fixture.whenStable();
      expect(text()).toContain('No such ingredient');
    });

    it('offers a cook nothing to change', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      expect(text()).not.toContain('Save corrections');
      expect(text()).not.toContain('Record what is in it');
    });
  });

  describe('correcting it', () => {
    beforeEach(() => arrive({ admin: true }));

    it('sends only the fields that were changed', async () => {
      asked().flush(detail());
      await fixture.whenStable();

      set('#kind', 'liquid');
      await fixture.whenStable();
      click('Save corrections');
      await fixture.whenStable();

      const request = backend.expectOne('/api/v1/registry/creme-fraiche');
      expect(request.request.method).toBe('PUT');
      // Density was never touched, so it must not travel: sending `null` would clear a
      // figure the admin did not mean to clear.
      expect(request.request.body).toEqual({ kind: 'liquid' });
      request.flush({ ...CREME, kind: 'liquid' });
    });

    it('sends a cleared density as an explicit null', async () => {
      asked().flush(detail({ ...CREME, density: '0.9780' }));
      await fixture.whenStable();

      set('#density', '');
      await fixture.whenStable();
      click('Save corrections');
      await fixture.whenStable();

      const request = backend.expectOne('/api/v1/registry/creme-fraiche');
      expect(request.request.body).toEqual({ density: null });
      request.flush({ ...CREME, density: null });
    });

    it('says so when there is nothing to save', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      click('Save corrections');
      await fixture.whenStable();
      expect(text()).toContain('Nothing changed');
    });

    it('keeps the form when saving fails', async () => {
      asked().flush(detail());
      await fixture.whenStable();

      set('#kind', 'liquid');
      await fixture.whenStable();
      click('Save corrections');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/registry/creme-fraiche')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain('Could not save');
      const kind: HTMLSelectElement = fixture.nativeElement.querySelector('#kind');
      expect(kind.value).toBe('liquid');
    });
  });

  describe('saying what is in it', () => {
    beforeEach(() => arrive({ admin: true }));

    it('starts from nobody having looked', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      expect(text()).toContain('Nobody has looked');
    });

    it('records what was ticked', async () => {
      asked().flush(detail());
      await fixture.whenStable();

      tick('milk');
      await fixture.whenStable();
      click('Record what is in it');
      await fixture.whenStable();

      const request = backend.expectOne('/api/v1/registry/creme-fraiche/allergens');
      expect(request.request.method).toBe('PUT');
      expect(request.request.body).toEqual({ allergens: ['milk'] });
      request.flush({ ...CREME, allergens: ['milk'], classified: true });
    });

    it('treats ticking nothing as a real answer, not as a blank form', async () => {
      // "I looked, there is nothing in it" is a different fact from "nobody has looked",
      // and this is the one control that can say the first (ADR-006).
      asked().flush(detail());
      await fixture.whenStable();

      click('Record what is in it');
      await fixture.whenStable();

      const request = backend.expectOne('/api/v1/registry/creme-fraiche/allergens');
      expect(request.request.body).toEqual({ allergens: [] });
      request.flush({ ...CREME, allergens: [], classified: true });
      await fixture.whenStable();

      expect(text()).toContain('Contains none');
      expect(text()).not.toContain('Nobody has looked');
    });

    it('shows an examined entry as examined', async () => {
      asked().flush(detail({ ...CREME, allergens: ['milk'], classified: true }));
      await fixture.whenStable();
      expect(text()).not.toContain('Nobody has looked');
    });
  });

  describe('teaching it a language', () => {
    beforeEach(() => arrive({ admin: true }));

    it('adds a spelling without touching the others', async () => {
      asked().flush(detail());
      await fixture.whenStable();

      set('#locale', 'de-CH');
      set('#spelling', 'Sauerrahm');
      await fixture.whenStable();
      click('Add the name');
      await fixture.whenStable();

      const request = backend.expectOne('/api/v1/registry/creme-fraiche/names');
      expect(request.request.method).toBe('POST');
      expect(request.request.body).toEqual({ locale: 'de-CH', spellings: ['Sauerrahm'] });
      request.flush(detail(CREME, { 'en-GB': ['crème fraîche'], 'de-CH': ['Sauerrahm'] }));
      await fixture.whenStable();

      expect(text()).toContain('Sauerrahm');
      expect(text()).toContain('crème fraîche');
    });

    it('says which entry already owns a name it cannot have', async () => {
      // The failure found by running it against a seeded instance: `Sauerrahm` in de-CH
      // already means `sour-cream-35-fat`. Naming the other entry is the useful part —
      // two entries claiming one name in one language are often one ingredient.
      asked().flush(detail());
      await fixture.whenStable();

      set('#locale', 'de-CH');
      set('#spelling', 'Sauerrahm');
      await fixture.whenStable();
      click('Add the name');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/registry/creme-fraiche/names')
        .flush(
          { detail: "'Sauerrahm' is already what this language calls 'sour-cream-35-fat'." },
          { status: 409, statusText: 'Conflict' },
        );
      await fixture.whenStable();

      expect(text()).toContain('sour-cream-35-fat');
    });
  });

  describe('approving it', () => {
    beforeEach(() => arrive({ admin: true }));

    it('offers the button while it needs a look', async () => {
      asked().flush(detail());
      await fixture.whenStable();
      expect(text()).toContain('Approve');
    });

    it('stops offering it once approved', async () => {
      asked().flush(detail());
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/registry/creme-fraiche/approved')
        .flush({ ...CREME, approved: true });
      await fixture.whenStable();

      expect(text()).not.toContain('Needs a look');
    });

    it('does not offer it for an entry already settled', async () => {
      asked().flush(detail({ ...CREME, approved: true }));
      await fixture.whenStable();
      expect(text()).not.toContain('Approve');
    });
  });
});
