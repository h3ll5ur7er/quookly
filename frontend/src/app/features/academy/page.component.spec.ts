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
  // The server answers this, rather than a screen re-deriving the three-part rule and
  // getting one part slightly wrong (ADR-060).
  may_rewrite: true,
  caution: null,
  also: [],
  entry: null,
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

  async function arrive({
    admin = false,
    signedIn = true,
    params = { slug: 'fold' } as Record<string, string>,
  } = {}): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [AcademyPageComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        { provide: AuthStore, useValue: { isAdmin: signal(admin), isSignedIn: signal(signedIn) } },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: { get: (key: string) => params[key] ?? null },
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
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).toContain('Combine without knocking out the air.');
    });

    it('offers a cook nothing to change', async () => {
      await arrive();
      // What the server sends somebody who may not: the rule has three parts and is
      // answered there rather than re-derived here (ADR-060).
      backend
        .expectOne((one) => one.url === '/api/v1/academy/fold')
        .flush({ ...FOLD, may_rewrite: false });
      await fixture.whenStable();
      expect(text()).not.toContain('Correct this page');
    });

    it('lets the author of a page nobody has read correct it', async () => {
      /* Not an administrator, and still offered it: an author who cannot fix their own
         typo will not write a second page. */
      await arrive();
      backend
        .expectOne((one) => one.url === '/api/v1/academy/fold')
        .flush({ ...FOLD, approved: false, may_rewrite: true });
      await fixture.whenStable();
      expect(text()).toContain('Correct this page');
    });

    it('says so when nobody has read the page yet', async () => {
      await arrive();
      backend
        .expectOne((one) => one.url === '/api/v1/academy/fold')
        .flush({ ...FOLD, approved: false, may_rewrite: true });
      await fixture.whenStable();
      expect(text()).toContain('not marked in recipes');
    });
  });

  describe('a word nobody has explained', () => {
    /* The only screen in the application that can produce something untrue, so it is the
       one that has to say what it is doing before and after (ADR-062). */
    async function arriveOnATerm(): Promise<void> {
      await arrive({ params: { term: 'spatchcock' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/terms/spatchcock').flush([]);
      await fixture.whenStable();
    }

    it('offers to ask, rather than stopping at the dead end', async () => {
      await arriveOnATerm();
      expect(text()).toContain('Ask for an explanation');
    });

    it('says who will have written it before anybody asks', async () => {
      await arriveOnATerm();
      expect(text()).toContain('written by a model');
    });

    it('asks, and shows what came back', async () => {
      await arriveOnATerm();
      click('Ask for an explanation');
      await fixture.whenStable();

      const sent = backend.expectOne((one) => one.url === '/api/v1/academy/explanations');
      expect(sent.request.method).toBe('POST');
      expect(sent.request.body.term).toBe('spatchcock');
      sent.flush({
        ...FOLD,
        slug: 'spatchcock',
        name: 'spatchcock',
        summary: 'Flatten a bird so it cooks evenly.',
        generated: true,
        approved: false,
      });
      await fixture.whenStable();

      expect(text()).toContain('Flatten a bird so it cooks evenly.');
      // Marked, because a page a model wrote must not read like one somebody wrote.
      expect(text()).toContain('Nobody here has checked it');
    });

    it('says plainly when the instance has no model to ask', async () => {
      await arriveOnATerm();
      click('Ask for an explanation');
      await fixture.whenStable();

      backend
        .expectOne((one) => one.url === '/api/v1/academy/explanations')
        .flush(
          { detail: 'Nobody has explained that yet, and this instance has no model to ask.' },
          { status: 422, statusText: 'Unprocessable Content' },
        );
      await fixture.whenStable();

      expect(text()).toContain('no model to ask');
    });

    it('offers nothing to ask with on a page that simply is not there', async () => {
      /* A slug nobody wrote is a broken link, not an unexplained word. */
      await arrive({ params: { slug: 'nothing-of-the-sort' } });
      backend
        .expectOne((one) => one.url === '/api/v1/academy/nothing-of-the-sort')
        .flush({}, { status: 404, statusText: 'Not Found' });
      await fixture.whenStable();
      expect(text()).not.toContain('Ask for an explanation');
    });
  });

  describe('a page about a food', () => {
    /* The facts are the registry's, read rather than copied (ADR-061). The screen's job is
       to show them without ever turning "nobody has looked" into "contains none". */
    const FLOUR = {
      ...FOLD,
      slug: 'about-plain-flour',
      kind: 'ingredient',
      entry: {
        slug: 'plain-flour',
        name: 'plain flour',
        kind: 'powder',
        allergens: ['gluten'],
        classified: true,
        density: null,
        piece_grams: null,
        has_nutrition: true,
      },
    };

    it('shows what the registry knows about the food', async () => {
      await arrive({ params: { slug: 'about-plain-flour' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/about-plain-flour').flush(FLOUR);
      await fixture.whenStable();
      expect(text()).toContain('gluten');
    });

    it('says nobody has looked rather than showing an empty list', async () => {
      /* The ADR-006 failure with better typography: a reader seeing no allergens on a
         food nobody has examined reads that as "contains none". */
      await arrive({ params: { slug: 'about-plain-flour' } });
      backend
        .expectOne((one) => one.url === '/api/v1/academy/about-plain-flour')
        .flush({ ...FLOUR, entry: { ...FLOUR.entry, allergens: [], classified: false } });
      await fixture.whenStable();

      expect(text()).toContain('Nobody has classified');
      expect(text()).not.toContain('None');
    });

    it('says so plainly when a classified food contains none of them', async () => {
      await arrive({ params: { slug: 'about-plain-flour' } });
      backend
        .expectOne((one) => one.url === '/api/v1/academy/about-plain-flour')
        .flush({ ...FLOUR, entry: { ...FLOUR.entry, allergens: [], classified: true } });
      await fixture.whenStable();

      expect(text()).toContain('None of the fourteen');
    });

    it('leads to the registry entry, where the facts are corrected', async () => {
      await arrive({ params: { slug: 'about-plain-flour' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/about-plain-flour').flush(FLOUR);
      await fixture.whenStable();

      const link: HTMLAnchorElement = fixture.nativeElement.querySelector('.academy__entry a');
      expect(link.getAttribute('href')).toBe('/settings/registry/plain-flour');
    });

    it('shows nothing of the sort on a technique page', async () => {
      await arrive();
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelector('.academy__entry')).toBeNull();
    });
  });

  describe('correcting it', () => {
    it('arrives filled in with what the page says', async () => {
      await arrive({ admin: true });
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
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
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
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
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
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
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
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
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(unchecked);
      await fixture.whenStable();
      expect(text()).toContain('Nobody here has checked it');
      expect(text()).toContain('Approve');
    });

    it('stops saying so once approved', async () => {
      await arrive({ admin: true });
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(unchecked);
      await fixture.whenStable();

      click('Approve');
      await fixture.whenStable();
      backend.expectOne('/api/v1/academy/fold/approved').flush({ ...unchecked, approved: true });
      await fixture.whenStable();

      expect(text()).not.toContain('Nobody here has checked it');
    });

    it('offers nothing to approve on a page that is already checked', async () => {
      await arrive({ admin: true });
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).not.toContain('Approve');
    });
  });

  describe('to somebody with no account', () => {
    /* A stranger is shown the page and nothing that leads where they cannot go: no
       correcting, no asking a model, and no link into the household's registry
       (ADR-063). */
    const FLOUR = {
      ...FOLD,
      slug: 'about-plain-flour',
      kind: 'ingredient',
      may_rewrite: false,
      entry: {
        slug: 'plain-flour',
        name: 'plain flour',
        kind: 'powder',
        allergens: ['gluten'],
        classified: true,
        density: null,
        piece_grams: null,
        has_nutrition: true,
      },
    };

    it('reads the page', async () => {
      await arrive({ signedIn: false });
      backend.expectOne((one) => one.url === '/api/v1/academy/fold').flush(FOLD);
      await fixture.whenStable();
      expect(text()).toContain('Combine without knocking out the air.');
    });

    it('still sees what the kitchen knows about a food', async () => {
      /* Generic food data, not the household's. The link to correct it is the private
         part, not the figures. */
      await arrive({ signedIn: false, params: { slug: 'about-plain-flour' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/about-plain-flour').flush(FLOUR);
      await fixture.whenStable();
      expect(text()).toContain('gluten');
    });

    it('is not sent to a registry screen it cannot open', async () => {
      await arrive({ signedIn: false, params: { slug: 'about-plain-flour' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/about-plain-flour').flush(FLOUR);
      await fixture.whenStable();
      expect(fixture.nativeElement.querySelector('.academy__entry a')).toBeNull();
    });

    it("is not offered a model to spend somebody else's money on", async () => {
      await arrive({ signedIn: false, params: { term: 'spatchcock' } });
      backend.expectOne((one) => one.url === '/api/v1/academy/terms/spatchcock').flush([]);
      await fixture.whenStable();

      expect(text()).toContain('Nobody has explained that yet');
      expect(text()).not.toContain('Ask for an explanation');
    });
  });
});
