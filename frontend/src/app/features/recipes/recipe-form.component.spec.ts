import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { vi } from 'vitest';
import { RecipeFormComponent } from './recipe-form.component';

const PRESENTED = {
  id: 7,
  title: 'Pancakes',
  summary: 'Batter, pan, patience.',
  yield_quantity: { magnitude: '12', unit: 'piece', display: '12 piece' },
  serves: null,
  visibility: 'private',
  suitability: null,
  timing: null,
  nutrition: null,
  lines: [
    {
      ingredient: 'plain flour',
      ingredient_id: 3,
      ingredient_kind: 'powder',
      quantity: { magnitude: '225', unit: 'g', display: '225 g' },
      preparation: 'sifted',
      optional: false,
    },
  ],
  steps: [{ position: 0, instruction: 'Whisk it.', duration_seconds: 300, attention: 'hands_on' }],
};

describe('RecipeFormComponent', () => {
  let fixture: ComponentFixture<RecipeFormComponent>;
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
    const field: HTMLInputElement = fixture.nativeElement.querySelector(selector);
    field.value = value;
    field.dispatchEvent(new Event('input'));
    field.dispatchEvent(new Event('change'));
  }

  async function arrive(recipeId: string | null): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RecipeFormComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'recipes/:id', children: [] }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => recipeId } } },
        },
      ],
    });
    fixture = TestBed.createComponent(RecipeFormComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  }

  afterEach(() => {
    vi.useRealTimers();
    backend.verify();
  });

  /**
   * Open the picker, type, and let the debounce elapse.
   *
   * Fake timers because the search is settled before it asks — a box that fires on every
   * keystroke asks the server about "f", "fl" and "flo" to answer a question about flour.
   */
  async function pick(term: string, found: unknown[]): Promise<void> {
    click('Choose an ingredient');
    await fixture.whenStable();

    vi.useFakeTimers();
    const search: HTMLInputElement = fixture.nativeElement.querySelector('.line__search');
    search.value = term;
    search.dispatchEvent(new Event('input'));
    await vi.advanceTimersByTimeAsync(300);
    vi.useRealTimers();
    await fixture.whenStable();

    backend.expectOne((request) => request.url === '/api/v1/ingredients').flush(found);
    await fixture.whenStable();
  }

  describe('writing a new one', () => {
    beforeEach(() => arrive(null));

    it('asks the server for nothing', () => {
      // Nothing to load. A blank form that fetched something would be asking about a
      // recipe that does not exist yet.
      backend.verify();
    });

    it('starts with somewhere to put an ingredient and a step', async () => {
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelectorAll('.line').length).toBe(1);
      expect(fixture.nativeElement.querySelectorAll('.step').length).toBe(1);
    });

    it('will not send a recipe with no title', async () => {
      await fixture.whenStable();
      click('Save recipe');
      await fixture.whenStable();
      backend.expectNone('/api/v1/recipes');
      expect(text()).toContain('needs a title');
    });

    it('sends what was typed', async () => {
      await fixture.whenStable();
      set('#title', 'Sourdough');
      set('#yield-magnitude', '2');
      await fixture.whenStable();

      await pick('flour', [{ id: 3, slug: 'plain-flour', name: 'plain flour', kind: 'powder' }]);
      click('plain flour');
      await fixture.whenStable();

      set('.line__magnitude', '500');
      set('.step__instruction', 'Mix, prove, bake.');
      await fixture.whenStable();

      click('Save recipe');
      await fixture.whenStable();

      const sent = backend.expectOne('/api/v1/recipes');
      expect(sent.request.method).toBe('POST');
      expect(sent.request.body.title).toBe('Sourdough');
      expect(sent.request.body.lines[0].ingredient_id).toBe(3);
      expect(sent.request.body.lines[0].magnitude).toBe('500');
      expect(sent.request.body.steps[0].instruction).toBe('Mix, prove, bake.');
      sent.flush(PRESENTED);
    });

    it('says so when saving fails, and keeps what was typed', async () => {
      await fixture.whenStable();
      set('#title', 'Sourdough');
      await fixture.whenStable();
      await pick('flour', [{ id: 3, slug: 'plain-flour', name: 'plain flour', kind: 'powder' }]);
      click('plain flour');
      set('.line__magnitude', '500');
      set('.step__instruction', 'Mix.');
      await fixture.whenStable();

      click('Save recipe');
      await fixture.whenStable();
      backend.expectOne('/api/v1/recipes').flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain('Could not save');
      const title: HTMLInputElement = fixture.nativeElement.querySelector('#title');
      expect(title.value).toBe('Sourdough');
    });
  });

  describe('correcting one that exists', () => {
    beforeEach(async () => {
      await arrive('7');
      backend.expectOne('/api/v1/recipes/7').flush(PRESENTED);
      await fixture.whenStable();
    });

    it('arrives filled in', () => {
      const title: HTMLInputElement = fixture.nativeElement.querySelector('#title');
      expect(title.value).toBe('Pancakes');
      expect(fixture.nativeElement.querySelectorAll('.line').length).toBe(1);
      expect(fixture.nativeElement.querySelectorAll('.step').length).toBe(1);
    });

    it('keeps the ingredient a line already points at', () => {
      expect(text()).toContain('plain flour');
    });

    it('sends the whole recipe, not a patch', async () => {
      set('#title', 'Buttermilk Pancakes');
      await fixture.whenStable();
      click('Save recipe');
      await fixture.whenStable();

      const sent = backend.expectOne('/api/v1/recipes/7');
      expect(sent.request.method).toBe('PUT');
      expect(sent.request.body.title).toBe('Buttermilk Pancakes');
      // Everything travels: lines and steps are ordered, so the server replaces rather
      // than patches and a partial body would delete what it left out.
      expect(sent.request.body.lines.length).toBe(1);
      expect(sent.request.body.steps.length).toBe(1);
      sent.flush(PRESENTED);
    });

    it('says when the recipe is not there', async () => {
      TestBed.resetTestingModule();
      await arrive('9999');
      backend.expectOne('/api/v1/recipes/9999').flush({}, { status: 404, statusText: 'Not Found' });
      await fixture.whenStable();
      expect(text()).toContain('No such recipe');
    });
  });

  describe('lines and steps', () => {
    beforeEach(() => arrive(null));

    it('another line can be added', async () => {
      await fixture.whenStable();
      click('Add an ingredient');
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelectorAll('.line').length).toBe(2);
    });

    it('another step can be added', async () => {
      await fixture.whenStable();
      click('Add a step');
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelectorAll('.step').length).toBe(2);
    });

    it('a line can be taken out', async () => {
      await fixture.whenStable();
      click('Add an ingredient');
      await fixture.whenStable();
      const remove: HTMLButtonElement[] = Array.from(
        fixture.nativeElement.querySelectorAll('.line__remove'),
      );
      remove[0].click();
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelectorAll('.line').length).toBe(1);
    });

    it('the last line cannot be taken out', async () => {
      // A recipe with no ingredients is refused by the server; leaving the cook with an
      // empty form and a rejection is a worse way to say so.
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelector('.line__remove')).toBeNull();
    });
  });
});
