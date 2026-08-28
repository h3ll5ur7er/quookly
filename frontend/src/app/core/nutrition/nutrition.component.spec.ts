import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NutritionView } from '@api';
import { NutritionComponent } from './nutrition.component';

function figure(nutrient: string, amount: string, unit = 'g') {
  return { nutrient, amount, unit } as never;
}

const CREDIT = {
  name: 'Swiss Food Composition Database',
  publisher: 'Federal Food Safety and Veterinary Office (FSVO)',
  licence: 'Open use. Must provide the source.',
  url: 'https://naehrwertdaten.ch/',
};

function panel(overrides: Partial<NutritionView> = {}): NutritionView {
  return {
    per_serving: [figure('energy_kcal', '349', 'kcal'), figure('fat', '19.4')],
    per_recipe: [figure('energy_kcal', '2792', 'kcal'), figure('fat', '155.2')],
    at_least: false,
    uncounted: [],
    credits: [CREDIT],
    ...overrides,
  } as NutritionView;
}

describe('NutritionComponent', () => {
  let fixture: ComponentFixture<NutritionComponent>;

  function render(view: NutritionView): void {
    fixture.componentRef.setInput('nutrition', view);
    fixture.detectChanges();
  }

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [NutritionComponent],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(NutritionComponent);
  });

  it('gives a plate and a tray, one at a time', () => {
    /* Two columns of figures plus a label are wider than a phone — 429 px in a 412 px
       viewport, so the right one was clipped and the two numbers ran together (D7). A cook
       is asking one of the two questions at a time anyway. */
    render(panel());
    expect(text()).toContain('Per serving');
    expect(text()).toContain('Whole recipe');

    // The plate first: it is the number that means something on a recipe making twelve.
    expect(text()).toContain('349 kcal');
    expect(text()).not.toContain('2792 kcal');
  });

  it('shows the tray when the tray is asked for', () => {
    render(panel());
    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('.nutrition__which button'),
    );
    buttons.find((one) => one.textContent?.includes('Whole recipe'))!.click();
    fixture.detectChanges();

    expect(text()).toContain('2792 kcal');
    expect(text()).not.toContain('349 kcal');
  });

  it('says which of the two is being shown', () => {
    render(panel());
    const plate: HTMLButtonElement = fixture.nativeElement.querySelector(
      '.nutrition__which button',
    );
    expect(plate.getAttribute('aria-pressed')).toBe('true');
  });

  it('drops the serving column where the recipe does not say how many it feeds', () => {
    // How much is in the tray is knowable; how much is on a plate is not (ADR-030).
    render(panel({ per_serving: null }));
    expect(text()).not.toContain('Per serving');
    expect(text()).toContain('Whole recipe');
  });

  it('reads in the order a packet reads', () => {
    render(
      panel({
        per_serving: null,
        per_recipe: [
          figure('protein', '4.5'),
          figure('energy_kj', '1460', 'kJ'),
          figure('saturates', '11.9'),
          figure('fat', '19.4'),
        ],
      }),
    );
    const names = [...fixture.nativeElement.querySelectorAll('tbody th')].map((node: Element) =>
      node.textContent!.trim(),
    );
    expect(names).toEqual(['Energy', 'Fat', 'of which saturates', 'Protein']);
  });

  it('sets saturates under the fat it is part of', () => {
    render(panel({ per_recipe: [figure('fat', '19.4'), figure('saturates', '11.9')] }));
    const indented = fixture.nativeElement.querySelectorAll('.nutrition__of-which');
    expect(indented.length).toBe(1);
    expect(indented[0].textContent).toContain('saturates');
  });

  it('names what could not be counted rather than counting it', () => {
    // "Two ingredients missing" tells a cook nothing they can act on.
    render(panel({ at_least: true, uncounted: ['baking powder', 'egg'] }));
    expect(text()).toContain('At least this much');
    expect(text()).toContain('baking powder, egg');
  });

  it('says so when there is nothing at all rather than showing an empty table', () => {
    render(panel({ per_serving: null, per_recipe: [], at_least: true, uncounted: ['starter'] }));
    expect(text()).toContain('This could not be worked out');
    expect(fixture.nativeElement.querySelector('table')).toBeNull();
  });

  it('credits whoever measured it', () => {
    // Mandatory under the Swiss grant, which is why it is a requirement (FR-20).
    render(panel());
    const credit = fixture.nativeElement.querySelector('.nutrition__credit a');
    expect(credit.textContent).toContain('Federal Food Safety and Veterinary Office');
    expect(credit.getAttribute('href')).toBe('https://naehrwertdaten.ch/');
  });

  it('credits every table that answered', () => {
    render(panel({ credits: [CREDIT, { ...CREDIT, publisher: 'USDA', url: 'https://fdc/' }] }));
    expect(fixture.nativeElement.querySelectorAll('.nutrition__credit a').length).toBe(2);
  });

  it('prints energy on one line, as a label does', () => {
    // Two rows both labelled "Energy" read as two different facts.
    render(
      panel({
        per_serving: null,
        per_recipe: [figure('energy_kj', '1460', 'kJ'), figure('energy_kcal', '349', 'kcal')],
      }),
    );
    const names = [...fixture.nativeElement.querySelectorAll('tbody th')].map((node: Element) =>
      node.textContent!.trim(),
    );
    expect(names).toEqual(['Energy']);
    expect(text()).toContain('1460 kJ / 349 kcal');
  });

  it('prints whichever of the two a table published', () => {
    render(panel({ per_serving: null, per_recipe: [figure('energy_kcal', '349', 'kcal')] }));
    expect(text()).toContain('349 kcal');
    expect(text()).not.toContain('/');
  });
});
