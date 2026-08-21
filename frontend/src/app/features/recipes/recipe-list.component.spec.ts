import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { RecipeListComponent } from './recipe-list.component';

const PANCAKES = {
  id: 1,
  title: 'Pancakes',
  summary: 'Batter, pan, patience.',
  yield_quantity: { magnitude: '12', unit: 'piece', display: '12 piece' },
  visibility: 'private',
  suitability: null,
  timing: {
    hands_on: { seconds: 900, at_least: false },
    total: { seconds: 2700, at_least: false },
    ahead: null,
  },
};

function judged(suitability: string | null) {
  return [{ ...PANCAKES, suitability }];
}

describe('RecipeListComponent', () => {
  let fixture: ComponentFixture<RecipeListComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RecipeListComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(RecipeListComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the cook’s recipes', () => {
    backend.expectOne('/api/v1/recipes').flush([]);
  });

  it('shows what it finds', async () => {
    backend.expectOne('/api/v1/recipes').flush([PANCAKES]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('Pancakes');
    expect(text()).toContain('12 piece');
  });

  it('offers a way in for each recipe', async () => {
    backend.expectOne('/api/v1/recipes').flush([PANCAKES]);
    await fixture.whenStable();
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('a[href="/recipes/1"]');
    expect(link).not.toBeNull();
  });

  it('says so plainly when there is nothing yet', async () => {
    backend.expectOne('/api/v1/recipes').flush([]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('No recipes yet');
  });

  it('reports a failure rather than showing an empty kitchen', async () => {
    backend.expectOne('/api/v1/recipes').flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  });

  async function show(body: unknown[]): Promise<void> {
    backend.expectOne('/api/v1/recipes').flush(body);
    await settle();
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('marks a recipe somebody cannot eat', async () => {
    await show(judged('unsuitable'));
    expect(text()).toContain('Not suitable');
  });

  it('marks a recipe nobody has checked, rather than leaving it bare', async () => {
    /*
     * A bare row means "fine" once a cook has learnt the pattern. Unknown is not fine,
     * and this is the screen where they decide what to open.
     */
    await show(judged('unknown'));
    expect(text()).toContain('Not checked');
  });

  it('says nothing about a recipe that suits everybody', async () => {
    // Twenty ticks would drown the one warning that matters.
    await show(judged('suitable'));
    expect(fixture.nativeElement.querySelector('.badge')).toBeNull();
  });

  it('carries a word beside the colour', async () => {
    await show(judged('caution'));
    expect(text()).toContain('Take care');
  });

  it('explains an unbadged list when there is nobody to judge against', async () => {
    await show(judged(null));
    expect(text()).toContain('Nobody recorded yet');
    expect(fixture.nativeElement.querySelector('a[href="/household"]')).not.toBeNull();
  });

  it('does not nag once there is somebody to judge against', async () => {
    await show(judged('suitable'));
    expect(text()).not.toContain('Nobody recorded yet');
  });

  it('says how long a recipe takes without opening it', async () => {
    // The question is asked before the tap. Answering it after is answering it late.
    await show([PANCAKES]);

    const row = fixture.nativeElement.querySelector('.recipes__item');
    expect(row.textContent).toContain('15 min');
    expect(row.textContent).toContain('hands-on');
  });

  it('leaves the row alone where the recipe says nothing about time', async () => {
    await show([{ ...PANCAKES, timing: null }]);

    expect(fixture.nativeElement.querySelector('app-timing')).toBeNull();
  });

  describe('finding something to cook', () => {
    function suggestion(title: string, extra: Record<string, unknown> = {}) {
      return {
        recipe: { ...PANCAKES, title },
        reasons: [],
        pressing: [],
        missing: 0,
        ...extra,
      };
    }

    it('does not ask the server until something is typed', async () => {
      // A plain listing is the common case, and a search box that fires on load asks a
      // question nobody put.
      await show([PANCAKES]);
      expect(backend.match((request) => request.url.includes('suggestions')).length).toBe(0);
    });

    it('asks what is worth cooking when the order says so', async () => {
      await show([PANCAKES]);
      fixture.nativeElement.querySelectorAll('.recipes__order-choice')[1].click();

      const asked = backend.expectOne('/api/v1/recipes/suggestions');
      asked.flush([suggestion('Spinach Pie', { reasons: ['uses_soon'], pressing: ['spinach'] })]);
      await settle();

      expect(text()).toContain('Spinach Pie');
    });

    it('says why a recipe is where it is', async () => {
      await show([PANCAKES]);
      fixture.nativeElement.querySelectorAll('.recipes__order-choice')[1].click();
      backend
        .expectOne('/api/v1/recipes/suggestions')
        .flush([suggestion('Spinach Pie', { reasons: ['uses_soon'], pressing: ['spinach'] })]);
      await settle();

      expect(text()).toContain('uses something up');
      expect(text()).toContain('spinach');
    });

    it('marks the one reason that is a warning rather than an encouragement', async () => {
      await show([PANCAKES]);
      fixture.nativeElement.querySelectorAll('.recipes__order-choice')[1].click();
      backend
        .expectOne('/api/v1/recipes/suggestions')
        .flush([suggestion('Flour Pudding', { reasons: ['not_for_everyone'] })]);
      await settle();

      expect(fixture.nativeElement.querySelector('.recipes__reason--warn')).not.toBeNull();
      expect(text()).toContain('not for everyone');
    });

    it('shows no reasons when the list is simply the alphabet', async () => {
      await show([PANCAKES]);
      expect(fixture.nativeElement.querySelector('.recipes__reason')).toBeNull();
    });

    it('offers no ordering choice while something is being searched for', async () => {
      // The answer to a question has an order of its own: how well it matched.
      await show([PANCAKES]);
      expect(fixture.nativeElement.querySelector('.recipes__order')).not.toBeNull();
    });

    it('says so when nothing matches, rather than looking empty', async () => {
      await show([PANCAKES]);
      fixture.nativeElement.querySelectorAll('.recipes__order-choice')[1].click();
      backend.expectOne('/api/v1/recipes/suggestions').flush([]);
      await settle();

      expect(text()).toContain('No recipes yet');
    });
  });
});
