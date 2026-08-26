import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AcademyService, PageSummaryView } from '@api';

@Component({
  selector: 'app-academy',
  imports: [RouterLink],
  templateUrl: './academy.component.html',
  styleUrl: './academy.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AcademyComponent {
  protected readonly pages = signal<PageSummaryView[] | null>(null);
  protected readonly failed = signal(false);

  constructor() {
    inject(AcademyService)
      .browseAcademy()
      .subscribe({
        // An empty Academy and an unreachable one look identical unless one says so.
        next: (found) => this.pages.set(found),
        error: () => this.failed.set(true),
      });
  }
}
