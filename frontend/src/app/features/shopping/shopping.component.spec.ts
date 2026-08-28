import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { ShoppingComponent } from './shopping.component';

function plan(
  lines: object[] = [{ ingredient_id: 4, name: 'plain flour', quantity: '200 g', bought: false }],
): object {
  return {
    id: 3,
    starts_on: '2026-08-24',
    ends_on: '2026-08-30',
    slots: [],
    shopping: lines,
  };
}

describe('ShoppingComponent', () => {
  let fixture: ComponentFixture<ShoppingComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function showing(answer: object | null = plan()): Promise<void> {
    backend.expectOne('/api/v1/plans/current').flush(answer);
    // The food tree, for the aisle headings. Asked for alongside the list rather than
    // after it: the two are independent, and a list that waited for its headings would
    // be a list a cook in a shop waited for (S2).
    backend.expectOne('/api/v1/registry/categories').flush([]);
    await settle();
  }

  function ticks(): HTMLInputElement[] {
    return [...fixture.nativeElement.querySelectorAll('.shopping__tick')];
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ShoppingComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(ShoppingComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  describe('the list itself', () => {
    it('opens on the week being cooked, without asking which one', async () => {
      // The whole reason this is its own screen: a cook holding a basket has one hand.
      await showing();
      expect(text()).toContain('plain flour');
      expect(text()).toContain('200 g');
    });

    it('says there is nothing to buy rather than showing an empty screen', async () => {
      await showing(plan([]));
      expect(text()).toContain('Nothing to buy');
    });

    it('tells a cook with no plan how to get one', async () => {
      await showing(null);
      expect(text()).toContain('Nothing is planned yet');
    });

    it('says a failure is a failure', async () => {
      // An empty list and a failed request look identical unless one of them says so,
      // and "you have nothing to buy" is a bad thing to tell somebody untruthfully.
      backend
        .expectOne('/api/v1/plans/current')
        .flush({}, { status: 500, statusText: 'Server Error' });
      backend.expectOne('/api/v1/registry/categories').flush([]);
      await settle();
      expect(text()).toContain('Could not load your list');
    });
  });

  describe('marking things off', () => {
    it('ticks a line off', async () => {
      await showing();
      ticks()[0].click();
      await settle();

      const asked = backend.expectOne('/api/v1/plans/3/shopping/4');
      expect(asked.request.method).toBe('PUT');
      expect(asked.request.body).toEqual({ bought: true });
      asked.flush(
        plan([{ ingredient_id: 4, name: 'plain flour', quantity: '200 g', bought: true }]),
      );
      await settle();

      expect(ticks()[0].checked).toBe(true);
    });

    it('marks it before the answer comes back', async () => {
      /* A shop is where signal is worst, and a checkbox that waits for a round trip
         before it moves reads as broken. The request is still made and the answer still
         wins; this is only about what the cook sees while it is in flight. */
      await showing();
      ticks()[0].click();
      await settle();

      expect(ticks()[0].checked).toBe(true);
      backend.expectOne('/api/v1/plans/3/shopping/4').flush(plan());
    });

    it('puts it back when the request fails, rather than lying', async () => {
      await showing();
      ticks()[0].click();
      await settle();
      backend
        .expectOne('/api/v1/plans/3/shopping/4')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await settle();

      expect(ticks()[0].checked).toBe(false);
    });

    it('puts a line back on the list', async () => {
      await showing(
        plan([{ ingredient_id: 4, name: 'plain flour', quantity: '200 g', bought: true }]),
      );
      expect(ticks()[0].checked).toBe(true);

      ticks()[0].click();
      await settle();
      expect(backend.expectOne('/api/v1/plans/3/shopping/4').request.body).toEqual({
        bought: false,
      });
    });

    it('keeps what is bought on the list rather than making it disappear', async () => {
      // A cook rereads the list at the till to check what they picked up.
      await showing(
        plan([{ ingredient_id: 4, name: 'plain flour', quantity: '200 g', bought: true }]),
      );
      expect(text()).toContain('plain flour');
    });

    it('says how much is left to get', async () => {
      // A progress line, because the useful question in a shop is "am I nearly done".
      await showing(
        plan([
          { ingredient_id: 4, name: 'plain flour', quantity: '200 g', bought: true },
          { ingredient_id: 5, name: 'butter', quantity: '100 g', bought: false },
        ]),
      );
      expect(text()).toContain('1 of 2');
    });
  });

  describe('by aisle', () => {
    /* Forty items in a flat list is read line by line; a cook in a shop walks aisles. The
       categories are the registry's, so the list and the registry cannot come to disagree
       about where flour is (S2, ADR-067). */
    const LINES = [
      {
        ingredient_id: 4,
        name: 'plain flour',
        quantity: '200 g',
        magnitude: '200',
        unit: 'g',
        bought: false,
        category_slug: 'cereals-flour',
      },
      {
        ingredient_id: 5,
        name: 'carrot',
        quantity: '3',
        magnitude: '3',
        unit: '',
        bought: false,
        category_slug: 'vegetables-fresh',
      },
      {
        ingredient_id: 6,
        name: 'polenta',
        quantity: '500 g',
        magnitude: '500',
        unit: 'g',
        bought: false,
        category_slug: 'cereals-flour',
      },
      {
        ingredient_id: 7,
        name: 'yuzu',
        quantity: '2',
        magnitude: '2',
        unit: '',
        bought: false,
        category_slug: null,
      },
    ];

    const TREE = [
      { slug: 'vegetables', name: 'Vegetables', parent_slug: null },
      { slug: 'vegetables-fresh', name: 'Fresh vegetables', parent_slug: 'vegetables' },
      { slug: 'cereals', name: 'Cereal products', parent_slug: null },
      { slug: 'cereals-flour', name: 'Flour and starch', parent_slug: 'cereals' },
    ];

    async function shopping(): Promise<void> {
      backend.expectOne('/api/v1/plans/current').flush(plan(LINES));
      backend.expectOne('/api/v1/registry/categories').flush(TREE);
      await settle();
    }

    function headings(): string[] {
      return [...fixture.nativeElement.querySelectorAll('.shopping__aisle')].map((node: Element) =>
        node.textContent!.trim(),
      );
    }

    it('puts the list into aisles, named as the cook reads them', async () => {
      await shopping();
      expect(headings()).toEqual(['Flour and starch', 'Fresh vegetables', 'Anything else']);
    });

    it('keeps what belongs together together', async () => {
      await shopping();
      const first = fixture.nativeElement.querySelectorAll('.shopping__group')[0];
      expect(
        [...first.querySelectorAll('.shopping__name')].map((n: Element) => n.textContent),
      ).toEqual(['plain flour', 'polenta']);
    });

    it('names the leftovers rather than pretending they are somewhere', async () => {
      /* "Anything else" is the screen's word for the unplaced, not the server's. A server
         that invented a category could not be told apart from one that knew (ADR-067). */
      await shopping();
      const last = [...fixture.nativeElement.querySelectorAll('.shopping__group')].at(-1);
      expect(last.textContent).toContain('yuzu');
    });

    it('is still a list when nothing has been placed', async () => {
      backend.expectOne('/api/v1/plans/current').flush(plan());
      backend.expectOne('/api/v1/registry/categories').flush([]);
      await settle();
      expect(headings()).toEqual([]);
      expect(text()).toContain('plain flour');
    });

    it('shops on even where the tree cannot be read', async () => {
      // A heading is a convenience; the list is the thing a cook is holding.
      backend.expectOne('/api/v1/plans/current').flush(plan(LINES));
      backend
        .expectOne('/api/v1/registry/categories')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await settle();
      expect(text()).toContain('plain flour');
    });
  });

  describe('when the shopping is done', () => {
    /* A shopping list is a checklist, and the only thing a cook could do with a ticked
       line was go to the pantry and type it in again (S3). Putting it away and starting
       over are the two things that happen at the end of a shop (S4). */
    const BOUGHT = [
      {
        ingredient_id: 4,
        name: 'plain flour',
        quantity: '200 g',
        magnitude: '200',
        unit: 'g',
        bought: true,
      },
      {
        ingredient_id: 5,
        name: 'butter',
        quantity: '250 g',
        magnitude: '250',
        unit: 'g',
        bought: false,
      },
    ];

    it('offers nothing to put away until something is in the basket', async () => {
      await showing(plan([{ ...BOUGHT[1] }]));
      expect(fixture.nativeElement.querySelector('.shopping__stow')).toBeNull();
    });

    it('puts what was ticked on the shelf, one lot each', async () => {
      await showing(plan(BOUGHT));
      fixture.nativeElement.querySelector('.shopping__stow').click();
      await settle();

      const added = backend.expectOne('/api/v1/pantry');
      expect(added.request.body).toEqual({ ingredient_id: 4, magnitude: '200', unit: 'g' });
      added.flush({ id: 1 });
      await settle();

      // And the line it came from is no longer in the basket: it is in the kitchen.
      const cleared = backend.expectOne('/api/v1/plans/3/shopping/4');
      expect(cleared.request.body).toEqual({ bought: false });
      cleared.flush(plan([{ ...BOUGHT[0], bought: false }, BOUGHT[1]]));
      await settle();
    });

    it('takes everything back out of the basket without stocking anything', async () => {
      await showing(plan(BOUGHT));
      fixture.nativeElement.querySelector('.shopping__clear').click();
      await settle();

      backend.expectNone('/api/v1/pantry');
      const cleared = backend.expectOne('/api/v1/plans/3/shopping/4');
      expect(cleared.request.body).toEqual({ bought: false });
      cleared.flush(plan([{ ...BOUGHT[0], bought: false }, BOUGHT[1]]));
      await settle();
    });
  });
});
