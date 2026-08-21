import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { LotComponent } from './lot.component';

const SHELF = [
  {
    ingredient_id: 3,
    slug: 'plain-flour',
    name: 'plain flour',
    kind: 'powder',
    total: '1.5 kg',
    freshness: 'soon',
    lots: [
      {
        id: 7,
        magnitude: '500',
        unit: 'g',
        quantity: '500 g',
        expires_on: '2026-08-24',
        days_remaining: 3,
        freshness: 'soon',
        note: 'Coop',
      },
      {
        id: 8,
        magnitude: '1',
        unit: 'kg',
        quantity: '1 kg',
        expires_on: null,
        days_remaining: null,
        freshness: 'undated',
        note: null,
      },
    ],
  },
];

describe('LotComponent', () => {
  let fixture: ComponentFixture<LotComponent>;
  let backend: HttpTestingController;
  let navigated: ReturnType<typeof vi.spyOn>;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function button(label: string): HTMLButtonElement | null {
    const found = [...fixture.nativeElement.querySelectorAll('button')].find((one) =>
      (one as HTMLButtonElement).textContent?.includes(label),
    );
    return (found as HTMLButtonElement) ?? null;
  }

  async function press(label: string): Promise<void> {
    button(label)!.click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function type(id: string, value: string): Promise<void> {
    const input = fixture.nativeElement.querySelector(`#${id}`) as HTMLInputElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function open(lotId: string): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [LotComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: new Map([['id', lotId]]) } },
        },
      ],
    });
    navigated = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LotComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    backend.expectOne('/api/v1/pantry').flush(SHELF);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  afterEach(() => backend.verify());

  it('names the packet rather than only the ingredient', async () => {
    await open('7');
    expect(text()).toContain('plain flour');
    expect(text()).toContain('Coop');
  });

  it('starts from what is recorded, so a correction is an edit and not a re-entry', async () => {
    await open('7');
    expect((fixture.nativeElement.querySelector('#magnitude') as HTMLInputElement).value).toBe(
      '500',
    );
  });

  it('shows the unit beside the number, because the number alone means nothing', async () => {
    await open('7');
    expect(text()).toContain('g');
  });

  it('restates what is there rather than sending a difference', async () => {
    await open('7');
    await type('magnitude', '300');
    await press('Save');
    const sent = backend.expectOne('/api/v1/pantry/lots/7');
    expect(sent.request.method).toBe('PATCH');
    expect(sent.request.body).toEqual({ magnitude: '300' });
    sent.flush(SHELF[0]);
    await fixture.whenStable();
    expect(navigated).toHaveBeenCalledWith('/pantry');
  });

  it('asks why before recording waste, because the reason is the point of asking', async () => {
    await open('7');
    await press('threw some away');
    expect(fixture.nativeElement.querySelector('#reason')).not.toBeNull();
  });

  it('records waste as its own act, not as an adjustment', async () => {
    await open('7');
    await press('threw some away');
    await type('wasted', '200');
    await press('Record');
    const sent = backend.expectOne('/api/v1/pantry/lots/7/waste');
    expect(sent.request.method).toBe('POST');
    expect(sent.request.body).toEqual({ magnitude: '200', reason: 'spoiled', note: null });
    sent.flush(SHELF[0]);
  });

  it('offers only one filled action at a time', async () => {
    await open('7');
    await press('threw some away');
    expect(button('Save')).toBeNull();
  });

  it('lets the cook back out of recording waste', async () => {
    await open('7');
    await press('threw some away');
    await press('Cancel');
    expect(button('Save')).not.toBeNull();
  });

  it('removes an entry that was a mistake, without calling it waste', async () => {
    await open('7');
    await press('never here');
    const sent = backend.expectOne('/api/v1/pantry/lots/7');
    expect(sent.request.method).toBe('DELETE');
    sent.flush(null, { status: 204, statusText: 'No Content' });
    await fixture.whenStable();
    expect(navigated).toHaveBeenCalledWith('/pantry');
  });

  it('explains why a packet with waste against it cannot simply be removed', async () => {
    await open('7');
    await press('never here');
    backend
      .expectOne('/api/v1/pantry/lots/7')
      .flush({ detail: 'no' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('already recorded waste');
  });

  it('says so when the packet is not there rather than showing an empty form', async () => {
    await open('99');
    expect(text()).toContain('No such stock');
    expect(fixture.nativeElement.querySelector('#magnitude')).toBeNull();
  });
});
