import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
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
  protected readonly signedIn = inject(AuthStore).isSignedIn;
}
