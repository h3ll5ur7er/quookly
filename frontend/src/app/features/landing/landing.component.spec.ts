import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { LandingComponent } from './landing.component';

describe('LandingComponent', () => {
  let fixture: ComponentFixture<LandingComponent>;

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  beforeEach(async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    fixture = TestBed.createComponent(LandingComponent);
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('says what Quookly is before asking for anything', () => {
    // A stranger arriving at somebody's instance used to get a password field and no
    // indication of what they were signing in to.
    expect(text()).toContain('The recipe');
    expect(fixture.nativeElement.querySelector('input')).toBeNull();
  });

  it('offers both doors', () => {
    const links = [...fixture.nativeElement.querySelectorAll('a')].map((a: HTMLAnchorElement) =>
      a.getAttribute('href'),
    );
    expect(links).toContain('/apply');
    expect(links).toContain('/sign-in');
  });

  it('says whose instance this is here, not on the next screen', () => {
    // Somebody who taps "ask" and only then learns they must wait for a stranger has been
    // surprised by the product.
    expect(text()).toContain('belongs to somebody');
  });

  it('is honest about being self-hosted', () => {
    expect(text()).toContain('self-hosted');
  });

  it('has one heading at the top of the document, and the rest below it', () => {
    // A landing page is where heading order is most often thrown away for looks.
    const levels = [...fixture.nativeElement.querySelectorAll('h1, h2, h3')].map(
      (node: Element) => node.tagName,
    );
    expect(levels[0]).toBe('H1');
    expect(levels.filter((tag) => tag === 'H1')).toHaveLength(1);
  });
});
