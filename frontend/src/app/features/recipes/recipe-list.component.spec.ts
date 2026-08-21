import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideApi } from '@api';
import { RecipeListComponent } from './recipe-list.component';

const PANCAKES = {
  id: 1,
  title: 'Pancakes',
  summary: 'Batter, pan, patience.',
  yield_quantity: { magnitude: '12', unit: 'piece', display: '12 piece' },
  visibility: 'private',
  suitability: null,
};

function judged(suitability: string | null) {
  return [{ ...PANCAKES, suitability }];
}

describe('RecipeListComponent', () => {
  let fixture: ComponentFixture<RecipeListComponent>;
  let backend: HttpTestingController;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [RecipeListComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(RecipeListComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('asks for the cook’s recipes', () => {
    backend.expectOne('/api/v1/recipes').flush([]);
  });

  it('shows what it finds', async () => {
    backend.expectOne('/api/v1/recipes').flush([PANCAKES]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('Pancakes');
    expect(text()).toContain('12 piece');
  });

  it('offers a way in for each recipe', async () => {
    backend.expectOne('/api/v1/recipes').flush([PANCAKES]);
    await fixture.whenStable();
    fixture.detectChanges();
    const link = fixture.nativeElement.querySelector('a[href="/recipes/1"]');
    expect(link).not.toBeNull();
  });

  it('says so plainly when there is nothing yet', async () => {
    backend.expectOne('/api/v1/recipes').flush([]);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(text()).toContain('No recipes yet');
  });

  it('reports a failure rather than showing an empty kitchen', async () => {
    backend.expectOne('/api/v1/recipes').flush({}, { status: 500, statusText: 'Server Error' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  });

  async function show(body: unknown[]): Promise<void> {
    backend.expectOne('/api/v1/recipes').flush(body);
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('marks a recipe somebody cannot eat', async () => {
    await show(judged('unsuitable'));
    expect(text()).toContain('Not suitable');
  });

  it('marks a recipe nobody has checked, rather than leaving it bare', async () => {
    /*
     * A bare row means "fine" once a cook has learnt the pattern. Unknown is not fine,
     * and this is the screen where they decide what to open.
     */
    await show(judged('unknown'));
    expect(text()).toContain('Not checked');
  });

  it('says nothing about a recipe that suits everybody', async () => {
    // Twenty ticks would drown the one warning that matters.
    await show(judged('suitable'));
    expect(fixture.nativeElement.querySelector('.badge')).toBeNull();
  });

  it('carries a word beside the colour', async () => {
    await show(judged('caution'));
    expect(text()).toContain('Take care');
  });

  it('explains an unbadged list when there is nobody to judge against', async () => {
    await show(judged(null));
    expect(text()).toContain('Nobody recorded yet');
    expect(fixture.nativeElement.querySelector('a[href="/household"]')).not.toBeNull();
  });

  it('does not nag once there is somebody to judge against', async () => {
    await show(judged('suitable'));
    expect(text()).not.toContain('Nobody recorded yet');
  });
});
