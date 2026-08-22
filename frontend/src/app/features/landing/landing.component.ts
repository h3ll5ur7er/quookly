import { NgOptimizedImage } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * The front door (UC-10.6).
 *
 * What a visitor sees at `/` before they have an account. It exists because there was
 * nothing here: a stranger arriving at somebody's Quookly got a sign-in form and no
 * indication of what they were signing in to.
 *
 * The claims are the ones the product actually makes, in the order somebody would judge
 * them. No screenshots: they age, and the promise here is about *less* on a screen, which
 * a screenshot of a screen is a poor way to make.
 */
@Component({
  selector: 'app-landing',
  imports: [NgOptimizedImage, RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {}
