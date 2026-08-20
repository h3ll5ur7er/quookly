import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { EaterFormComponent } from './eater-form.component';

const JONAS = {
  id: 7,
  name: 'Jonas',
  age_band: 'adult',
  appetite: '1.4',
  constraints: [{ allergen: 'peanuts', ingredient_slug: null, severity: 'medical' }],
};

function build(id: string | null): {
  fixture: ComponentFixture<EaterFormComponent>;
  backend: HttpTestingController;
} {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    imports: [EaterFormComponent],
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      provideApi(''),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: new Map(id === null ? [] : [['id', id]]) } },
      },
    ],
  });
  return {
    fixture: TestBed.createComponent(EaterFormComponent),
    backend: TestBed.inject(HttpTestingController),
  };
}

describe('EaterFormComponent', () => {
  let fixture: ComponentFixture<EaterFormComponent>;
  let backend: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  function field(id: string): HTMLInputElement | HTMLSelectElement {
    return fixture.nativeElement.querySelector(`#${id}`);
  }

  async function set(id: string, value: string): Promise<void> {
    const control = field(id);
    control.value = value;
    control.dispatchEvent(new Event(id === 'ageBand' || id === 'severity' ? 'change' : 'input'));
    control.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function click(selector: string): Promise<void> {
    fixture.nativeElement.querySelector(selector).click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function chips(): string[] {
    return [...fixture.nativeElement.querySelectorAll('.chip')].map((chip: HTMLElement) =>
      chip.textContent!.trim(),
    );
  }

  afterEach(() => backend.verify());

  describe('adding somebody', () => {
    beforeEach(async () => {
      ({ fixture, backend } = build('new'));
      navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
      await fixture.whenStable();
      fixture.detectChanges();
    });

    it('asks for nobody, because there is nobody yet', () => {
      backend.expectNone(() => true);
    });

    it('is still an add form when the route carries no id at all', async () => {
      /*
       * `/household/new` is its own route and has no `:id`. Reading the absent parameter
       * as a number asks for eater zero, and the add form becomes a "not found" page.
       */
      ({ fixture, backend } = build(null));
      await fixture.whenStable();
      fixture.detectChanges();
      backend.expectNone(() => true);
      expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
    });

    it('starts with a standard portion, which is what most people eat', () => {
      expect(field('appetite').value).toBe('1');
    });

    it('sends what was filled in', async () => {
      await set('name', 'Mira');
      await click('button[type="submit"]');
      const request = backend.expectOne('/api/v1/eaters');
      expect(request.request.method).toBe('POST');
      expect(request.request.body.name).toBe('Mira');
      request.flush(JONAS);
      await fixture.whenStable();
      expect(navigate).toHaveBeenCalledWith('/household');
    });

    it('will not send an eater with no name', async () => {
      await click('button[type="submit"]');
      backend.expectNone(() => true);
    });

    it('records an allergen as a constraint', async () => {
      await set('name', 'Mira');
      await set('avoids', 'peanuts');
      await click('.secondary');
      expect(chips().join(' ')).toContain('Peanuts');
      await click('button[type="submit"]');
      const request = backend.expectOne('/api/v1/eaters');
      expect(request.request.body.constraints).toEqual([
        { allergen: 'peanuts', ingredient_slug: null, severity: 'medical' },
      ]);
      request.flush(JONAS);
    });

    it('takes a constraint back off again', async () => {
      await set('avoids', 'peanuts');
      await click('.secondary');
      await click('.chip__remove');
      expect(chips()).toEqual([]);
    });
  });

  describe('avoiding a particular ingredient', () => {
    beforeEach(async () => {
      ({ fixture, backend } = build('new'));
      navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
      await fixture.whenStable();
      fixture.detectChanges();
      await set('avoids', 'ingredient');
    });

    it('refuses a name the registry does not know', async () => {
      /*
       * The important one. A constraint is matched to a recipe by slug, so a name that
       * resolves to nothing produces a constraint that never fires — which reads on
       * screen as protection and is the opposite of it.
       */
      await set('ingredient', 'unicorn tears');
      backend.expectOne('/api/v1/ingredients?search=unicorn%20tears').flush([]);
      await fixture.whenStable();
      await click('.secondary');
      expect(chips()).toEqual([]);
      expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    });

    it('records the slug of what was picked, not the words that were typed', async () => {
      await set('ingredient', 'coriander');
      backend
        .expectOne('/api/v1/ingredients?search=coriander')
        .flush([{ id: 3, slug: 'coriander-leaf', name: 'coriander', kind: 'solid' }]);
      await fixture.whenStable();
      fixture.detectChanges();
      await click('.secondary');
      await set('name', 'Mira');
      await click('button[type="submit"]');
      const request = backend.expectOne('/api/v1/eaters');
      expect(request.request.body.constraints[0].ingredient_slug).toBe('coriander-leaf');
      request.flush(JONAS);
    });

    it('does not look anything up for a single letter', async () => {
      await set('ingredient', 'c');
      backend.expectNone(() => true);
    });
  });

  describe('correcting somebody already there', () => {
    beforeEach(async () => {
      ({ fixture, backend } = build('7'));
      navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
      backend.expectOne('/api/v1/eaters/7').flush(JONAS);
      await fixture.whenStable();
      fixture.detectChanges();
    });

    it('fills the form with what is already known', () => {
      expect(field('name').value).toBe('Jonas');
      expect(field('appetite').value).toBe('1.4');
    });

    it('shows what they already avoid', () => {
      expect(chips().join(' ')).toContain('Peanuts');
    });

    it('sends the whole person back, so a removed allergy is really removed', async () => {
      await click('.chip__remove');
      await click('button[type="submit"]');
      const request = backend.expectOne('/api/v1/eaters/7');
      expect(request.request.method).toBe('PUT');
      expect(request.request.body.constraints).toEqual([]);
      request.flush(JONAS);
    });

    it('can take somebody out of the household', async () => {
      await click('.destructive');
      const request = backend.expectOne('/api/v1/eaters/7');
      expect(request.request.method).toBe('DELETE');
      request.flush(null);
      await fixture.whenStable();
      expect(navigate).toHaveBeenCalledWith('/household');
    });
  });

  describe('somebody who is not there', () => {
    it('says so rather than offering an empty form', async () => {
      ({ fixture, backend } = build('404'));
      backend.expectOne('/api/v1/eaters/404').flush({}, { status: 404, statusText: 'Not Found' });
      await fixture.whenStable();
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('not in your household');
      expect(fixture.nativeElement.querySelector('form')).toBeNull();
    });
  });
});
