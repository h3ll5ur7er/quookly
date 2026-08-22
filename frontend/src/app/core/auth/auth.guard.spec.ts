import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree } from '@angular/router';
import { provideRouter } from '@angular/router';
import type { Authenticated } from '@api';
import { requireSignedIn } from './auth.guard';
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

function guardFor(url: string): boolean | UrlTree {
  return TestBed.runInInjectionContext(() => requireSignedIn({} as never, { url } as never)) as
    | boolean
    | UrlTree;
}

describe('requireSignedIn', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  it('lets a signed-in cook through', () => {
    TestBed.inject(AuthStore).signIn(SESSION);
    expect(guardFor('/dashboard')).toBe(true);
  });

  it('redirects a stranger to sign in', () => {
    const result = guardFor('/dashboard');
    expect(result).not.toBe(true);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toContain('/sign-in');
  });

  it('remembers where they were going', () => {
    const result = guardFor('/dashboard');
    const target = TestBed.inject(Router).serializeUrl(result as UrlTree);
    expect(target).toContain('returnUrl=%2Fdashboard');
  });
});
