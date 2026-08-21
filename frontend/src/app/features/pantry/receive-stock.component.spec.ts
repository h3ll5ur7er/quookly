import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { ReceiveStockComponent } from './receive-stock.component';

const FLOUR = { id: 3, slug: 'plain-flour', name: 'plain flour', kind: 'powder' };
const MILK = { id: 4, slug: 'whole-milk', name: 'whole milk', kind: 'liquid' };

const PREFERENCES = [
  { kind: 'powder', unit: 'kg', chosen: true },
  { kind: 'liquid', unit: 'dl', chosen: true },
  { kind: 'solid', unit: 'g', chosen: false },
  { kind: 'countable', unit: 'piece', chosen: false },
];

describe('ReceiveStockComponent', () => {
  let fixture: ComponentFixture<ReceiveStockComponent>;
  let backend: HttpTestingController;
  /** Stubbed for every test: a real navigation would look for a route the bare test
      router does not have, and fail after the assertion had already passed. */
  let navigated: ReturnType<typeof vi.spyOn>;

  function field(id: string): HTMLInputElement | HTMLSelectElement {
    return fixture.nativeElement.querySelector(`#${id}`);
  }

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function type(id: string, value: string): Promise<void> {
    const input = field(id);
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  /** Type an ingredient name and let the registry answer, as a cook picking one does. */
  async function pick(name: string, found: object[]): Promise<void> {
    await type('ingredient', name);
    backend.expectOne((request) => request.url === '/api/v1/ingredients').flush(found);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ReceiveStockComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    navigated = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(ReceiveStockComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    backend.expectOne('/api/v1/preferences/units').flush(PREFERENCES);
    await fixture.whenStable();
    fixture.detectChanges();
  });

  afterEach(() => backend.verify());

  it('offers the units this kind of ingredient is measured in', async () => {
    await pick('plain flour', [FLOUR]);
    const options = [...field('unit').querySelectorAll('option')].map((o) => o.textContent?.trim());
    expect(options).toContain('g');
    expect(options).not.toContain('ml');
  });

  it('starts on the unit this cook reads that kind in', async () => {
    await pick('plain flour', [FLOUR]);
    expect((field('unit') as HTMLSelectElement).value).toBe('kg');
  });

  it('changes the units when the ingredient changes kind', async () => {
    await pick('plain flour', [FLOUR]);
    await pick('whole milk', [MILK]);
    expect((field('unit') as HTMLSelectElement).value).toBe('dl');
  });

  it('refuses a name the registry does not know rather than sending it', async () => {
    await pick('unicorn tears', []);
    await type('magnitude', '500');
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('Pick one from the list');
    backend.expectNone('/api/v1/pantry');
  });

  it('sends what was entered, and goes back to the pantry', async () => {
    await pick('plain flour', [FLOUR]);
    await type('magnitude', '2');
    await type('expires_on', '2026-12-01');
    await type('note', 'Coop');
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/pantry');
    expect(sent.request.body).toEqual({
      ingredient_id: 3,
      magnitude: '2',
      unit: 'kg',
      expires_on: '2026-12-01',
      note: 'Coop',
    });
    sent.flush({}, { status: 201, statusText: 'Created' });
    await fixture.whenStable();
    expect(navigated).toHaveBeenCalledWith('/pantry');
  });

  it('leaves an unanswered date absent rather than sending an empty one', async () => {
    await pick('plain flour', [FLOUR]);
    await type('magnitude', '2');
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/pantry');
    expect(sent.request.body.expires_on).toBeNull();
    expect(sent.request.body.note).toBeNull();
    sent.flush({}, { status: 201, statusText: 'Created' });
  });

  it('says so when saving fails, and lets the cook try again', async () => {
    await pick('plain flour', [FLOUR]);
    await type('magnitude', '2');
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();
    backend.expectOne('/api/v1/pantry').flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('button[type="submit"]').disabled).toBe(false);
  });
});
