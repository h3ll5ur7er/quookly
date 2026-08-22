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
});
