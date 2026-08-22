import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { vi } from 'vitest';
import { RecipeDetailComponent } from './recipe-detail.component';

function pancakes(flour = '125 g', yieldDisplay = '12 piece', serves: string | null = null) {
  return {
    id: 1,
    title: 'Pancakes',
    summary: 'Batter, pan, patience.',
    yield_quantity: { magnitude: '12', unit: 'piece', display: yieldDisplay },
    serves,
    visibility: 'private',
    provenance: 'authored',
    lines: [
      {
        ingredient: 'plain flour',
        quantity: { magnitude: '125', unit: 'g', display: flour },
        preparation: 'sifted',
        optional: false,
      },
      {
        ingredient: 'egg',
        quantity: { magnitude: '2', unit: 'piece', display: '2 piece' },
        preparation: null,
        optional: true,
      },
    ],
    steps: [
      {
        position: 0,
        instruction: 'Whisk.',
        duration_seconds: null,
        temperature_celsius: null,
        attention: 'hands_on',
      },
      {
        position: 1,
        instruction: 'Rest.',
        duration_seconds: 1800,
        temperature_celsius: null,
        attention: 'waiting',
      },
      {
        position: 2,
        instruction: 'Fry.',
        duration_seconds: null,
        temperature_celsius: 180,
        attention: 'hands_on',
      },
    ],
    timing: {
      hands_on: { seconds: 600, at_least: true },
      total: { seconds: 2400, at_least: true },
      ahead: null,
    },
  };
}

describe('RecipeDetailComponent', () => {
  let fixture: ComponentFixture<RecipeDetailComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RecipeDetailComponent],
      providers: [
        provideZonelessChangeDetection(),
        // A made version navigates to itself, so the route has to exist to be reached.
        provideRouter([{ path: 'recipes/:id', children: [] }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: new Map([['id', '1']]) } } },
      ],
    });
    fixture = TestBed.createComponent(RecipeDetailComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  describe('reading a recipe', () => {
    it('asks for the recipe named in the route', () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
    });

    it('shows the ingredients as the backend rendered them', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).toContain('125 g');
      expect(text()).toContain('plain flour');
    });

    it('shows a preparation note with its line', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).toContain('sifted');
    });

    it('marks an optional ingredient as optional', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).toContain('optional');
    });

    it('shows the steps in order', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      const steps = [...fixture.nativeElement.querySelectorAll('.recipe__step-text')];
      expect(steps.map((s: HTMLElement) => s.textContent?.trim())).toEqual([
        'Whisk.',
        'Rest.',
        'Fry.',
      ]);
    });

    it('surfaces a timing as a readable duration, not a count of seconds', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).toContain('30 min');
      expect(text()).not.toContain('1800');
    });

    it('surfaces a temperature', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).toContain('180');
    });
  });

  describe('changing the yield', () => {
    it('asks the backend to scale rather than doing arithmetic here', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();

      fixture.componentInstance.showFor(6);
      await settle();

      const scaled = backend.expectOne('/api/v1/recipes/1?servings=6');
      scaled.flush(pancakes('62.7 g', '6 piece'));
      await settle();
      expect(text()).toContain('62.7 g');
    });

    it('will not ask for a yield of nothing', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      fixture.componentInstance.showFor(0);
      await settle();
      backend.expectNone('/api/v1/recipes/1?servings=0');
    });
  });

  describe('when it cannot be shown', () => {
    it('says a missing recipe is missing', async () => {
      backend
        .expectOne('/api/v1/recipes/1')
        .flush({ detail: 'No such recipe.' }, { status: 404, statusText: 'Not Found' });
      await settle();
      expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
        'could not be found',
      );
    });
  });

  it('shows a line the cook judges themselves without inventing a number', async () => {
    /* "Salt, to taste" has no quantity. A zero or a one there would be a lie. */
    const recipe = {
      ...pancakes(),
      lines: [
        { ingredient: 'fine salt', quantity: null, preparation: 'to taste', optional: false },
      ],
    };
    backend.expectOne('/api/v1/recipes/1').flush(recipe);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('fine salt');
    expect(text()).toContain('to taste');
    // The quantity column is empty rather than holding a fabricated number. Asserted on
    // the element, because the page elsewhere is full of digits — "30 min", "180 °C".
    const quantity = fixture.nativeElement.querySelector('.lines__quantity');
    expect(quantity.textContent.trim()).toBe('');
  });

  it('shows the verdict above the ingredients, not after them', async () => {
    backend.expectOne('/api/v1/recipes/1').flush({
      ...pancakes(),
      suitability: {
        outcome: 'unsuitable',
        findings: [
          {
            eater: 'Mira',
            ingredient: 'peanut butter',
            severity: 'medical',
            allergen: 'peanuts',
            avoidable: false,
            unknown: false,
          },
        ],
      },
    });
    await fixture.whenStable();
    fixture.detectChanges();
    const html = fixture.nativeElement.innerHTML;
    expect(html).toContain('Not suitable');
    expect(html.indexOf('Not suitable')).toBeLessThan(html.indexOf('Ingredients'));
  });

  it('says nothing at all when there is nobody to judge against', async () => {
    backend.expectOne('/api/v1/recipes/1').flush({ ...pancakes(), suitability: null });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.verdict')).toBeNull();
  });

  describe('how many it feeds', () => {
    it('says so where the yield counts something other than portions', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes('125 g', '12 piece', '4'));
      await settle();
      expect(text()).toContain('Serves');
      expect(text()).toContain('4');
    });

    it('says nothing where the recipe never said', async () => {
      /* Absent is an answer. A pieces-per-serving figure invented for the screen would
         be a number a cook cannot see is wrong. */
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(text()).not.toContain('Serves');
    });
  });

  describe('how long it takes', () => {
    it('answers before the ingredients, not after the method', async () => {
      // Asked before a cook decides to read the rest, so answered there.
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();

      const header = fixture.nativeElement.querySelector('.recipe__header');
      expect(header.textContent).toContain('hands-on');
      expect(header.textContent).toContain('at least 10 min');
    });

    it('marks the step a cook can walk away from', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();

      const steps = fixture.nativeElement.querySelectorAll('.steps__step');
      expect(steps[1].textContent).toContain('you can walk away');
    });

    it('leaves ordinary work unmarked', async () => {
      // A badge on every hands-on step would mark the whole method and single out none.
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();

      const steps = fixture.nativeElement.querySelectorAll('.steps__step');
      expect(steps[0].querySelector('.fact--quiet')).toBeNull();
    });

    it('says nothing where the recipe says nothing', async () => {
      backend.expectOne('/api/v1/recipes/1').flush({ ...pancakes(), timing: null });
      await settle();

      expect(fixture.nativeElement.querySelector('app-timing')).toBeNull();
    });
  });

  describe('making a version of it', () => {
    it('will not ask with nothing to change', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(fixture.nativeElement.querySelector('.recipe__vary button').disabled).toBe(true);
    });

    function ask(change: string): void {
      const field = fixture.nativeElement.querySelector('#change');
      field.value = change;
      field.dispatchEvent(new Event('input'));
      fixture.detectChanges();
      fixture.nativeElement.querySelector('.recipe__vary form').dispatchEvent(new Event('submit'));
    }

    it('sends what the cook wants changed', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      ask('make it dairy-free');

      const asked = backend.expectOne('/api/v1/recipes/1/variants');
      expect(asked.request.body).toEqual({ change: 'make it dairy-free' });
      asked.flush({ ...pancakes(), id: 4 });
    });

    it('shows who and what when the version is refused', async () => {
      // Not an error string: asking for a dairy-free version and being handed one with
      // cream in it is the case that rule exists for (ADR-047).
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      ask('make it dairy-free');

      backend.expectOne('/api/v1/recipes/1/variants').flush(
        {
          detail: {
            message: 'The version that came back is not suitable for your household.',
            verdict: {
              outcome: 'unsuitable',
              findings: [
                {
                  eater: 'Mira',
                  ingredient: 'double cream',
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

      expect(text()).toContain('Mira');
      expect(text()).toContain('double cream');
      expect(text()).toContain('not suitable for your household');
    });

    it('says where a version came from, and links back', async () => {
      backend
        .expectOne('/api/v1/recipes/1')
        .flush({ ...pancakes(), derived_from: 9, derived_from_title: 'Buttermilk Pancakes' });
      await settle();

      const back = fixture.nativeElement.querySelector('.recipe__derived a');
      expect(back.textContent).toContain('Buttermilk Pancakes');
      expect(back.getAttribute('href')).toBe('/recipes/9');
    });

    it('says nothing about where it came from when it came from nowhere', async () => {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
      expect(fixture.nativeElement.querySelector('.recipe__derived')).toBeNull();
    });
  });

  describe('what a cook does next', () => {
    /**
     * The complaint this answers: a recipe screen you can read and then not act on. The
     * two things a cook wants from a dish they have just decided on are to make it now
     * and to make it on Thursday, and neither was reachable from here.
     */
    function router(): Router {
      return TestBed.inject(Router);
    }

    async function shown(): Promise<void> {
      backend.expectOne('/api/v1/recipes/1').flush(pancakes());
      await settle();
    }

    it('starts cooking this recipe, planned or not', async () => {
      await shown();
      const go = vi.spyOn(router(), 'navigateByUrl').mockResolvedValue(true);

      fixture.nativeElement.querySelector('.recipe__cook').click();
      await settle();

      const asked = backend.expectOne('/api/v1/cooking/sessions/for-recipe');
      expect(asked.request.body).toEqual({ recipe_id: 1 });
      asked.flush({ id: 7 });
      await settle();

      expect(go).toHaveBeenCalledWith('/cook/7');
    });

    it('says so rather than going quiet when cooking will not start', async () => {
      await shown();
      fixture.nativeElement.querySelector('.recipe__cook').click();
      await settle();
      backend
        .expectOne('/api/v1/cooking/sessions/for-recipe')
        .flush({}, { status: 404, statusText: 'Not Found' });
      await settle();

      expect(text()).toContain('could not be started');
    });

    it('takes a cook to the week they are planning, with the dish already chosen', async () => {
      await shown();
      const go = vi.spyOn(router(), 'navigateByUrl').mockResolvedValue(true);

      fixture.nativeElement.querySelector('.recipe__plan').click();
      await settle();
      backend.expectOne('/api/v1/plans/current').flush({ id: 4, slots: [] });
      await settle();

      expect(go).toHaveBeenCalledWith('/plans/4/meal?recipe=1');
    });

    it('sends a cook with no plan yet to make one', async () => {
      // Rather than a dead button or an error. Nothing is wrong; there is simply a step
      // in front of the one they asked for.
      await shown();
      const go = vi.spyOn(router(), 'navigateByUrl').mockResolvedValue(true);

      fixture.nativeElement.querySelector('.recipe__plan').click();
      await settle();
      backend.expectOne('/api/v1/plans/current').flush(null);
      await settle();

      expect(go).toHaveBeenCalledWith('/plans');
    });
  });
});
