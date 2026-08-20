import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { RecipeDetailComponent } from './recipe-detail.component';

function pancakes(flour = '125 g', yieldDisplay = '12 piece') {
  return {
    id: 1,
    title: 'Pancakes',
    summary: 'Batter, pan, patience.',
    yield_quantity: { magnitude: '12', unit: 'piece', display: yieldDisplay },
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
      { position: 0, instruction: 'Whisk.', duration_seconds: null, temperature_celsius: null },
      { position: 1, instruction: 'Rest.', duration_seconds: 1800, temperature_celsius: null },
      { position: 2, instruction: 'Fry.', duration_seconds: null, temperature_celsius: 180 },
    ],
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
        provideRouter([]),
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
});
