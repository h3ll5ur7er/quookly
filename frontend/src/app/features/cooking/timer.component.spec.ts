import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TimerView } from '@api';
import { TimerComponent } from './timer.component';

/**
 * The client ticks; the server holds the instants (ADR-013). So what is checked here is
 * that the same two numbers always produce the same clock, whenever they are read.
 */
describe('TimerComponent', () => {
  let fixture: ComponentFixture<TimerComponent>;

  function render(timer: TimerView | null, duration = 300): void {
    fixture.componentRef.setInput('duration', duration);
    fixture.componentRef.setInput('timer', timer);
    fixture.detectChanges();
  }

  function clock(): string {
    return fixture.nativeElement.querySelector('.timer__clock').textContent.trim();
  }

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [TimerComponent],
      providers: [provideZonelessChangeDetection()],
    });
    fixture = TestBed.createComponent(TimerComponent);
  });

  it('shows the step’s whole duration before anybody starts it', () => {
    render(null, 300);
    expect(clock()).toBe('5:00');
  });

  it('counts down from what a running timer has already had', () => {
    // Half a second past the minute, so the assertion is about the arithmetic rather than
    // about which side of a tick the test and the component's clock landed on.
    const started = new Date(Date.now() - 60_500).toISOString();
    render({ step_position: 0, running_since: started, elapsed_seconds: 0, duration_seconds: 300 });
    expect(clock()).toBe('4:00');
  });

  it('adds up what a paused timer counted across its runs', () => {
    // The door, then the phone. A timer that forgot either would send somebody back to a
    // pan four minutes early.
    render({ step_position: 0, running_since: null, elapsed_seconds: 240, duration_seconds: 300 });
    expect(clock()).toBe('1:00');
  });

  it('counts past zero rather than stopping there', () => {
    // A pan does not stop cooking because a timer ran out, and "+2:00" is the number a
    // cook coming back to it actually needs.
    render({ step_position: 0, running_since: null, elapsed_seconds: 420, duration_seconds: 300 });
    expect(clock()).toBe('+2:00');
  });

  it('says the time is up in words, not only in colour', () => {
    render({ step_position: 0, running_since: null, elapsed_seconds: 420, duration_seconds: 300 });
    expect(fixture.nativeElement.textContent).toContain('Time is up');
  });

  it('shows hours where a recipe has them', () => {
    render(null, 5400);
    expect(clock()).toBe('1:30:00');
  });

  it('offers to start a timer nobody has started', () => {
    render(null);
    expect(fixture.nativeElement.textContent).toContain('Start');
  });

  it('offers to pause a running one', () => {
    const started = new Date().toISOString();
    render({ step_position: 0, running_since: started, elapsed_seconds: 0, duration_seconds: 300 });
    expect(fixture.nativeElement.textContent).toContain('Pause');
  });

  it('announces the clock, because the cook is looking at a pan', () => {
    render(null);
    expect(fixture.nativeElement.querySelector('.timer__clock').getAttribute('role')).toBe(
      'status',
    );
  });
});
