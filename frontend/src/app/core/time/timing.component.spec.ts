import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TimingView } from '@api';
import { TimingComponent } from './timing.component';

describe('TimingComponent', () => {
  let fixture: ComponentFixture<TimingComponent>;

  function render(timing: TimingView): void {
    fixture.componentRef.setInput('timing', timing);
    fixture.detectChanges();
  }

  function text(): string {
    return fixture.nativeElement.textContent;
  }

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [TimingComponent],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(TimingComponent);
  });

  it('gives the work and the clock as two separate answers', () => {
    render({
      hands_on: { seconds: 900, at_least: false },
      total: { seconds: 6600, at_least: false },
      ahead: null,
    });
    expect(text()).toContain('15 min');
    expect(text()).toContain('hands-on');
    expect(text()).toContain('1 h 50 min');
    expect(text()).toContain('total');
  });

  it('says when a number is only the floor', () => {
    // A step that gave no duration does not make the recipe shorter. Printed bare, this
    // is a number somebody plans an evening around.
    render({
      hands_on: { seconds: 900, at_least: true },
      total: { seconds: 900, at_least: true },
      ahead: null,
    });
    expect(text()).toContain('at least 15 min');
  });

  it('asks for work done the day before as an instruction, not a third total', () => {
    render({
      hands_on: { seconds: 600, at_least: false },
      total: { seconds: 600, at_least: false },
      ahead: { seconds: 28800, at_least: false },
    });
    expect(text()).toContain('Start 8 h ahead');
    // And it stays out of the total: ten minutes of work is still a ten-minute evening.
    expect(text()).not.toContain('8 h 10 min');
  });

  it('shows only the number it has', () => {
    // Only the baking was timed. "0 min hands-on" would say the cake makes itself.
    render({ hands_on: null, total: { seconds: 2700, at_least: true }, ahead: null });
    expect(text()).not.toContain('hands-on');
    expect(text()).toContain('at least 45 min');
  });

  it('rounds to the minute a cook reads rather than the second a timer counts', () => {
    render({ hands_on: { seconds: 3600, at_least: false }, total: null, ahead: null });
    expect(text()).toContain('1 h');
    expect(text()).not.toContain('60 min');
  });
});
