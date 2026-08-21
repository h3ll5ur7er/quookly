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
import { ThemeStore } from './core/theme/theme.store';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ThemePickerComponent,
    LocalePickerComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly title = signal('Quookly');

  // Injected so the theme is resolved and applied from the first paint.
  private readonly theme = inject(ThemeStore);

  /** Navigation to places that refuse you is worse than no navigation. */
  private readonly authenticated = inject(AuthStore).isSignedIn;

  private readonly router = inject(Router);
  private readonly root = inject(ActivatedRoute);

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

  protected readonly signedIn = computed(() => this.authenticated() && this.chromed());
}
