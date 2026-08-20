import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { SignInComponent } from './sign-in.component';

const AUTHENTICATED = {
  token: 'a-token',
  cook: {
    id: 1,
    email: 'cook@example.com',
    display_name: 'Emanuel',
    is_admin: false,
    registered_at: '2026-08-20T12:00:00Z',
  },
};

describe('SignInComponent', () => {
  let fixture: ComponentFixture<SignInComponent>;
  let backend: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  function fill(email: string, password: string): void {
    const form = (fixture.componentInstance as unknown as { form: { setValue: (v: unknown) => void } })
      .form;
    form.setValue({ email, password });
  }

  function submit(): void {
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
  }

  beforeEach(async () => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [SignInComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(SignInComponent);
    backend = TestBed.inject(HttpTestingController);
    // The router has no routes here; navigation is asserted, not performed.
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('will not submit an empty form', () => {
    submit();
    backend.expectNone('/api/v1/accounts/sign-in');
  });

  it('signs the cook in and sends them onward', async () => {
    fill('cook@example.com', 'a-sufficiently-long-password');
    submit();
    backend.expectOne('/api/v1/accounts/sign-in').flush(AUTHENTICATED);
    await fixture.whenStable();

    expect(TestBed.inject(AuthStore).isSignedIn()).toBe(true);
    expect(navigate).toHaveBeenCalledWith('/recipes');
  });

  it('reports a refusal without saying why', async () => {
    fill('cook@example.com', 'wrong-password-entirely');
    submit();
    backend
      .expectOne('/api/v1/accounts/sign-in')
      .flush({ detail: 'nope' }, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]');
    expect(alert.textContent).toContain('did not match an account');
    expect(TestBed.inject(AuthStore).isSignedIn()).toBe(false);
  });

  it('lets the cook try again after a refusal', async () => {
    fill('cook@example.com', 'wrong-password-entirely');
    submit();
    backend
      .expectOne('/api/v1/accounts/sign-in')
      .flush({}, { status: 401, statusText: 'Unauthorized' });
    await fixture.whenStable();

    submit();
    backend.expectOne('/api/v1/accounts/sign-in').flush(AUTHENTICATED);
    await fixture.whenStable();
    expect(TestBed.inject(AuthStore).isSignedIn()).toBe(true);
  });
});
