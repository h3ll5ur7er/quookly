import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { ApplicationsComponent } from './applications.component';

const APPLICATIONS = '/api/v1/accounts/applications';

function applicant(id: number, name: string): object {
  return {
    id,
    email: `${name.toLowerCase()}@example.com`,
    display_name: name,
    is_admin: false,
    standing: 'applied',
    registered_at: '2026-08-20T12:00:00Z',
    locale: null,
  };
}

describe('ApplicationsComponent', () => {
  let fixture: ComponentFixture<ApplicationsComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function showing(queue: object[]): Promise<void> {
    backend.expectOne(APPLICATIONS).flush(queue);
    await settle();
  }

  function rows(): Element[] {
    return [...fixture.nativeElement.querySelectorAll('.applications__row')];
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApplicationsComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(ApplicationsComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('shows who is waiting, in the order the API gave', async () => {
    // Oldest first, and the order is the API's to decide: the person waiting longest is
    // the one most owed an answer.
    await showing([applicant(2, 'Ana'), applicant(3, 'Mira')]);
    expect(rows()).toHaveLength(2);
    expect(rows()[0].textContent).toContain('Ana');
  });

  it('says so when nobody is waiting, rather than showing an empty screen', async () => {
    await showing([]);
    expect(text()).toContain('Nobody is waiting');
  });

  it('lets somebody in', async () => {
    await showing([applicant(2, 'Ana')]);
    fixture.nativeElement.querySelector('.applications__approve').click();
    await settle();

    const asked = backend.expectOne(`${APPLICATIONS}/2/approved`);
    expect(asked.request.method).toBe('POST');
    asked.flush({ ...applicant(2, 'Ana'), standing: 'approved' });
    await settle();

    expect(rows()).toHaveLength(0);
    expect(text()).toContain('can now sign in');
  });

  it('turns somebody away, and takes them off the queue too', async () => {
    // Refused is a decision, not a pending one. Leaving them here would ask an admin the
    // same question every time they looked.
    await showing([applicant(2, 'Ana')]);
    fixture.nativeElement.querySelector('.applications__refuse').click();
    await settle();
    backend
      .expectOne(`${APPLICATIONS}/2/refused`)
      .flush({ ...applicant(2, 'Ana'), standing: 'refused' });
    await settle();

    expect(rows()).toHaveLength(0);
    expect(text()).toContain('turned away');
  });

  it('keeps them on the queue when the decision did not land', async () => {
    await showing([applicant(2, 'Ana')]);
    fixture.nativeElement.querySelector('.applications__approve').click();
    await settle();
    backend
      .expectOne(`${APPLICATIONS}/2/approved`)
      .flush({}, { status: 500, statusText: 'Server Error' });
    await settle();

    expect(rows()).toHaveLength(1);
    expect(text()).toContain('Something went wrong');
  });

  it('says a failure is a failure rather than showing an empty queue', async () => {
    backend.expectOne(APPLICATIONS).flush({}, { status: 403, statusText: 'Forbidden' });
    await settle();
    expect(text()).toContain('Something went wrong');
    expect(text()).not.toContain('Nobody is waiting');
  });
});
