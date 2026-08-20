import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { HouseholdComponent } from './household.component';

const MIRA = {
  id: 1,
  name: 'Mira',
  age_band: 'child',
  appetite: '0.6',
  constraints: [{ allergen: 'peanuts', ingredient_slug: null, severity: 'medical' }],
};

const ANA = { id: 2, name: 'Ana', age_band: 'adult', appetite: '1', constraints: [] };

describe('HouseholdComponent', () => {
  let fixture: ComponentFixture<HouseholdComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function answer(household: object[], summary: object): Promise<void> {
    backend.expectOne('/api/v1/eaters').flush(household);
    backend.expectOne('/api/v1/eaters/summary').flush(summary);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [HouseholdComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(HouseholdComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the household and what it adds up to', () => {
    backend.expectOne('/api/v1/eaters').flush([]);
    backend.expectOne('/api/v1/eaters/summary').flush({ people: 0, servings: '0' });
  });

  it('shows everyone it finds', async () => {
    await answer([MIRA, ANA], { people: 2, servings: '1.6' });
    expect(text()).toContain('Mira');
    expect(text()).toContain('Ana');
  });

  it('says how many servings the household comes to, not just how many people', async () => {
    await answer([MIRA, ANA], { people: 2, servings: '1.6' });
    expect(text()).toContain('1.6');
  });

  it('names what somebody avoids rather than showing a code', async () => {
    await answer([MIRA], { people: 1, servings: '0.6' });
    expect(text()).toContain('Peanuts');
  });

  it('carries a word beside the colour, because a warning must not be colour alone', async () => {
    await answer([MIRA], { people: 1, servings: '0.6' });
    expect(text()).toContain('never');
  });

  it('offers a way to edit each person', async () => {
    await answer([MIRA], { people: 1, servings: '0.6' });
    expect(fixture.nativeElement.querySelector('a[href="/household/1"]')).not.toBeNull();
  });

  it('offers a way to add somebody', async () => {
    await answer([], { people: 0, servings: '0' });
    expect(fixture.nativeElement.querySelector('a[href="/household/new"]')).not.toBeNull();
  });

  it('explains an empty household rather than showing a blank screen', async () => {
    await answer([], { people: 0, servings: '0' });
    expect(text()).toContain('Nobody here yet');
  });

  it('reports a failure rather than claiming the household is empty', async () => {
    backend.expectOne('/api/v1/eaters').flush({}, { status: 500, statusText: 'Server Error' });
    backend.expectOne('/api/v1/eaters/summary').flush({ people: 0, servings: '0' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(text()).not.toContain('Nobody here yet');
  });
});
