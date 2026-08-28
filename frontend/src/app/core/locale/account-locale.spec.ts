import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Standing, provideApi } from '@api';
import type { Authenticated } from '@api';
import { AccountLocale } from './account-locale';
import { LOCALE_STORAGE_KEY } from './locale.store';

function session(locale: string | null): Authenticated {
  return {
    token: 'a-token',
    cook: {
      id: 1,
      email: 'cook@example.com',
      display_name: 'Emanuel',
      is_admin: false,
      standing: Standing.approved,
      registered_at: '2026-08-20T12:00:00Z',
      locale,
    },
  } as Authenticated;
}

describe('AccountLocale', () => {
  let backend: HttpTestingController;

  function settling(): AccountLocale {
    return TestBed.inject(AccountLocale);
  }

  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('adopts the language on the account, whatever the browser says', () => {
    /* The whole of L6. The household's browser is English and the account is German; the
       cook signing in reads German without touching the operating system. */
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en-GB');

    expect(settling().settle(session('de-CH'))).toBe(true);

    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('de-CH');
  });

  it('does not reload when the account already agrees with the screen', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'de-CH');
    expect(settling().settle(session('de-CH'))).toBe(false);
  });

  it('records the language in use where the account has none', () => {
    /* Otherwise the two halves disagree for ever: the browser answers for the interface
       and the server falls back to English for ingredient names, so a German screen says
       "caster sugar". Writing it down is what makes the account the authority it is
       supposed to be. */
    localStorage.setItem(LOCALE_STORAGE_KEY, 'de-CH');

    expect(settling().settle(session(null))).toBe(false);

    const asked = backend.expectOne('/api/v1/setup/locale');
    expect(asked.request.body).toEqual({ locale: 'de-CH' });
    asked.flush({});
  });

  it('leaves alone a language this build does not ship', () => {
    /* An account set to something we have no catalogue for is still a choice somebody
       made. Overwriting it with the language of whichever device they happen to be at is
       how a preference quietly disappears. */
    localStorage.setItem(LOCALE_STORAGE_KEY, 'de-CH');

    expect(settling().settle(session('pt-BR'))).toBe(false);

    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('de-CH');
    backend.expectNone('/api/v1/setup/locale');
  });
});
