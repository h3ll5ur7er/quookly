import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  ActivatedRoute,
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { filter, map, startWith } from 'rxjs';
import { AuthStore } from './core/auth/auth.store';
import { LocalePickerComponent } from './core/locale/locale-picker.component';
import { ThemePickerComponent } from './core/theme/theme-picker.component';
import { SECTIONS, sectionLabel } from './core/shell/sections';
import { ThemeStore } from './core/theme/theme.store';

@Component({
  selector: 'app-root',
  imports: [
    LocalePickerComponent,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ThemePickerComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly title = signal('Quookly');

  // Injected so the theme is resolved and applied from the first paint.
  private readonly theme = inject(ThemeStore);

  private readonly auth = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly root = inject(ActivatedRoute);

  protected readonly sections = SECTIONS;
  protected readonly sectionLabel = sectionLabel;

  /** Navigation to places that refuse you is worse than no navigation. */
  protected readonly signedIn = this.auth.isSignedIn;

  protected readonly name = computed(() => this.auth.cook()?.display_name ?? '');

  /** One letter, because a sidebar is not a place for a full name at every width. */
  protected readonly initial = computed(() => this.name().trim().charAt(0).toUpperCase());

  /**
   * Whether this screen wants the application's furniture around it.
   *
   * Read from the route rather than matched against a path, so a screen declares its own
   * posture and the shell does not accumulate a list of exceptions. Cooking mode is the
   * one that says no: the cook is standing at a hob and a navigation bar is an invitation
   * to leave in the middle of a recipe.
   */
  protected readonly chromed = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      startWith(null),
      map(() => {
        let route = this.root;
        while (route.firstChild !== null) {
          route = route.firstChild;
        }
        return route.snapshot.data['chrome'] !== false;
      }),
    ),
    { initialValue: true },
  );
}
