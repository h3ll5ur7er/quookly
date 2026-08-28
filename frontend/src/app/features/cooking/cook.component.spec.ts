import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { CookComponent } from './cook.component';

function line(ingredient: string, display: string) {
  return {
    ingredient,
    quantity: { magnitude: display.split(' ')[0], unit: 'g', display },
    preparation: null,
    optional: false,
  };
}

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    plan_slot_id: 3,
    title: 'Shortbread',
    yield_quantity: { magnitude: '4', unit: 'serving', display: '4 servings' },
    serves: null,
    sizing: 'to_the_table',
    suitability: null,
    mise_en_place: [
      { preparation: 'softened', lines: [line('unsalted butter', '200 g')] },
      { preparation: null, lines: [line('plain flour', '300 g')] },
    ],
    ahead: [],
    steps: [
      {
        position: 0,
        instruction: 'Cream the butter.',
        duration_seconds: 300,
        temperature_celsius: null,
        attention: 'hands_on',
        lines: [line('unsalted butter', '200 g')],
        timer: null,
      },
      {
        position: 1,
        instruction: 'Bake until pale gold.',
        duration_seconds: 2400,
        temperature_celsius: 160,
        attention: 'waiting',
        lines: [],
        timer: null,
      },
    ],
    at_step: null,
    started_at: '2026-08-24T18:00:00Z',
    finished_at: null,
    outcome: null,
    ...overrides,
  };
}

describe('CookComponent', () => {
  let fixture: ComponentFixture<CookComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function open(body: Record<string, unknown> = session()): Promise<void> {
    backend.expectOne('/api/v1/cooking/sessions/7').flush(body);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [CookComponent],
      providers: [
        provideZonelessChangeDetection(),
        // Giving up navigates back to the plan, so the route has to exist to be reached.
        provideRouter([{ path: 'plans', children: [] }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: new Map([['id', '7']]) } } },
      ],
    });
    fixture = TestBed.createComponent(CookComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  describe('getting ready', () => {
    it('opens on the prep list rather than on step one', async () => {
      await open();
      expect(text()).toContain('Get everything ready');
    });

    it('groups the prep by the work it wants', async () => {
      await open();
      const groups = fixture.nativeElement.querySelectorAll('.cook__group-title');
      expect([...groups].map((node: Element) => node.textContent!.trim())).toEqual([
        'softened',
        'Weigh out',
      ]);
    });

    it('carries the quantities to weigh', async () => {
      await open();
      expect(text()).toContain('300 g');
    });

    it('ticks something off without asking the server', async () => {
      // A prep list is a glance at what is left, not a fact about the meal. Nothing is
      // sent, so `backend.verify()` in afterEach is the assertion.
      await open();
      const row = fixture.nativeElement.querySelector('.cook__tick input');
      row.click();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.cook__tick--done')).not.toBeNull();
    });

    it('says when the meal could not be sized to the table', async () => {
      // Before starting, not when the tray comes out short.
      await open(session({ sizing: 'as_written' }));
      expect(text()).toContain('Nobody was listed at this meal');
    });

    it('puts work for the day before above the prep list', async () => {
      await open(
        session({
          ahead: [
            {
              position: 0,
              instruction: 'Soak the beans overnight.',
              duration_seconds: 28800,
              temperature_celsius: null,
              attention: 'ahead',
              lines: [],
              timer: null,
            },
          ],
        }),
      );
      expect(text()).toContain('Before today');
      expect(text()).toContain('Soak the beans overnight.');
    });

    it('starts cooking at the first step', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();

      const moved = backend.expectOne('/api/v1/cooking/sessions/7/step');
      expect(moved.request.body).toEqual({ position: 0 });
      moved.flush(session({ at_step: 0 }));
    });
  });

  describe('a step', () => {
    async function atStep(position: number): Promise<void> {
      await open(session({ at_step: position }));
    }

    it('fills the screen with the instruction', async () => {
      await atStep(0);
      expect(fixture.nativeElement.querySelector('.cook__instruction').textContent).toContain(
        'Cream the butter.',
      );
    });

    it('says where the cook is', async () => {
      await atStep(1);
      expect(fixture.nativeElement.querySelector('.cook__place').textContent).toContain('2');
    });

    it('shows the quantities the step asks for', async () => {
      // So nobody has to scroll back to the ingredient list with their hands in a bowl.
      await atStep(0);
      expect(fixture.nativeElement.querySelector('.cook__lines').textContent).toContain('200 g');
    });

    it('shows the oven temperature where there is one, at the weight the clock has', async () => {
      // On a baking step 160 °C is as much of the instruction as 40:00 is, and it was a
      // small muted chip beside a very large number (C2).
      await atStep(1);
      const heat = fixture.nativeElement.querySelector('.cook__heat');
      expect(heat.querySelector('.cook__degrees').textContent.trim()).toBe('160');
      expect(heat.textContent).toContain('°C');
    });

    it('marks the step a cook can walk away from', async () => {
      await atStep(1);
      expect(text()).toContain('you can walk away');
    });

    it('offers a timer for a step that has a duration', async () => {
      await atStep(0);
      expect(fixture.nativeElement.querySelector('app-timer')).not.toBeNull();
    });

    it('starts a timer on the server rather than in the tab', async () => {
      await atStep(0);
      fixture.nativeElement.querySelector('.timer__button--primary').click();
      backend.expectOne('/api/v1/cooking/sessions/7/timers/0/started').flush(session());
    });

    it('goes on to the next step', async () => {
      await atStep(0);
      fixture.nativeElement.querySelector('.cook__move--go').click();

      const moved = backend.expectOne('/api/v1/cooking/sessions/7/step');
      expect(moved.request.body).toEqual({ position: 1 });
      moved.flush(session({ at_step: 1 }));
    });

    it('goes back from the first step to the prep list', async () => {
      // A real place to return to: a cook goes back to see what else wants chopping.
      await atStep(0);
      fixture.nativeElement.querySelector('.cook__move').click();

      const moved = backend.expectOne('/api/v1/cooking/sessions/7/step');
      expect(moved.request.body).toEqual({ position: null });
      moved.flush(session());
    });

    it('offers to finish on the last step', async () => {
      await atStep(1);
      expect(text()).toContain('I am done');
    });

    it('finishing completes the session', async () => {
      await atStep(1);
      fixture.nativeElement.querySelector('.cook__move--go').click();
      backend
        .expectOne('/api/v1/cooking/sessions/7/completed')
        .flush(session({ at_step: 1, outcome: 'completed', finished_at: '2026-08-24T19:00:00Z' }));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(text()).toContain('That is dinner');
    });
  });

  describe('leaving', () => {
    it('offers a way out that keeps the session', async () => {
      // Leaving is not stopping. The whole of UC-9.7 is that it is still there.
      await open();
      const out = fixture.nativeElement.querySelector('.cook__out');
      expect(out.getAttribute('href')).toBe('/plans');
      expect(backend.match('/api/v1/cooking/sessions/7/abandoned')).toEqual([]);
    });

    it('giving up says nothing came out of the pantry', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__give-up').click();
      backend
        .expectOne('/api/v1/cooking/sessions/7/abandoned')
        .flush(session({ outcome: 'abandoned' }));
    });
  });

  it('says so when the session is not one of yours', async () => {
    backend
      .expectOne('/api/v1/cooking/sessions/7')
      .flush({ detail: 'No such meal to cook.' }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('That meal is not one you are cooking');
  });

  describe('when the connection drops', () => {
    /* The kitchen is often the furthest room from the router, and a screen that goes blank
       mid-recipe is the failure NFR-13 names. */

    function unreachable(request: import('@angular/common/http/testing').TestRequest): void {
      // Status 0 is "the request never arrived", which is what a browser reports with no
      // network. Being told no is a different thing and is handled differently.
      request.error(new ProgressEvent('error'), { status: 0, statusText: 'Unknown Error' });
    }

    it('keeps showing the meal it last had', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();
      unreachable(backend.expectOne('/api/v1/cooking/sessions/7/step'));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(text()).toContain('Shortbread');
      expect(text()).not.toContain('That meal is not one you are cooking');
    });

    it('says so, and says it is not a problem', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();
      unreachable(backend.expectOne('/api/v1/cooking/sessions/7/step'));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(text()).toContain('No connection');
      expect(text()).toContain('Keep going');
    });

    it('turns the page anyway', async () => {
      // A cook standing at step one is at step one whether or not the router agrees.
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();
      unreachable(backend.expectOne('/api/v1/cooking/sessions/7/step'));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.cook__instruction').textContent).toContain(
        'Cream the butter.',
      );
    });

    it('will not start a timer it cannot have stamped', async () => {
      // The instant is the server's, and one stamped on the way back would quietly lose
      // however long the connection was down (ADR-013).
      await open(session({ at_step: 0 }));
      fixture.nativeElement.querySelector('.timer__button--primary').click();
      unreachable(backend.expectOne('/api/v1/cooking/sessions/7/timers/0/started'));
      await fixture.whenStable();
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.timer__button--primary').disabled).toBe(true);
      expect(text()).toContain('Timers need the connection');
    });

    it('sends where the cook got to once the network is back', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();
      unreachable(backend.expectOne('/api/v1/cooking/sessions/7/step'));
      await fixture.whenStable();
      fixture.detectChanges();

      window.dispatchEvent(new Event('online'));
      await fixture.whenStable();
      fixture.detectChanges();

      const caught = backend.expectOne('/api/v1/cooking/sessions/7/step');
      expect(caught.request.body).toEqual({ position: 0 });
      caught.flush(session({ at_step: 0 }));
    });

    it('is told apart from a meal that is not yours', async () => {
      await open();
      fixture.nativeElement.querySelector('.cook__move--go').click();
      backend
        .expectOne('/api/v1/cooking/sessions/7/step')
        .flush({ detail: 'No such meal to cook.' }, { status: 404, statusText: 'Not Found' });
      await fixture.whenStable();
      fixture.detectChanges();

      expect(text()).toContain('That meal is not one you are cooking');
    });
  });
});
