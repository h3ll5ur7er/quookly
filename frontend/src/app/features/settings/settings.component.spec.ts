import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { SettingsComponent } from './settings.component';

const UNITS = [
  { kind: 'powder', unit: 'g', chosen: false },
  { kind: 'liquid', unit: 'ml', chosen: false },
  { kind: 'solid', unit: 'g', chosen: false },
  { kind: 'countable', unit: 'piece', chosen: false },
];

function session(isAdmin: boolean) {
  return {
    token: 'a-token',
    cook: {
      id: 1,
      email: 'chef@example.com',
      display_name: 'Emanuel',
      is_admin: isAdmin,
      registered_at: '2026-01-01T00:00:00Z',
      locale: null,
    },
  };
}

describe('SettingsComponent', () => {
  let fixture: ComponentFixture<SettingsComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function open(isAdmin: boolean): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [SettingsComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    TestBed.inject(AuthStore).signIn(session(isAdmin));
    fixture = TestBed.createComponent(SettingsComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    backend.expectOne('/api/v1/preferences/units').flush(UNITS);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function reporting(status: object): Promise<void> {
    backend.expectOne('/api/v1/instance/inference').flush(status);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  afterEach(() => backend.verify());

  describe('as an ordinary cook', () => {
    it('does not ask about the instance at all', async () => {
      /* It names an address on the operator's network. Not a cook's business, and asking
         would only earn a 403. */
      await open(false);
      backend.expectNone('/api/v1/instance/inference');
      expect(text()).not.toContain('Recipe reading');
    });

    it('still shows the units', async () => {
      await open(false);
      expect(text()).toContain('Units');
    });
  });

  describe('as an administrator', () => {
    it('says what the instance will ask', async () => {
      await open(true);
      await reporting({
        configured: true,
        base_url: 'http://jarvis:9293/v1',
        model: 'qwen',
        authenticated: false,
        reachable: true,
        detail: null,
      });
      expect(text()).toContain('http://jarvis:9293/v1');
      expect(text()).toContain('qwen');
      expect(text()).toContain('Answering');
    });

    it('says whether a key is set without saying what it is', async () => {
      await open(true);
      await reporting({
        configured: true,
        base_url: 'https://openrouter.ai/api/v1',
        model: 'a-model',
        authenticated: true,
        reachable: true,
        detail: null,
      });
      expect(text()).toContain('Set');
    });

    it('says why a provider is not answering', async () => {
      /* "Could not reach it" and "check the key" send an operator to two different
         places. Flattening them into "not answering" sends them to neither. */
      await open(true);
      await reporting({
        configured: true,
        base_url: 'http://jarvis:9293/v1',
        model: 'qwen',
        authenticated: false,
        reachable: false,
        detail: 'could not reach it: no route to host',
      });
      expect(text()).toContain('Not answering');
      expect(text()).toContain('no route to host');
    });

    it('treats no provider as a state rather than a fault', async () => {
      await open(true);
      await reporting({
        configured: false,
        base_url: null,
        model: null,
        authenticated: false,
        reachable: null,
        detail: 'Set QUOOKLY_INFERENCE_BASE_URL and QUOOKLY_INFERENCE_MODEL.',
      });
      expect(text()).toContain('Every other part of Quookly works without one');
      expect(text()).toContain('QUOOKLY_INFERENCE_BASE_URL');
    });

    it('keeps the units when the instance section fails', async () => {
      /* Two requests, two failures. One should not take the other down. */
      await open(true);
      backend
        .expectOne('/api/v1/instance/inference')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();
      fixture.detectChanges();
      expect(text()).toContain('Units');
    });
  });
});
