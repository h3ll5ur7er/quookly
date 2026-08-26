import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { AcademyPageComponent } from './page.component';

const FOLD = {
  slug: 'fold',
  kind: 'technique',
  name: 'fold',
  summary: 'Combine without knocking out the air.',
  explanation: 'Cut down through the middle and turn the mixture over itself.',
  spellings: ['fold in', 'folded in'],
  origin: 'seed',
  generated: false,
  approved: true,
  caution: null,
  also: [],
};

describe('AcademyPageComponent', () => {
  let fixture: ComponentFixture<AcademyPageComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function click(label: string): void {
    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    const wanted = buttons.find((button) => button.textContent?.trim() === label);
    if (!wanted) {
      throw new Error(`No button reading "${label}"`);
    }
    wanted.click();
  }

  function set(selector: string, value: string): void {
    const field: HTMLInputElement = fixture.nativeElement.querySelector(selector);
    field.value = value;
    field.dispatchEvent(new Event('input'));
  }

  async function arrive({ admin = false, params = { slug: 'fold' } } = {}): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [AcademyPageComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: AuthStore, useValue: { isAdmin: signal(admin) } },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: { get: (key: string) => (params as Record<string, string>)[key] ?? null },
            },
          },
        },
      ],
    });
    fixture = TestBed.createComponent(AcademyPageComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  }

  afterEach(() => backend.verify());

  describe('reading a page', () => {
    it('shows what it means', async () => {
      await arrive();
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).toContain('Combine without knocking out the air.');
    });

    it('offers a cook nothing to change', async () => {
      await arrive();
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).not.toContain('Correct this page');
    });
  });

  describe('correcting it', () => {
    it('arrives filled in with what the page says', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();

      click('Correct this page');
      await fixture.whenStable();

      const name: HTMLInputElement = fixture.nativeElement.querySelector('#name');
      const spellings: HTMLInputElement = fixture.nativeElement.querySelector('#spellings');
      expect(name.value).toBe('fold');
      // One per line: they are a list, and a comma is a character a spelling may contain.
      expect(spellings.value).toBe('fold in\nfolded in');
    });

    it('sends the whole wording for one language', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();

      click('Correct this page');
      await fixture.whenStable();
      set('#summary', 'Combine gently.');
      await fixture.whenStable();
      click('Save the page');
      await fixture.whenStable();

      const sent = backend.expectOne('/api/v1/academy/fold/wordings/en-GB');
      expect(sent.request.method).toBe('PUT');
      expect(sent.request.body.summary).toBe('Combine gently.');
      expect(sent.request.body.spellings).toEqual(['fold in', 'folded in']);
      sent.flush({ ...FOLD, summary: 'Combine gently.' });
      await fixture.whenStable();
      expect(text()).toContain('Combine gently.');
    });

    it('sends the language being edited, not always English', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();

      click('Correct this page');
      await fixture.whenStable();
      const locale: HTMLSelectElement = fixture.nativeElement.querySelector('#locale');
      locale.value = 'de-CH';
      locale.dispatchEvent(new Event('change'));
      await fixture.whenStable();
      click('Save the page');
      await fixture.whenStable();

      backend.expectOne('/api/v1/academy/fold/wordings/de-CH').flush(FOLD);
    });

    it('keeps what was typed when saving fails', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();

      click('Correct this page');
      await fixture.whenStable();
      set('#summary', 'Combine gently.');
      await fixture.whenStable();
      click('Save the page');
      await fixture.whenStable();

      backend
        .expectOne('/api/v1/academy/fold/wordings/en-GB')
        .flush({}, { status: 500, statusText: 'Server Error' });
      await fixture.whenStable();

      expect(text()).toContain('Could not save');
      const summary: HTMLInputElement = fixture.nativeElement.querySelector('#summary');
      expect(summary.value).toBe('Combine gently.');
    });
  });

  describe('approving it', () => {
    const unchecked = { ...FOLD, origin: 'user', generated: true, approved: false };

    it('offers approval on a page nobody has checked', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(unchecked);
      await fixture.whenStable();
      expect(text()).toContain('Nobody here has checked it');
      expect(text()).toContain('Approve');
    });

    it('stops saying so once approved', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(unchecked);
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();
      backend.expectOne('/api/v1/academy/fold/approved').flush({ ...unchecked, approved: true });
      await fixture.whenStable();

      expect(text()).not.toContain('Nobody here has checked it');
    });

    it('offers nothing to approve on a page that is already checked', async () => {
      await arrive({ admin: true });
      backend.expectOne('/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).not.toContain('Approve');
    });
  });
});
