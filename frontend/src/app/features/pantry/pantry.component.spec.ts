import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { PantryComponent } from './pantry.component';

function lot(overrides: object = {}): object {
  return {
    id: 7,
    magnitude: '500',
    unit: 'g',
    quantity: '500 g',
    expires_on: null,
    days_remaining: null,
    freshness: 'undated',
    note: null,
    ...overrides,
  };
}

function entry(overrides: object = {}): object {
  return {
    ingredient_id: 3,
    slug: 'plain-flour',
    name: 'plain flour',
    kind: 'powder',
    total: '500 g',
    freshness: 'undated',
    lots: [lot()],
    ...overrides,
  };
}

describe('PantryComponent', () => {
  let fixture: ComponentFixture<PantryComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function answer(shelf: object[], pressing: object[] = []): Promise<void> {
    backend.expectOne('/api/v1/pantry').flush(shelf);
    backend.expectOne('/api/v1/pantry/using-soon').flush(pressing);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [PantryComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(PantryComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the shelf and for what is pressing', () => {
    backend.expectOne('/api/v1/pantry').flush([]);
    backend.expectOne('/api/v1/pantry/using-soon').flush([]);
  });

  it('names what the cook has, and how much of it', async () => {
    await answer([entry()]);
    expect(text()).toContain('plain flour');
    expect(text()).toContain('500 g');
  });

  it('shows the lots rather than only a total, because dates belong to packets', async () => {
    await answer([
      entry({
        total: '1 kg',
        lots: [
          lot({ id: 1, quantity: '500 g', expires_on: '2026-09-03' }),
          lot({ id: 2, quantity: '500 g', expires_on: '2026-12-01' }),
        ],
      }),
    ]);
    expect(fixture.nativeElement.querySelector('a[href="/pantry/lots/1"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('a[href="/pantry/lots/2"]')).not.toBeNull();
  });

  it('says how soon something wants using, in words rather than in a count', async () => {
    await answer(
      [],
      [
        entry({
          freshness: 'soon',
          lots: [lot({ expires_on: '2026-09-03', days_remaining: 1, freshness: 'soon' })],
        }),
      ],
    );
    expect(text()).toContain('tomorrow');
  });

  it('leads with what is past its date rather than hiding it', async () => {
    await answer(
      [],
      [
        entry({
          freshness: 'past',
          lots: [lot({ expires_on: '2026-08-19', days_remaining: -2, freshness: 'past' })],
        }),
      ],
    );
    expect(text()).toContain('2 days ago');
  });

  it('says nothing about urgency when nothing is urgent', async () => {
    await answer([entry()]);
    expect(fixture.nativeElement.querySelector('[aria-labelledby="usingSoon"]')).toBeNull();
  });

  it('shows no total where the lots have no honest sum, rather than inventing one', async () => {
    await answer([
      entry({
        name: 'egg',
        total: null,
        lots: [lot({ id: 1, quantity: '6' }), lot({ id: 2, quantity: '200 g' })],
      }),
    ]);
    expect(text()).toContain('6');
    expect(text()).toContain('200 g');
  });

  it('explains an empty pantry rather than showing a blank screen', async () => {
    await answer([]);
    expect(text()).toContain('Nothing in your pantry yet');
  });

  it('reports a failure rather than claiming the pantry is empty', async () => {
    backend.expectOne('/api/v1/pantry').flush({}, { status: 500, statusText: 'Server Error' });
    backend.expectOne('/api/v1/pantry/using-soon').flush([]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(text()).not.toContain('Nothing in your pantry yet');
  });

  it('offers a way to add stock', async () => {
    await answer([]);
    expect(fixture.nativeElement.querySelector('a[href="/pantry/add"]')).not.toBeNull();
  });
});
