import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { BootstrapComponent } from './bootstrap.component';

const ADMIN = {
  token: 'a-token',
  cook: {
    id: 1,
    email: 'admin@example.com',
    display_name: 'Emanuel',
    is_admin: true,
    registered_at: '2026-08-20T12:00:00Z',
  },
};

describe('BootstrapComponent', () => {
  let fixture: ComponentFixture<BootstrapComponent>;
  let backend: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  function fill(password: string): void {
    (
      fixture.componentInstance as unknown as { form: { setValue: (v: unknown) => void } }
    ).form.setValue({
      display_name: 'Emanuel',
      email: 'admin@example.com',
      password,
    });
  }

  function submit(): void {
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
  }

  beforeEach(async () => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [BootstrapComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(BootstrapComponent);
    backend = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('refuses a password the API would reject anyway', () => {
    fill('short');
    submit();
    backend.expectNone('/api/v1/accounts/bootstrap');
  });

  it('creates the administrator and continues to the recipes', async () => {
    fill('a-sufficiently-long-password');
    submit();
    backend.expectOne('/api/v1/accounts/bootstrap').flush(ADMIN);
    await fixture.whenStable();

    expect(TestBed.inject(AuthStore).isAdmin()).toBe(true);
    expect(navigate).toHaveBeenCalledWith('/recipes');
  });

  it('explains a claimed instance rather than failing silently', async () => {
    fill('a-sufficiently-long-password');
    submit();
    backend
      .expectOne('/api/v1/accounts/bootstrap')
      .flush({ detail: 'taken' }, { status: 409, statusText: 'Conflict' });
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain(
      'already been claimed',
    );
  });
});
