import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import type { Authenticated } from '@api';
import { authInterceptor } from './auth.interceptor';
import { AuthStore } from './auth.store';
import { Standing } from '@api';

const SESSION: Authenticated = {
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

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let auth: AuthStore;

  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthStore);
  });

  afterEach(() => backend.verify());

  it('sends no authorization when nobody is signed in', () => {
    http.get('/api/v1/status').subscribe();
    const request = backend.expectOne('/api/v1/status');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({});
  });

  it('attaches the token once signed in', () => {
    auth.signIn(SESSION);
    http.get('/api/v1/status').subscribe();
    const request = backend.expectOne('/api/v1/status');
    expect(request.request.headers.get('Authorization')).toBe('Bearer a-token');
    request.flush({});
  });

  it('stops attaching it after signing out', () => {
    auth.signIn(SESSION);
    auth.signOut();
    http.get('/api/v1/status').subscribe();
    const request = backend.expectOne('/api/v1/status');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({});
  });

  it('leaves an authorization header the caller already set', () => {
    auth.signIn(SESSION);
    http.get('/api/v1/status', { headers: { Authorization: 'Bearer something-else' } }).subscribe();
    const request = backend.expectOne('/api/v1/status');
    expect(request.request.headers.get('Authorization')).toBe('Bearer something-else');
    request.flush({});
  });
});
