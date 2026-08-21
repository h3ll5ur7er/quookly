import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { MealComponent } from './meal.component';

const RECIPES = [
  {
    id: 1,
    title: 'Pancakes',
    summary: null,
    yield_quantity: {},
    serves: null,
    visibility: 'private',
    suitability: null,
  },
  {
    id: 2,
    title: 'Soup',
    summary: null,
    yield_quantity: {},
    serves: null,
    visibility: 'private',
    suitability: null,
  },
];

const HOUSEHOLD = [
  { id: 7, name: 'Ana', age_band: 'adult', appetite: '1', constraints: [] },
  { id: 8, name: 'Mira', age_band: 'child', appetite: '0.6', constraints: [] },
];

function slot(overrides: object = {}): object {
  return {
    id: 5,
    on_date: '2026-08-24',
    meal: 'dinner',
    recipe_id: 1,
    recipe_title: 'Pancakes',
    attendee_ids: [7],
    attendees: ['Ana'],
    factor: '1',
    sizing: 'to_the_table',
    suitability: null,
    ...overrides,
  };
}

const WEEK = {
  id: 3,
  starts_on: '2026-08-24',
  ends_on: '2026-08-30',
  slots: [slot()],
  shopping: [],
};

describe('MealComponent', () => {
  let fixture: ComponentFixture<MealComponent>;
  let backend: HttpTestingController;
  let navigated: ReturnType<typeof vi.spyOn>;

  function field(id: string): HTMLInputElement | HTMLSelectElement {
    return fixture.nativeElement.querySelector(`#${id}`);
  }

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function button(label: string): HTMLButtonElement | null {
    const found = [...fixture.nativeElement.querySelectorAll('button')].find((one) =>
      (one as HTMLButtonElement).textContent?.includes(label),
    );
    return (found as HTMLButtonElement) ?? null;
  }

  /** Open the editor at an address, then let the three requests it makes answer. */
  async function open(query: Record<string, string>, plan: object = WEEK): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [MealComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: new Map([['id', '3']]),
              queryParamMap: new Map(Object.entries(query)),
            },
          },
        },
      ],
    });
    navigated = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(MealComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    backend.expectOne('/api/v1/plans/3').flush(plan);
    backend.expectOne('/api/v1/recipes').flush(RECIPES);
    backend.expectOne('/api/v1/eaters').flush(HOUSEHOLD);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  afterEach(() => backend.verify());

  it('opens on the day and meal it was pointed at', async () => {
    await open({ on: '2026-08-26', meal: 'lunch' });
    expect((field('on_date') as HTMLInputElement).value).toBe('2026-08-26');
    expect((field('meal') as HTMLSelectElement).value).toBe('lunch');
  });

  it('opens an existing meal filled in', async () => {
    /* The same address opens the slot that is there or makes a new one, because that is
       how the API keys a slot — there is no state where the screen has to decide which. */
    await open({ on: '2026-08-24', meal: 'dinner' });
    expect((field('recipe_id') as HTMLSelectElement).value).toBe('1');
    expect(
      (fixture.nativeElement.querySelector('.meal__person input') as HTMLInputElement).checked,
    ).toBe(true);
  });

  it('opens an empty day empty', async () => {
    await open({ on: '2026-08-26', meal: 'dinner' });
    expect((field('recipe_id') as HTMLSelectElement).value).toBe('');
    expect(
      (fixture.nativeElement.querySelector('.meal__person input') as HTMLInputElement).checked,
    ).toBe(false);
  });

  it('offers a meal without a dish, because a slot can hold its place', async () => {
    await open({ on: '2026-08-26' });
    expect(text()).toContain('Not decided yet');
  });

  it('shows how much each person eats beside their name', async () => {
    /* The number the yield actually follows from. A tick list of names alone would make
       "scaled to your table" look like a head count. */
    await open({ on: '2026-08-26' });
    expect(text()).toContain('0.6');
    expect(text()).toContain('portions');
  });

  it('states the meal whole, dish and guests together', async () => {
    await open({ on: '2026-08-26', meal: 'lunch' });
    (field('recipe_id') as HTMLSelectElement).value = '2';
    field('recipe_id').dispatchEvent(new Event('change'));
    fixture.nativeElement.querySelectorAll('.meal__person input')[1].click();
    await fixture.whenStable();

    button('Save this meal')!.click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/plans/3/slots');
    expect(sent.request.method).toBe('PUT');
    expect(sent.request.body).toEqual({
      on_date: '2026-08-26',
      meal: 'lunch',
      recipe_id: 2,
      attendee_ids: [8],
    });
    sent.flush(WEEK);
    await fixture.whenStable();
    expect(navigated).toHaveBeenCalledWith('/plans/3');
  });

  it('sends no recipe when none was chosen, rather than a zero', async () => {
    await open({ on: '2026-08-26', meal: 'lunch' });
    button('Save this meal')!.click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/plans/3/slots');
    expect(sent.request.body.recipe_id).toBeNull();
    sent.flush(WEEK);
  });

  it('takes an existing meal off the plan', async () => {
    await open({ on: '2026-08-24', meal: 'dinner' });

    button('Take this meal off')!.click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/plans/3/slots/5');
    expect(sent.request.method).toBe('DELETE');
    sent.flush(WEEK);
  });

  it('offers no way to remove a meal that was never put down', async () => {
    await open({ on: '2026-08-26', meal: 'lunch' });
    expect(button('Take this meal off')).toBeNull();
  });

  it('shows the verdict for a meal somebody at it cannot eat', async () => {
    const judged = {
      ...WEEK,
      slots: [
        slot({
          suitability: {
            outcome: 'unsuitable',
            findings: [
              {
                eater: 'Mira',
                ingredient: 'plain flour',
                severity: 'medical',
                allergen: 'gluten',
                avoidable: false,
                unknown: false,
              },
            ],
          },
        }),
      ],
    };
    await open({ on: '2026-08-24', meal: 'dinner' }, judged);

    expect(text()).toContain('Mira');
  });

  it('says so when saving fails, and lets the cook try again', async () => {
    await open({ on: '2026-08-26', meal: 'lunch' });
    button('Save this meal')!.click();
    await fixture.whenStable();
    backend
      .expectOne('/api/v1/plans/3/slots')
      .flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(button('Save this meal')!.disabled).toBe(false);
  });

  describe('moving to another day', () => {
    async function moveTo(day: string): Promise<void> {
      const input = field('on_date') as HTMLInputElement;
      input.value = day;
      input.dispatchEvent(new Event('input'));
      await fixture.whenStable();
      fixture.detectChanges();
    }

    it('shows that day rather than the one you came from', async () => {
      /* A reactive form's value is not a signal, so a `computed` over it is evaluated
         once and cached. This screen showed the wrong day and, worse, saved to it. */
      await open({ on: '2026-08-26', meal: 'dinner' });

      await moveTo('2026-08-24');

      expect((field('recipe_id') as HTMLSelectElement).value).toBe('1');
      expect(button('Take this meal off')).not.toBeNull();
    });

    it('empties the form when that day holds nothing', async () => {
      await open({ on: '2026-08-24', meal: 'dinner' });

      await moveTo('2026-08-27');

      expect((field('recipe_id') as HTMLSelectElement).value).toBe('');
      expect(button('Take this meal off')).toBeNull();
    });

    it('saves to the day it is showing', async () => {
      await open({ on: '2026-08-26', meal: 'dinner' });
      await moveTo('2026-08-27');

      button('Save this meal')!.click();
      await fixture.whenStable();

      const sent = backend.expectOne('/api/v1/plans/3/slots');
      expect(sent.request.body.on_date).toBe('2026-08-27');
      sent.flush(WEEK);
    });

    it('removes the meal it is showing, not the one it opened on', async () => {
      await open({ on: '2026-08-26', meal: 'dinner' });
      await moveTo('2026-08-24');

      button('Take this meal off')!.click();
      await fixture.whenStable();

      const sent = backend.expectOne('/api/v1/plans/3/slots/5');
      expect(sent.request.method).toBe('DELETE');
      sent.flush(WEEK);
    });
  });

  it('offers nothing to fill in until it knows what it is showing', async () => {
    /* The form used to be typeable before the plan arrived, and filling it in from the
       plan then wiped what had been typed. Found end to end: a meal saved without the
       recipe somebody had just chosen. */
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [MealComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { paramMap: new Map([['id', '3']]), queryParamMap: new Map() },
          },
        },
      ],
    });
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(MealComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('#recipe_id')).toBeNull();
    expect(text()).toContain('Loading…');

    backend.expectOne('/api/v1/plans/3').flush(WEEK);
    backend.expectOne('/api/v1/recipes').flush(RECIPES);
    backend.expectOne('/api/v1/eaters').flush(HOUSEHOLD);
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('#recipe_id')).not.toBeNull();
  });
});
