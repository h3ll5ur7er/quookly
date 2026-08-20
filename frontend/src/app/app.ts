import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { ThemePickerComponent } from './core/theme/theme-picker.component';
import { ThemeStore } from './core/theme/theme.store';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, ThemePickerComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class App {
  protected readonly title = signal('Quookly');

  // Injected so the theme is resolved and applied from the first paint.
  private readonly theme = inject(ThemeStore);
}
