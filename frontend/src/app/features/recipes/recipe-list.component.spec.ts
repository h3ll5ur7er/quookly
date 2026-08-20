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
};

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
});
