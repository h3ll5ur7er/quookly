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
    spoken_for: null,
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

  async function answer(shelf: object[]): Promise<void> {
    backend.expectOne('/api/v1/pantry').flush(shelf);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function names(): string[] {
    return [...fixture.nativeElement.querySelectorAll('.pantry__name span:first-child')].map(
      (node: Element) => node.textContent!.trim(),
    );
  }

  function click(label: string): void {
    const buttons: HTMLButtonElement[] = [...fixture.nativeElement.querySelectorAll('button')];
    buttons.find((one) => one.textContent?.includes(label))!.click();
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

  it('asks for the shelf, and for the shelf only', () => {
    /* It used to ask for "what is pressing" as well and print it above the same lots it
       was about, so a shelf with one thing on it said everything twice (N1). What is
       pressing is a property of the lots the shelf already carries. */
    backend.expectOne('/api/v1/pantry').flush([]);
    backend.expectNone('/api/v1/pantry/using-soon');
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
    await answer([
      entry({
        freshness: 'soon',
        lots: [lot({ expires_on: '2026-09-03', days_remaining: 1, freshness: 'soon' })],
      }),
    ]);
    expect(text()).toContain('tomorrow');
  });

  it('leads with what is past its date rather than hiding it', async () => {
    await answer([
      entry({
        freshness: 'past',
        lots: [lot({ expires_on: '2026-08-19', days_remaining: -2, freshness: 'past' })],
      }),
    ]);
    expect(text()).toContain('2 days ago');
  });

  it('puts what wants eating first, which is what this screen is for', async () => {
    await answer([
      entry({ ingredient_id: 1, name: 'plain flour' }),
      entry({
        ingredient_id: 2,
        name: 'soured cream',
        freshness: 'soon',
        lots: [lot({ id: 2, days_remaining: 2, expires_on: '2026-08-30', freshness: 'soon' })],
      }),
      entry({
        ingredient_id: 3,
        name: 'chard',
        freshness: 'past',
        lots: [lot({ id: 3, days_remaining: -1, expires_on: '2026-08-27', freshness: 'past' })],
      }),
    ]);
    expect(names()).toEqual(['chard', 'soured cream', 'plain flour']);
  });

  it('goes back to the alphabet for a cook looking for something', async () => {
    await answer([
      entry({ ingredient_id: 1, name: 'plain flour' }),
      entry({
        ingredient_id: 3,
        name: 'chard',
        freshness: 'past',
        lots: [lot({ id: 3, days_remaining: -1, expires_on: '2026-08-27', freshness: 'past' })],
      }),
    ]);
    click('A–Z');
    expect(names()).toEqual(['chard', 'plain flour']);
  });

  it('grades how pressing a packet is, rather than only wording it', async () => {
    // "Use within 2 days" and "use within 20 days" differed in nothing but the words (N2).
    await answer([
      entry({
        lots: [
          lot({ id: 1, days_remaining: 2, expires_on: '2026-08-30', freshness: 'soon' }),
          lot({ id: 2, days_remaining: 20, expires_on: '2026-09-17', freshness: 'soon' }),
        ],
      }),
    ]);
    const bands = [...fixture.nativeElement.querySelectorAll('.pantry__lot')].map((node: Element) =>
      [...node.classList].find((one) => one.startsWith('pantry__lot--')),
    );
    expect(bands).toEqual(['pantry__lot--now', 'pantry__lot--later']);
  });

  it('says nothing about urgency when nothing is urgent', async () => {
    await answer([entry()]);
    expect(fixture.nativeElement.querySelector('.pantry__urgency')).toBeNull();
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
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(text()).not.toContain('Nothing in your pantry yet');
  });

  it('offers a way to add stock', async () => {
    await answer([]);
    expect(fixture.nativeElement.querySelector('a[href="/pantry/add"]')).not.toBeNull();
  });

  it('says how much of a total a planned meal has claimed', async () => {
    /* The total stays what is in the cupboard — planning reserves rather than deducts.
       But "how much can I use today" is a different question, and a cook who uses the lot
       leaves Thursday short with nothing having warned them. */
    await answer([entry({ spoken_for: '200 g' })]);
    expect(text()).toContain('200 g');
    expect(text()).toContain('is planned for a meal');
  });

  it('says nothing where nothing has been claimed', async () => {
    await answer([entry()]);
    expect(text()).not.toContain('is planned for a meal');
  });
});
