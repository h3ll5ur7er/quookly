import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { SetupComponent } from './setup.component';

function step(name: string, done: boolean, declared = false) {
  return { step: name, done, declared };
}

function progress(steps: ReturnType<typeof step>[], nextStep: string | null) {
  return { steps, next_step: nextStep, complete: nextStep === null };
}

const NOTHING_DONE = progress(
  [
    step('household', false),
    step('constraints', false),
    step('units', false),
    step('locale', false),
  ],
  'household',
);

describe('SetupComponent', () => {
  let fixture: ComponentFixture<SetupComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function load(body: object): Promise<void> {
    backend.expectOne('/api/v1/setup').flush(body);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [SetupComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(SetupComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks the backend what is outstanding rather than remembering', () => {
    backend.expectOne('/api/v1/setup').flush(NOTHING_DONE);
  });

  it('shows every step, not only the next one', async () => {
    // UC-10.3: a wizard revealing one door at a time cannot say how far there is to go.
    await load(NOTHING_DONE);
    expect(fixture.nativeElement.querySelectorAll('.setup__step').length).toBe(4);
  });

  it('says why each step is worth doing', async () => {
    await load(NOTHING_DONE);
    expect(text()).toContain('scaled to the people at your table');
  });

  it('offers a way to do each outstanding step', async () => {
    await load(NOTHING_DONE);
    expect(fixture.nativeElement.querySelector('a[href="/household/new"]')).not.toBeNull();
  });

  it('marks a step that is done', async () => {
    await load(progress([step('household', true), step('constraints', false)], 'constraints'));
    const first = fixture.nativeElement.querySelectorAll('.setup__step')[0];
    expect(first.className).toContain('setup__step--done');
  });

  it('says which answer settled a declared step, rather than only ticking it', async () => {
    /*
     * "Nobody avoids anything" and "somebody has a recorded allergy" are both done, and
     * they are not the same thing to show a cook (FR-15).
     */
    await load(progress([step('constraints', true, true)], null));
    expect(text()).toContain('You said nobody avoids anything');
  });

  it('does not claim a step settled by real data was declared', async () => {
    await load(progress([step('constraints', true, false)], null));
    expect(text()).not.toContain('You said nobody avoids anything');
    expect(text()).toContain('Done');
  });

  it('lets a cook answer a question with nothing', async () => {
    await load(NOTHING_DONE);
    fixture.nativeElement.querySelectorAll('.setup__skip')[1].click();
    const request = backend.expectOne('/api/v1/setup/declarations/constraints');
    expect(request.request.method).toBe('POST');
    request.flush(progress([step('constraints', true, true)], null));
  });

  it('shows the answer without asking again', async () => {
    await load(NOTHING_DONE);
    fixture.nativeElement.querySelectorAll('.setup__skip')[1].click();
    backend
      .expectOne('/api/v1/setup/declarations/constraints')
      .flush(progress([step('constraints', true, true)], null));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('You said nobody avoids anything');
  });

  it('fills in only the step to start with', async () => {
    /* Four primary buttons down a page compete with each other and answer nothing. */
    await load(NOTHING_DONE);
    expect(fixture.nativeElement.querySelectorAll('.setup__go--now').length).toBe(1);
    expect(fixture.nativeElement.querySelector('.setup__go--now').textContent).toContain(
      'Add someone',
    );
  });

  it('moves the emphasis on as steps are settled', async () => {
    await load(progress([step('household', true), step('constraints', false)], 'constraints'));
    expect(fixture.nativeElement.querySelector('.setup__go--now').textContent).toContain(
      'Record what they avoid',
    );
  });

  it('says so when everything is settled, and points somewhere useful', async () => {
    await load(progress([step('household', true)], null));
    expect(text()).toContain('Everything is set');
    expect(fixture.nativeElement.querySelector('a[href="/recipes"]')).not.toBeNull();
  });

  it('reports a failure rather than showing an empty checklist', async () => {
    backend.expectOne('/api/v1/setup').flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  });
});
