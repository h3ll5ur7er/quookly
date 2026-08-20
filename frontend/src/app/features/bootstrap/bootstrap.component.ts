import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AccountsService } from '@api';
import { AuthStore } from '../../core/auth/auth.store';

/** The minimum the API will accept; stated here so the form can say so before submitting. */
const MINIMUM_PASSWORD_LENGTH = 12;

@Component({
  selector: 'app-bootstrap',
  imports: [ReactiveFormsModule],
  templateUrl: './bootstrap.component.html',
  styleUrl: './bootstrap.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BootstrapComponent {
  private readonly accounts = inject(AccountsService);
  private readonly auth = inject(AuthStore);
  private readonly router = inject(Router);

  protected readonly minimumPasswordLength = MINIMUM_PASSWORD_LENGTH;
  protected readonly submitting = signal(false);
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
    this.accounts.bootstrapAdmin(this.form.getRawValue()).subscribe({
      next: (authenticated) => {
        this.auth.signIn(authenticated);
        void this.router.navigateByUrl('/dashboard');
      },
      error: (response: { status?: number }) => {
        this.submitting.set(false);
        this.error.set(
          response.status === 409
            ? 'This instance has already been claimed. Sign in instead.'
            : 'Could not create the account. Please try again.',
        );
      },
    });
  }
}
