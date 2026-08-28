import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { TranslateRecipeComponent } from './translate-recipe.component';

const DRAFT = {
  locale: 'en',
  by_hand: false,
  current: true,
  title: 'Chocolate cake',
  summary: 'A simple cake.',
  steps: ['Cream the butter and sugar.', 'Bake at 180 C.'],
  source: {
    title: 'Schokoladenkuchen',
    summary: 'Ein einfacher Kuchen.',
    steps: ['Butter und Zucker schaumig rühren.', 'Bei 180 °C backen.'],
  },
  source_language: 'de',
};

/**
 * Correcting a translation (ADR-064).
 *
 * The screen exists because a model's German is a starting point and the cook who wrote
 * the recipe knows what it says. Two things make it more than a form: the author's words
 * sit beside every field, because proof-reading a language without the original is
 * guessing — and a correction of sentences that have since moved is the *only* thing this
 * screen can show, since it is kept and deliberately not shown anywhere else.
 */
describe('TranslateRecipeComponent', () => {
  let fixture: ComponentFixture<TranslateRecipeComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function settle(): Promise<void> {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  async function open(draft: object | null = DRAFT, status = 200): Promise<void> {
    const asked = backend.expectOne('/api/v1/recipes/7/translations/en');
    if (status === 200) {
      asked.flush(draft);
    } else {
      asked.flush({}, { status, statusText: 'Not Found' });
    }
    await settle();
  }

  function value(selector: string): string {
    return (fixture.nativeElement.querySelector(selector) as HTMLInputElement).value;
  }

  function type(selector: string, into: string): void {
    const field: HTMLInputElement = fixture.nativeElement.querySelector(selector);
    field.value = into;
    field.dispatchEvent(new Event('input'));
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [TranslateRecipeComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: new Map([
                ['id', '7'],
                ['locale', 'en'],
              ]),
            },
          },
        },
      ],
    });
    fixture = TestBed.createComponent(TranslateRecipeComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('fills the form with the translation as it stands', async () => {
    await open();
    expect(value('#title')).toBe('Chocolate cake');
    expect(value('#step-0')).toBe('Cream the butter and sugar.');
  });

  it('puts the author’s own words beside every field', async () => {
    // Proof-reading a translation without the original is guessing at it.
    await open();
    expect(text()).toContain('Schokoladenkuchen');
    expect(text()).toContain('Butter und Zucker schaumig rühren.');
  });

  it('says whose words these currently are', async () => {
    await open();
    expect(text()).toContain('A machine wrote this');
  });

  it('says so instead when somebody here wrote them', async () => {
    await open({ ...DRAFT, by_hand: true });
    expect(text()).not.toContain('A machine wrote this');
  });

  it('sends the corrected words', async () => {
    await open();
    type('#title', 'Chocolate cake, properly');
    await settle();

    fixture.nativeElement.querySelector('form').requestSubmit();
    await settle();

    const sent = backend.expectOne('/api/v1/recipes/7/translations/en');
    expect(sent.request.method).toBe('PUT');
    expect(sent.request.body).toEqual({
      title: 'Chocolate cake, properly',
      summary: 'A simple cake.',
      steps: ['Cream the butter and sugar.', 'Bake at 180 C.'],
    });
    sent.flush({ ...DRAFT, by_hand: true, title: 'Chocolate cake, properly' });
    await settle();
  });

  it('warns when the recipe has moved under the words', async () => {
    /* Kept and not shown, which means this screen is the only place these words exist at
       all. A cook who cannot see that would think the translation was live (ADR-064). */
    await open({ ...DRAFT, by_hand: true, current: false });
    expect(text()).toContain('The recipe has changed');
  });

  it('says nothing about that when the two still agree', async () => {
    await open();
    expect(text()).not.toContain('The recipe has changed');
  });

  it('says there is nothing to correct rather than showing an empty form', async () => {
    await open(null, 404);
    expect(text()).toContain('Nothing to correct');
    expect(fixture.nativeElement.querySelector('form')).toBeNull();
  });

  it('reports a refusal rather than pretending it saved', async () => {
    await open();
    fixture.nativeElement.querySelector('form').requestSubmit();
    await settle();
    backend
      .expectOne('/api/v1/recipes/7/translations/en')
      .flush({}, { status: 500, statusText: 'Server Error' });
    await settle();
    expect(text()).toContain('Could not save');
  });

  it('leads back to the recipe it is a translation of', async () => {
    await open();
    const back: HTMLAnchorElement = fixture.nativeElement.querySelector('.translate__back');
    expect(back.getAttribute('href')).toBe('/recipes/7');
  });
});
