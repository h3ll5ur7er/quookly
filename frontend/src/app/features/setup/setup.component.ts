import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SetupProgressView, SetupService, SetupStep } from '@api';
import {
  stepAction,
  stepDecline,
  stepDeclared,
  stepRoute,
  stepTitle,
  stepWhy,
} from './setup.labels';

/**
 * What a new cook still has to set up (UC-10.2, UC-10.3).
 *
 * A checklist rather than a wizard. Nothing here stores progress — the backend derives it
 * from the profile every time (ADR-014), which is what lets a cook leave halfway, come
 * back a month later, and be asked exactly what is still outstanding.
 *
 * Every step is shown, not only the next one. A wizard that reveals one door at a time
 * cannot tell somebody how far there is left to go.
 */
@Component({
  selector: 'app-setup',
  imports: [RouterLink],
  templateUrl: './setup.component.html',
  styleUrl: './setup.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SetupComponent {
  private readonly setup = inject(SetupService);

  protected readonly progress = signal<SetupProgressView | null>(null);
  protected readonly failed = signal(false);
  protected readonly declining = signal<SetupStep | null>(null);

  protected readonly stepTitle = stepTitle;
  protected readonly stepWhy = stepWhy;
  protected readonly stepAction = stepAction;
  protected readonly stepDecline = stepDecline;
  protected readonly stepDeclared = stepDeclared;
  protected readonly stepRoute = stepRoute;

  constructor() {
    this.setup.getSetup().subscribe({
      next: (progress) => this.progress.set(progress),
      error: () => this.failed.set(true),
    });
  }

  /** Answer a question outright: nobody has any, the defaults are fine. */
  protected decline(step: SetupStep): void {
    if (this.declining() !== null) {
      return;
    }
    this.declining.set(step);
    this.setup.declareStep(step).subscribe({
      next: (progress) => {
        this.progress.set(progress);
        this.declining.set(null);
      },
      error: () => {
        this.declining.set(null);
        this.failed.set(true);
      },
    });
  }
}
