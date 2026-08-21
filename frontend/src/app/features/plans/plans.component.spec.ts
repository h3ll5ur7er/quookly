import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { PlansComponent } from './plans.component';

describe('PlansComponent', () => {
  let fixture: ComponentFixture<PlansComponent>;
  let backend: HttpTestingController;
  let navigated: ReturnType<typeof vi.spyOn>;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function answer(weeks: object[]): Promise<void> {
    backend.expectOne('/api/v1/plans').flush(weeks);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [PlansComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    navigated = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(PlansComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the plans', () => {
    backend.expectOne('/api/v1/plans').flush([]);
  });

  it('explains an empty list rather than showing a blank screen', async () => {
    await answer([]);
    expect(text()).toContain('Nothing planned yet');
  });

  it('lists a week by its period and how much of it is planned', async () => {
    await answer([{ id: 3, starts_on: '2026-08-24', ends_on: '2026-08-30', planned: 4 }]);
    expect(text()).toContain('4');
    expect(fixture.nativeElement.querySelector('a[href="/plans/3"]')).not.toBeNull();
  });

  it('says "one meal" rather than "1 meals"', async () => {
    await answer([{ id: 3, starts_on: '2026-08-24', ends_on: '2026-08-30', planned: 1 }]);
    expect(text()).toContain('One meal');
  });

  it('offers next week already filled in', async () => {
    /* A cook planning on a Sunday evening is planning the week that starts tomorrow, and
       a blank pair of date fields is a small puzzle in front of the thing they came for. */
    await answer([]);
    const from = fixture.nativeElement.querySelector('#starts_on') as HTMLInputElement;
    const to = fixture.nativeElement.querySelector('#ends_on') as HTMLInputElement;
    expect(from.value).not.toBe('');
    expect(new Date(`${from.value}T00:00:00`).getDay()).toBe(1);
    expect(new Date(to.value).getTime() - new Date(from.value).getTime()).toBe(6 * 86_400_000);
  });

  it('opens the week it just started', async () => {
    await answer([]);
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();

    const sent = backend.expectOne('/api/v1/plans');
    expect(sent.request.method).toBe('POST');
    sent.flush({ id: 12, starts_on: '2026-08-24', ends_on: '2026-08-30', slots: [], shopping: [] });
    await fixture.whenStable();

    expect(navigated).toHaveBeenCalledWith('/plans/12');
  });

  it('reports a failure rather than claiming there are no plans', async () => {
    backend.expectOne('/api/v1/plans').flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(text()).not.toContain('Nothing planned yet');
  });
});
