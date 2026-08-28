import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideApi, Standing } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { SignInComponent } from './sign-in.component';

const AUTHENTICATED = {
  token: 'a-token',
  cook: {
    id: 1,
    email: 'cook@example.com',
    display_name: 'Emanuel',
    is_admin: false,
    standing: Standing.approved,
    registered_at: '2026-08-20T12:00:00Z',
  },
};

describe('SignInComponent', () => {
  let fixture: ComponentFixture<SignInComponent>;
  let backend: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  function fill(email: string, password: string): void {
    const form = (
      fixture.componentInstance as unknown as { form: { setValue: (v: unknown) => void } }
    ).form;
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
    expect(navigate).toHaveBeenCalledWith('/');

    // This account has no language recorded, so the one being read is written down —
    // otherwise the server answers in English while the screen is in something else, for
    // ever (L6).
    backend.expectOne('/api/v1/setup/locale').flush({});
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
    backend.expectOne('/api/v1/setup/locale').flush({});
  });

  describe('when the door is not open yet', () => {
    /**
     * Three different refusals, three different sentences. The API tells them apart only
     * once the password has matched (ADR-049), so repeating that distinction here reveals
     * nothing — and collapsing them would leave an applicant retyping a password that was
     * right all along.
     */
    async function refusedWith(status: number, detail: string): Promise<void> {
      fill('cook@example.com', 'a-sufficiently-long-password');
      submit();
      await fixture.whenStable();
      backend
        .expectOne('/api/v1/accounts/sign-in')
        .flush({ detail }, { status, statusText: 'Refused' });
      await fixture.whenStable();
      fixture.detectChanges();
    }

    it('tells an applicant they are waiting on a person', async () => {
      await refusedWith(403, 'Your application is waiting for an administrator.');
      expect(fixture.nativeElement.textContent).toContain('waiting');
      expect(fixture.nativeElement.textContent).not.toContain('did not match');
    });

    it('tells somebody who was turned away, rather than leaving them waiting forever', async () => {
      await refusedWith(403, 'An administrator of this instance declined this account.');
      expect(fixture.nativeElement.textContent).toContain('declined');
    });

    it('still says nothing at all about a wrong password', async () => {
      await refusedWith(401, 'Those credentials did not match an account.');
      expect(fixture.nativeElement.textContent).toContain('did not match');
    });

    it('offers the way to apply, for somebody with no account at all', async () => {
      expect(fixture.nativeElement.querySelector('.auth__apply').getAttribute('href')).toBe(
        '/apply',
      );
    });
  });
});
