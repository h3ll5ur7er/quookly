import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { ImportRecipeComponent } from './import-recipe.component';

const IMPORTED = {
  recipe: {
    id: 7,
    title: 'Classic pancakes',
    summary: null,
    yield_quantity: { magnitude: '8', unit: 'piece', display: '8 piece' },
    visibility: 'private',
    provenance: 'imported_url',
    lines: [
      { ingredient: 'plain flour', quantity: null, preparation: null, optional: false },
      { ingredient: 'whole milk', quantity: null, preparation: null, optional: false },
    ],
    steps: [{ position: 0, instruction: 'Whisk.' }],
    suitability: null,
  },
  read_from: 'metadata',
  source_url: 'https://example.com/pancakes',
  ingredients_added: [],
};

describe('ImportRecipeComponent', () => {
  let fixture: ComponentFixture<ImportRecipeComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function field(): HTMLInputElement {
    return fixture.nativeElement.querySelector('#url');
  }

  async function paste(url: string): Promise<void> {
    field().value = url;
    field().dispatchEvent(new Event('input'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function submit(): Promise<void> {
    fixture.nativeElement.querySelector('button[type="submit"]').click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [ImportRecipeComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(ImportRecipeComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    fixture.detectChanges();
  });

  afterEach(() => backend.verify());

  describe('what it will send', () => {
    it('sends the pasted address', async () => {
      await paste('https://example.com/pancakes');
      await submit();
      const request = backend.expectOne('/api/v1/recipes/import-url');
      expect(request.request.body).toEqual({ url: 'https://example.com/pancakes' });
      request.flush(IMPORTED);
    });

    it('will not send an empty box', async () => {
      await submit();
      backend.expectNone(() => true);
    });

    it('will not send something that is not a web address', async () => {
      /* The API refuses it too, but a round trip to be told so is a wasted half-minute. */
      await paste('my pancake recipe');
      await submit();
      backend.expectNone(() => true);
    });

    it('will not send twice while it is already reading', async () => {
      await paste('https://example.com/pancakes');
      await submit();
      await submit();
      backend.expectOne('/api/v1/recipes/import-url').flush(IMPORTED);
    });
  });

  describe('while it is reading', () => {
    it('says that it is, and why it may take a moment', async () => {
      /* A model reading a page takes the better part of half a minute. A cook watching an
         unexplained animation for that long concludes it is broken. */
      await paste('https://example.com/pancakes');
      await submit();
      expect(text()).toContain('Reading the page');
      expect(text()).toContain('takes a little longer');
      backend.expectOne('/api/v1/recipes/import-url').flush(IMPORTED);
      await settle();
    });

    it('announces the wait as progress rather than a problem', async () => {
      await paste('https://example.com/pancakes');
      await submit();
      expect(fixture.nativeElement.querySelector('[role="status"]')).not.toBeNull();
      expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
      backend.expectOne('/api/v1/recipes/import-url').flush(IMPORTED);
      await settle();
    });
  });

  describe('when it works', () => {
    async function importing(body: object = IMPORTED): Promise<void> {
      await paste('https://example.com/pancakes');
      await submit();
      backend.expectOne('/api/v1/recipes/import-url').flush(body);
      await settle();
    }

    it('says what it got', async () => {
      await importing();
      expect(text()).toContain('Classic pancakes');
      expect(text()).toContain('2');
    });

    it('offers a way into the recipe', async () => {
      await importing();
      expect(fixture.nativeElement.querySelector('a[href="/recipes/7"]')).not.toBeNull();
    });

    it('says nothing about a model when the page published its own data', async () => {
      await importing();
      expect(text()).not.toContain('read through by a model');
    });

    it('says so when a model had to read it', async () => {
      /* Worth knowing before cooking from it: this is the fallible path. */
      await importing({ ...IMPORTED, read_from: 'model' });
      expect(text()).toContain('read through by a model');
    });

    it('names ingredients it had never seen', async () => {
      /* The part a cook has to act on. Nothing is known about a new entry's allergens, so
         every recipe using one reads as unknown until somebody looks. */
      await importing({ ...IMPORTED, ingredients_added: ['buttermilk', 'oil'] });
      expect(text()).toContain('buttermilk');
      expect(text()).toContain('oil');
      expect(text()).toContain('nothing is known about what they contain');
    });

    it('says nothing about new ingredients when there were none', async () => {
      await importing();
      expect(text()).not.toContain('nothing is known about what they contain');
    });

    it('clears the box, so the next paste starts clean', async () => {
      await importing();
      expect(field().value).toBe('');
    });
  });

  describe('when it does not work', () => {
    async function failing(detail: string | undefined, status = 422): Promise<void> {
      await paste('https://example.com/pancakes');
      await submit();
      backend
        .expectOne('/api/v1/recipes/import-url')
        .flush({ detail }, { status, statusText: 'Unprocessable' });
      await settle();
    }

    it('shows what the API said, because the API says something useful', async () => {
      /* "That site will not serve an automated reader, but the page works in your browser"
         is the only part of a failure a cook can act on. Flattening it into "that did not
         work" throws exactly that away. */
      await failing(
        'That site will not serve an automated reader. The page works in your browser.',
      );
      expect(text()).toContain('works in your browser');
    });

    it('announces a failure rather than leaving it to be noticed', async () => {
      await failing('No recipe was found on that page.');
      expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    });

    it('falls back to something plain when the API said nothing useful', async () => {
      await failing(undefined, 500);
      expect(text()).toContain('That did not work');
    });

    it('stops saying it is reading', async () => {
      await failing('No recipe was found on that page.');
      expect(text()).not.toContain('Reading the page');
    });

    it('lets the cook try again', async () => {
      await failing('No recipe was found on that page.');
      await paste('https://example.com/other');
      await submit();
      backend.expectOne('/api/v1/recipes/import-url').flush(IMPORTED);
      await settle();
      expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    });
  });
});
