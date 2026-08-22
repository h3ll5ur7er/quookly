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

  const SIGNED_IN = {
    token: 'a-token',
    cook: {
      id: 1,
      email: 'chef@example.com',
      display_name: 'Emanuel',
      is_admin: true,
      registered_at: '2026-01-01T00:00:00Z',
    },
  };

  it('offers the way to each part of the app once somebody is signed in', async () => {
    TestBed.inject(AuthStore).signIn(SIGNED_IN);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(links()).toEqual(['/', '/recipes', '/plans', '/shopping', '/pantry']);
  });

  it('shows no navigation to somebody who cannot use it', async () => {
    TestBed.inject(AuthStore).signOut();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(links()).toEqual([]);
  });

  it('names the navigation, so it is not an unlabelled group of links', async () => {
    TestBed.inject(AuthStore).signIn(SIGNED_IN);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('nav')?.getAttribute('aria-label')).toBeTruthy();
  });

  async function signedIn(): Promise<void> {
    TestBed.inject(AuthStore).signIn(SIGNED_IN);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('does not put what is set once into the bar a cook lives in', async () => {
    // Household, units, theme and language are chosen and then left alone. A permanent
    // share of a phone screen is the wrong price for that.
    await signedIn();
    expect(links()).not.toContain('/household');
    expect(fixture.nativeElement.querySelector('app-theme-picker')).toBeNull();
    expect(fixture.nativeElement.querySelector('app-locale-picker')).toBeNull();
  });

  it('offers the way to settings and the account', async () => {
    await signedIn();
    const account = fixture.nativeElement.querySelector('.shell__account');
    expect(account.getAttribute('href')).toBe('/settings');
  });

  it('says who is signed in', async () => {
    await signedIn();
    expect(fixture.nativeElement.textContent).toContain('Emanuel');
    expect(fixture.nativeElement.querySelector('.shell__avatar').textContent.trim()).toBe('E');
  });

  it('carries the mark, which lived only in a PWA icon before', async () => {
    await signedIn();
    expect(fixture.nativeElement.querySelector('.shell__mark')).not.toBeNull();
  });

  it('labels every destination in words, not in glyphs alone', async () => {
    // Five words do not fit a 360px bar and five glyphs are a guessing game. Together they
    // fit and they are readable.
    await signedIn();
    const labels = [...fixture.nativeElement.querySelectorAll('.shell__label')].map(
      (node: Element) => node.textContent!.trim(),
    );
    expect(labels).toEqual(['Home', 'Recipes', 'Plan', 'Shopping', 'Pantry']);
  });
});
