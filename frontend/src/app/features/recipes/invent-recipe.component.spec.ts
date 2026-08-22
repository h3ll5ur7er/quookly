import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { InventRecipeComponent } from './invent-recipe.component';

const PANTRY = [
  {
    ingredient_id: 7,
    slug: 'spinach',
    name: 'spinach',
    kind: 'solid',
    freshness: 'soon',
    lots: [],
  },
  { ingredient_id: 9, slug: 'rice', name: 'rice', kind: 'powder', freshness: 'fresh', lots: [] },
];

describe('InventRecipeComponent', () => {
  let fixture: ComponentFixture<InventRecipeComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function open(pantry: unknown[] = PANTRY): Promise<void> {
    backend.expectOne('/api/v1/pantry').flush(pantry);
    await settle();
  }

  function type(written: string): void {
    fixture.nativeElement.querySelector('#description').value = written;
    fixture.nativeElement.querySelector('#description').dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [InventRecipeComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'recipes/:id', children: [] }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(InventRecipeComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  describe('asking', () => {
    it('will not ask with nothing to go on', async () => {
      // "Write me a recipe" with no constraints is a question with too many answers.
      await open();
      expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(true);
    });

    it('a description is enough', async () => {
      await open();
      type('something quick with chicken');
      expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);
    });

    it('picking something from the pantry is enough', async () => {
      await open();
      fixture.nativeElement.querySelector('.invent__pick input').click();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);
    });

    it('sends what was said and what was picked', async () => {
      await open();
      type('a pie');
      fixture.nativeElement.querySelector('.invent__pick input').click();
      fixture.detectChanges();
      fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));

      const asked = backend.expectOne('/api/v1/recipes/generated');
      expect(asked.request.body).toEqual({
        description: 'a pie',
        ingredient_ids: [7],
        serves: 4,
      });
      asked.flush({ id: 3 });
    });

    it('marks what needs using rather than reordering the shelf', async () => {
      // A pantry a cook can learn the shape of beats one that rearranges itself.
      await open();
      const chips = fixture.nativeElement.querySelectorAll('.invent__pick');
      expect(chips[0].textContent).toContain('needs using');
      expect(chips[1].textContent).not.toContain('needs using');
    });

    it('still works with an empty pantry', async () => {
      // A pantry that will not load is not a reason to refuse to write a recipe.
      await open([]);
      type('a pie');
      expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);
    });

    it('explains the wait rather than spinning at it', async () => {
      await open();
      type('a pie');
      fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
      await settle();

      expect(text()).toContain('written from scratch');
      backend.expectOne('/api/v1/recipes/generated').flush({ id: 3 });
    });
  });

  describe('when it comes back refused', () => {
    async function refuse(): Promise<void> {
      await open();
      type('a pie');
      fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
      backend.expectOne('/api/v1/recipes/generated').flush(
        {
          detail: {
            message: 'What came back is not suitable for your household.',
            verdict: {
              outcome: 'unsuitable',
              findings: [
                {
                  eater: 'Mira',
                  ingredient: 'parmesan',
                  severity: 'medical',
                  allergen: 'milk',
                  avoidable: false,
                  unknown: false,
                },
              ],
            },
          },
        },
        { status: 422, statusText: 'Unprocessable Content' },
      );
      await settle();
    }

    it('shows who and what, not an error string', async () => {
      // "Mira — parmesan" is something a cook can act on (ADR-006).
      await refuse();
      expect(text()).toContain('Mira');
      expect(text()).toContain('parmesan');
    });

    it('says the recipe was not kept', async () => {
      await refuse();
      expect(text()).toContain('not suitable for your household');
    });

    it('leaves the cook where they were, able to ask again', async () => {
      await refuse();
      expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);
    });
  });

  describe('when it cannot help', () => {
    it('says what the API said rather than flattening it', async () => {
      await open();
      type('a pie');
      fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
      backend
        .expectOne('/api/v1/recipes/generated')
        .flush(
          { detail: 'Writing a recipe needs a model, and this instance has none configured.' },
          { status: 422, statusText: 'Unprocessable Content' },
        );
      await settle();

      expect(text()).toContain('none configured');
    });
  });
});
