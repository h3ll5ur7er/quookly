import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { ApplyComponent } from './apply.component';

const APPLICATION = {
  display_name: 'Emanuel',
  email: 'cook@example.com',
  password: 'a-sufficiently-long-password',
};

describe('ApplyComponent', () => {
  let fixture: ComponentFixture<ApplyComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function fill(values: Record<string, string> = APPLICATION): void {
    (
      fixture.componentInstance as unknown as { form: { setValue: (v: unknown) => void } }
    ).form.setValue(values);
  }

  async function submit(): Promise<void> {
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ApplyComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(ApplyComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    fixture.detectChanges();
  });

  afterEach(() => backend.verify());

  it('says whose instance this is before the form, not after it', () => {
    // Somebody who fills this in expecting to be cooking in a minute has been misled by
    // the button. The sentence has to come first or it is an apology.
    expect(text()).toContain('belongs to somebody');
  });

  it('will not send an incomplete application', async () => {
    fill({ ...APPLICATION, email: '' });
    await submit();
    backend.expectNone('/api/v1/accounts/applications');
  });

  it('will not send a password the API would refuse', async () => {
    fill({ ...APPLICATION, password: 'short' });
    await submit();
    backend.expectNone('/api/v1/accounts/applications');
  });

  it('sends the application', async () => {
    fill();
    await submit();
    const asked = backend.expectOne('/api/v1/accounts/applications');
    expect(asked.request.body).toEqual(APPLICATION);
    asked.flush({ id: 2, standing: 'applied' });
  });

  it('says what happens next, rather than signing anybody in', async () => {
    fill();
    await submit();
    backend.expectOne('/api/v1/accounts/applications').flush({ id: 2, standing: 'applied' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('Your application is in');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });

  it('says an address is taken without saying which door it is behind', async () => {
    // The API answers the same way for an account and an earlier application, and
    // guessing between them here would undo that.
    fill();
    await submit();
    backend
      .expectOne('/api/v1/accounts/applications')
      .flush({}, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('already been used');
  });

  it('lets somebody try again when sending failed', async () => {
    fill();
    await submit();
    backend
      .expectOne('/api/v1/accounts/applications')
      .flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(text()).toContain('Please try again');
    expect(fixture.nativeElement.querySelector('form')).not.toBeNull();
  });
});
