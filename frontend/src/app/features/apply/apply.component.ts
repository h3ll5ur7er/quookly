import { NgOptimizedImage } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AccountsService } from '@api';

/** The minimum the API will accept; stated here so the form can say so before submitting. */
const MINIMUM_PASSWORD_LENGTH = 12;

/**
 * Applying for an account (UC-10.6).
 *
 * Not a sign-up. A Quookly instance is somebody's household server, so this asks rather
 * than creates ([ADR-049](../../../../../doc/07-decisions.md)) — and what comes back is a
 * sentence explaining that, not a session. Saying so *before* the form is submitted is
 * the part that matters: somebody who fills this in expecting to be cooking in a minute
 * has been misled by the button.
 */
@Component({
  selector: 'app-apply',
  imports: [ReactiveFormsModule, NgOptimizedImage, RouterLink],
  templateUrl: './apply.component.html',
  styleUrl: './apply.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplyComponent {
  private readonly accounts = inject(AccountsService);

  protected readonly minimumPasswordLength = MINIMUM_PASSWORD_LENGTH;
  protected readonly submitting = signal(false);
  protected readonly applied = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    display_name: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(MINIMUM_PASSWORD_LENGTH)]],
  });

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    this.accounts.applyForAccount(this.form.getRawValue()).subscribe({
      next: () => this.applied.set(true),
      error: (response: { status?: number }) => {
        this.submitting.set(false);
        this.error.set(
          response.status === 409
            ? // The same answer whether that address holds an account or an earlier
              // application. Which of the two it is, is not a stranger's business.
              $localize`:@@applyTaken:That email has already been used here. Try signing in.`
            : $localize`:@@applyFailed:Could not send your application. Please try again.`,
        );
      },
    });
  }
}
