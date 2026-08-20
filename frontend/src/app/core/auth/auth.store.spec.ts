import { TestBed } from '@angular/core/testing';
import type { Authenticated } from '@api';
import { AuthStore, SESSION_STORAGE_KEY } from './auth.store';

const SESSION: Authenticated = {
  token: 'a-token',
  cook: {
    id: 1,
    email: 'cook@example.com',
    display_name: 'Emanuel',
    is_admin: false,
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
