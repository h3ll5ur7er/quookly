import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideApi } from '@api';
import { AcademyComponent } from './academy.component';

/**
 * The Academy's front page: the sections, what is waiting to be read, and the way in.
 *
 * The lookup exists because a word nobody has explained is a word no recipe underlines —
 * so without it the screen that says "nobody has explained that yet" cannot be reached at
 * all, and neither can asking for one (ADR-062).
 */
describe('AcademyComponent', () => {
  let fixture: ComponentFixture<AcademyComponent>;
  let backend: HttpTestingController;

  const PAGES = [
    {
      slug: 'blanch',
      kind: 'technique',
      name: 'blanch',
      summary: 'Into boiling water.',
      approved: true,
    },
    {
      slug: 'about-plain-flour',
      kind: 'ingredient',
      name: 'plain flour',
      summary: 'The everyday one.',
      approved: false,
    },
  ];

  const text = () => fixture.nativeElement.textContent as string;

  const click = (name: string) => {
    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    buttons.find((one) => one.textContent?.trim().includes(name))!.click();
  };

  async function arrive(pages: unknown[] = PAGES): Promise<void> {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [AcademyComponent],
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideApi(''),
      ],
    });
    fixture = TestBed.createComponent(AcademyComponent);
    backend = TestBed.inject(HttpTestingController);
    await fixture.whenStable();
    backend.expectOne((one) => one.url === '/api/v1/academy').flush(pages);
    await fixture.whenStable();
  }

  afterEach(() => backend.verify());

  it('lists what the Academy explains', async () => {
    await arrive();
    expect(text()).toContain('blanch');
  });

  it('separates what nobody has read yet', async () => {
    await arrive();
    expect(text()).toContain('Waiting to be read');
    expect(text()).toContain('plain flour');
  });

  it('narrows to one section', async () => {
    await arrive();
    click('Ingredients');
    await fixture.whenStable();
    expect(text()).not.toContain('blanch');
  });

  it('takes a word straight to what claims it', async () => {
    await arrive();
    // After `arrive`, not before: it resets the testing module, so a spy taken earlier is
    // on a router this component never sees.
    const went = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);

    const box: HTMLInputElement = fixture.nativeElement.querySelector('#lookup');
    box.value = 'spatchcock';
    box.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    click('Look it up');
    await fixture.whenStable();

    expect(went).toHaveBeenCalledWith(['/academy', 'terms', 'spatchcock']);
  });

  it('will not look up nothing', async () => {
    await arrive();
    const look: HTMLButtonElement = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('button'),
    ).find((one) => one.textContent?.includes('Look it up'))!;
    expect(look.disabled).toBe(true);
  });
});
