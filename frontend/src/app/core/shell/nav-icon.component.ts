import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Section } from './sections';

/**
 * The mark beside a destination's name.
 *
 * Drawn rather than typed. These were five text characters — `◆ ☰ ▤ ✓ ▦` — and a diamond
 * for Home and a grid square for Pantry mean nothing on their own; worse, they read as a
 * font that failed to load, on the one piece of furniture that is on every screen (X3).
 *
 * One stroke weight, one grid, no fills: a set rather than five separate drawings. They
 * take their colour from the link, so "where you are" is still said by the whole row.
 */
@Component({
  selector: 'app-nav-icon',
  host: { 'aria-hidden': 'true' },
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.75"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      @switch (name()) {
        @case ('home') {
          <!-- A roof and a door: the place you come back to. -->
          <path d="M3.5 10.6 12 4l8.5 6.6" />
          <path d="M6 9.8V20h12V9.8" />
          <path d="M10 20v-5h4v5" />
        }
        @case ('recipes') {
          <!-- An open book, because that is what a collection of recipes is. -->
          <path
            d="M12 7c-1.6-1.6-4.2-2.2-8-1.8v13c3.8-.4 6.4.2 8 1.8 1.6-1.6 4.2-2.2 8-1.8v-13c-3.8-.4-6.4.2-8 1.8Z"
          />
          <path d="M12 7v13" />
        }
        @case ('plan') {
          <!-- A calendar: the week, which is what the plan is a week of. -->
          <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" />
          <path d="M3.5 10.5h17" />
          <path d="M8.5 3.5v4M15.5 3.5v4" />
        }
        @case ('shopping') {
          <!-- A basket, held by the handle a cook holds it by. -->
          <path d="M3.5 9.5h17l-1.7 9.4a2 2 0 0 1-2 1.6H7.2a2 2 0 0 1-2-1.6L3.5 9.5Z" />
          <path d="M8.8 9.5 11 3.8M15.2 9.5 13 3.8" />
        }
        @case ('pantry') {
          <!-- A jar with a lid: what a shelf of kept food actually looks like. -->
          <path d="M8.5 3.5h7v3h-7z" />
          <path
            d="M7 9.5a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v8a3.5 3.5 0 0 1-3.5 3.5h-3A3.5 3.5 0 0 1 7 17.5v-8Z"
          />
          <path d="M7 12.5h10" />
        }
        @case ('academy') {
          <!-- A mortarboard: the one section that is read rather than cooked. -->
          <path d="M12 4 2.5 8.5 12 13l9.5-4.5L12 4Z" />
          <path d="M6.5 10.7v4.8c0 1.7 2.5 3 5.5 3s5.5-1.3 5.5-3v-4.8" />
        }
      }
    </svg>
  `,
  styles: `
    :host {
      display: block;
    }

    svg {
      display: block;
      inline-size: 100%;
      block-size: 100%;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NavIconComponent {
  readonly name = input.required<Section['name']>();
}
