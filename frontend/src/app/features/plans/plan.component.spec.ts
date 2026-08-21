import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { PlanComponent } from './plan.component';

function slot(overrides: object = {}): object {
  return {
    id: 5,
    on_date: '2026-08-24',
    meal: 'dinner',
    recipe_id: 1,
    recipe_title: 'Pancakes',
    attendee_ids: [2],
    attendees: ['Ana'],
    factor: '1',
    sizing: 'to_the_table',
    suitability: null,
    ...overrides,
  };
}

function week(overrides: object = {}): object {
  return {
    id: 3,
    starts_on: '2026-08-24',
    ends_on: '2026-08-26',
    slots: [slot()],
    shopping: [{ ingredient_id: 9, name: 'plain flour', quantity: '200 g' }],
    ...overrides,
  };
}

describe('PlanComponent', () => {
  let fixture: ComponentFixture<PlanComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function answer(plan: object): Promise<void> {
    backend.expectOne('/api/v1/plans/3').flush(plan);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [PlanComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: new Map([['id', '3']]) } } },
      ],
    });
    fixture = TestBed.createComponent(PlanComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the plan named in the route', () => {
    backend.expectOne('/api/v1/plans/3').flush(week());
  });

  it('lays out every day of the period, gaps included', async () => {
    /* The gaps are the point. A list of only what is planned reads as a finished week;
       a row per day shows a cook where Tuesday still is. */
    await answer(week());
    expect(text()).toContain('Monday');
    expect(text()).toContain('Tuesday');
    expect(text()).toContain('Wednesday');
  });

  it('makes an empty day the way to fill it', async () => {
    await answer(week());
    const empty = fixture.nativeElement.querySelector('.week__empty');
    expect(empty).not.toBeNull();
    expect(empty.getAttribute('href')).toContain('/plans/3/meal');
    expect(empty.getAttribute('href')).toContain('2026-08-25');
  });

  it('names what is planned and who is at it', async () => {
    await answer(week());
    expect(text()).toContain('Pancakes');
    expect(text()).toContain('Ana');
  });

  it('says nobody has been named rather than pretending nobody is coming', async () => {
    await answer(
      week({ slots: [slot({ attendee_ids: [], attendees: [], sizing: 'as_written' })] }),
    );
    expect(text()).toContain('Nobody said yet');
  });

  it('warns when a recipe would not say how many it feeds', async () => {
    /* One batch is right often enough to be worth doing, and wrong often enough that
       saying nothing would leave somebody feeding four of the six they invited. */
    await answer(week({ slots: [slot({ sizing: 'unscalable' })] }));
    expect(text()).toContain('does not say how many it serves');
  });

  it('says nothing about sizing when the meal was sized to its table', async () => {
    await answer(week());
    expect(text()).not.toContain('does not say how many it serves');
  });

  it('marks a meal somebody at it cannot eat', async () => {
    await answer(
      week({
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
      }),
    );
    expect(fixture.nativeElement.querySelector('.badge--unsuitable')).not.toBeNull();
  });

  it('shows the shopping list the week comes to', async () => {
    await answer(week());
    expect(text()).toContain('plain flour');
    expect(text()).toContain('200 g');
  });

  it('says so when there is nothing to buy, rather than showing an empty box', async () => {
    await answer(week({ shopping: [] }));
    expect(text()).toContain('Nothing to buy');
  });

  it('offers a way to add a meal', async () => {
    await answer(week());
    expect(fixture.nativeElement.querySelector('a.action').getAttribute('href')).toBe(
      '/plans/3/meal',
    );
  });

  it('says so when the plan is not there', async () => {
    backend.expectOne('/api/v1/plans/3').flush({}, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('No such plan');
  });

  it('marks nothing when everybody at the meal can eat it', async () => {
    /* A tick on every meal that is fine drowns the one that is not, and a mark that is
       always on stops being read. */
    await answer(week({ slots: [slot({ suitability: { outcome: 'suitable', findings: [] } })] }));
    expect(fixture.nativeElement.querySelector('.badge')).toBeNull();
  });
});
