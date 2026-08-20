import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Outcome, Severity, VerdictView } from '@api';
import { VerdictComponent } from './verdict.component';

describe('VerdictComponent', () => {
  let fixture: ComponentFixture<VerdictComponent>;

  function render(verdict: VerdictView): void {
    fixture.componentRef.setInput('verdict', verdict);
    fixture.detectChanges();
  }

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  function classes(): string {
    return fixture.nativeElement.querySelector('.verdict').className;
  }

  const finding = {
    eater: 'Mira',
    ingredient: 'peanut butter',
    severity: Severity.medical,
    allergen: null,
    avoidable: false,
    unknown: false,
  };

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [VerdictComponent],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(VerdictComponent);
  });

  it('names the outcome in words, not only in colour', () => {
    render({ outcome: Outcome.unsuitable, findings: [finding] });
    expect(text()).toContain('Not suitable');
  });

  it('names who and what, so the cook can act on it', () => {
    render({ outcome: Outcome.unsuitable, findings: [finding] });
    expect(text()).toContain('Mira');
    expect(text()).toContain('peanut butter');
  });

  it('says an ingredient was never checked rather than implying it is safe', () => {
    render({
      outcome: Outcome.unknown,
      findings: [{ ...finding, ingredient: 'mystery paste', unknown: true }],
    });
    expect(text()).toContain('Not enough is known');
    expect(text()).toContain('not checked for allergens');
  });

  it('does not dress unknown up as suitable', () => {
    /*
     * The distinction the whole safety path rests on. If unknown looked like suitable, a
     * cook would read "nobody has checked" as "checked and fine".
     */
    render({ outcome: Outcome.unknown, findings: [{ ...finding, unknown: true }] });
    expect(classes()).toContain('verdict--unknown');
    expect(classes()).not.toContain('verdict--suitable');
    expect(text()).not.toContain('Suits everyone');
  });

  it('tells a cook when leaving something out would fix it', () => {
    render({ outcome: Outcome.suitable, findings: [{ ...finding, avoidable: true }] });
    // Suitable with an avoidable finding: the reason is worth saying even so.
    render({ outcome: Outcome.caution, findings: [{ ...finding, avoidable: true }] });
    expect(text()).toContain('can be left out');
  });

  it('stays quiet when everything is fine', () => {
    render({ outcome: Outcome.suitable, findings: [] });
    expect(text()).toContain('Suits everyone');
    expect(fixture.nativeElement.querySelector('.verdict__findings')).toBeNull();
  });

  it('is announced as a status rather than interrupting as an alert', () => {
    render({ outcome: Outcome.unsuitable, findings: [finding] });
    expect(fixture.nativeElement.querySelector('[role="status"]')).not.toBeNull();
  });
});
