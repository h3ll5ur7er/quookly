import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { PictureComponent } from './picture.component';

describe('PictureComponent', () => {
  let backend: HttpTestingController;

  function show(mediaId: string, description: string) {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [PictureComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    });
    const fixture = TestBed.createComponent(PictureComponent);
    fixture.componentRef.setInput('mediaId', mediaId);
    fixture.componentRef.setInput('description', description);
    backend = TestBed.inject(HttpTestingController);
    return fixture;
  }

  it('fetches the bytes rather than pointing an img at the endpoint', async () => {
    // The endpoint wants the bearer token, and an `<img src>` does not carry one.
    const fixture = show('abc', 'Carrot cut into matchsticks.');
    await fixture.whenStable();
    const asked = backend.expectOne('/api/v1/media/abc');
    expect(asked.request.responseType).toBe('blob');
    asked.flush(new Blob(['bytes'], { type: 'image/webp' }));
  });

  it('gives the picture the alt text it was handed', async () => {
    const fixture = show('abc', 'Carrot cut into matchsticks.');
    await fixture.whenStable();
    backend.expectOne('/api/v1/media/abc').flush(new Blob(['bytes'], { type: 'image/webp' }));
    await fixture.whenStable();
    fixture.detectChanges();
    const image: HTMLImageElement = fixture.nativeElement.querySelector('img');
    expect(image.alt).toBe('Carrot cut into matchsticks.');
  });

  it('says so rather than showing a broken image', async () => {
    const fixture = show('abc', 'Carrot cut into matchsticks.');
    await fixture.whenStable();
    backend.expectOne('/api/v1/media/abc').flush(null, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('could not be loaded');
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
  });
});
