import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AuthStore } from './core/auth/auth.store';
import { App } from './app';

describe('App', () => {
  let fixture: ComponentFixture<App>;

  function links(): (string | null)[] {
    return [...fixture.nativeElement.querySelectorAll('nav a')].map((a: HTMLAnchorElement) =>
      a.getAttribute('href'),
    );
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [App],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    fixture = TestBed.createComponent(App);
    await fixture.whenStable();
  });

  it('should create the app', () => {
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('offers the way to each part of the app once somebody is signed in', async () => {
    TestBed.inject(AuthStore).signIn({
      token: 'a-token',
      cook: {
        id: 1,
        email: 'chef@example.com',
        display_name: 'Emanuel',
        is_admin: true,
        registered_at: '2026-01-01T00:00:00Z',
      },
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(links()).toContain('/recipes');
    expect(links()).toContain('/household');
  });

  it('shows no navigation to somebody who cannot use it', async () => {
    TestBed.inject(AuthStore).signOut();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(links()).toEqual([]);
  });

  it('names the navigation, so it is not an unlabelled group of links', async () => {
    TestBed.inject(AuthStore).signIn({
      token: 'a-token',
      cook: {
        id: 1,
        email: 'chef@example.com',
        display_name: 'Emanuel',
        is_admin: true,
        registered_at: '2026-01-01T00:00:00Z',
      },
    });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('nav')?.getAttribute('aria-label')).toBeTruthy();
  });
});
