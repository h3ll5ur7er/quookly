import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { HomeComponent } from './home.component';

const TODAY = new Date().toISOString().slice(0, 10);

function plan(overrides: object = {}): object {
  return {
    id: 3,
    starts_on: TODAY,
    ends_on: TODAY,
    slots: [],
    shopping: [],
    ...overrides,
  };
}

describe('HomeComponent', () => {
  let fixture: ComponentFixture<HomeComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  async function answering(soon: object[] = [], week: object = plan()): Promise<void> {
    backend.expectOne('/api/v1/pantry/using-soon').flush(soon);
    backend.expectOne('/api/v1/plans/current').flush(week);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function cards(): HTMLElement[] {
    return [...fixture.nativeElement.querySelectorAll('.card')];
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(HomeComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks its three questions whether or not it has answers', async () => {
    /* Home used to show only the cards that had something in them, so the ordinary
       weekday — a shelf with something on it and nothing planned — was one card and two
       thirds of an empty screen (H1). The questions are the page; the answers vary. */
    await answering();
    expect(text()).toContain('Use these first');
    expect(text()).toContain('On today');
    expect(text()).toContain('Still to buy');
    expect(cards().length).toBe(4);
  });

  it('answers a question it has no answer to, quietly', async () => {
    await answering();
    expect(text()).toContain('Nothing is about to go off');
    expect(text()).toContain('Nothing is planned for today');
    expect(text()).toContain('already in your kitchen');
  });

  it('does not mark a card urgent when nothing is', async () => {
    await answering();
    expect(fixture.nativeElement.querySelector('.card--urgent')).toBeNull();
  });

  it('marks the card that has a deadline', async () => {
    await answering([{ ingredient_id: 1, name: 'soured cream', total: '200 g' }]);
    expect(fixture.nativeElement.querySelector('.card--urgent')).not.toBeNull();
    expect(text()).toContain('soured cream');
  });

  it('offers what to do next, which is the third thing home is for', async () => {
    // "What wants eating, what is on tonight, what to do next" — only the first two were
    // ever on the screen (H1).
    await answering();
    const next = fixture.nativeElement.querySelector('.home__next');
    const hrefs = [...next.querySelectorAll('a')].map((a: HTMLAnchorElement) =>
      a.getAttribute('href'),
    );
    expect(hrefs).toEqual(['/recipes/new', '/plans', '/pantry/add']);
  });

  it('says what each card leads to, as something to press', async () => {
    // Bold red text with no chevron, underline or border is not an action (H2).
    await answering();
    for (const more of fixture.nativeElement.querySelectorAll('.card__more')) {
      expect(more.querySelector('.card__arrow')).not.toBeNull();
    }
  });

  it('greets in a line, and titles the page with the day instead', async () => {
    // The greeting was an `h1` taking a fifth of the viewport above the fold, and it is
    // the least useful thing on the screen after the first day (H3).
    await answering();
    expect(fixture.nativeElement.querySelector('.home__greeting').tagName).toBe('P');
    const heading = fixture.nativeElement.querySelector('h1').textContent.trim();
    expect(heading).not.toContain('Good');
    expect(heading.length).toBeGreaterThan(0);
  });
});
