import { TestBed } from '@angular/core/testing';
import type { Authenticated } from '@api';
import { keep, kept } from '../offline/kept';
import { LOCALE_STORAGE_KEY } from '../locale/locale.store';
import { AuthStore, SESSION_STORAGE_KEY } from './auth.store';
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

function store(): AuthStore {
  return TestBed.inject(AuthStore);
}

describe('AuthStore', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  describe('signed out by default', () => {
    it('starts with nobody signed in', () => {
      expect(store().isSignedIn()).toBe(false);
      expect(store().cook()).toBeNull();
      expect(store().token()).toBeNull();
    });
  });

  describe('signing in', () => {
    it('remembers the cook and the token', () => {
      const auth = store();
      auth.signIn(SESSION);
      expect(auth.isSignedIn()).toBe(true);
      expect(auth.cook()?.email).toBe('cook@example.com');
      expect(auth.token()).toBe('a-token');
    });

    it('exposes whether the cook is an admin', () => {
      const auth = store();
      auth.signIn({ ...SESSION, cook: { ...SESSION.cook, is_admin: true } });
      expect(auth.isAdmin()).toBe(true);
    });

    it('survives a reload', () => {
      store().signIn(SESSION);
      TestBed.resetTestingModule();
      expect(store().isSignedIn()).toBe(true);
      expect(store().cook()?.email).toBe('cook@example.com');
    });
  });

  describe('signing out', () => {
    it('forgets the session', () => {
      const auth = store();
      auth.signIn(SESSION);
      auth.signOut();
      expect(auth.isSignedIn()).toBe(false);
      expect(auth.token()).toBeNull();
    });

    it('does not leave the session behind for the next visitor', () => {
      const auth = store();
      auth.signIn(SESSION);
      auth.signOut();
      expect(localStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    });

    it('does not leave what was kept for a lost connection either', () => {
      // A cooking session held for offline reading is somebody's dinner, and the next
      // person at this device is not necessarily the last one.
      const auth = store();
      auth.signIn(SESSION);
      keep('cooking.7', { title: 'Shortbread' });

      auth.signOut();

      expect(kept('cooking.7')).toBeNull();
    });

    it('forgets the language, because it belonged to whoever chose it', () => {
      /* A household shares a device. The language on it is the language of the person who
         signed in, not of the box — so leaving it behind hands the next cook somebody
         else's language, and hands *their* account that language the first time they have
         none of their own (L6). */
      const auth = store();
      auth.signIn(SESSION);
      localStorage.setItem(LOCALE_STORAGE_KEY, 'de-CH');

      auth.signOut();

      expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull();
    });
  });

  describe('signing in', () => {
    it('clears what the last person left behind', () => {
      keep('cooking.7', { title: 'Shortbread' });
      store().signIn(SESSION);
      expect(kept('cooking.7')).toBeNull();
    });
  });

  describe('when storage is unusable', () => {
    it('treats corrupt stored data as signed out rather than crashing', () => {
      localStorage.setItem(SESSION_STORAGE_KEY, 'not json');
      expect(store().isSignedIn()).toBe(false);
    });

    it('ignores stored data that is not a session', () => {
      localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ nonsense: true }));
      expect(store().isSignedIn()).toBe(false);
    });

    it('still signs in when storage refuses to write', () => {
      const setItem = Storage.prototype.setItem;
      Storage.prototype.setItem = () => {
        throw new Error('storage is full');
      };
      try {
        const auth = store();
        auth.signIn(SESSION);
        expect(auth.isSignedIn()).toBe(true);
      } finally {
        Storage.prototype.setItem = setItem;
      }
    });
  });
});
