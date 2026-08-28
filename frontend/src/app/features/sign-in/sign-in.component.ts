import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NgOptimizedImage } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AccountsService } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { AccountLocale } from '../../core/locale/account-locale';

@Component({
  selector: 'app-sign-in',
  imports: [ReactiveFormsModule, NgOptimizedImage, RouterLink],
  templateUrl: './sign-in.component.html',
  styleUrl: './sign-in.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SignInComponent {
  private readonly accounts = inject(AccountsService);
  private readonly auth = inject(AuthStore);
  private readonly language = inject(AccountLocale);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly submitting = signal(false);
  protected readonly failed = signal(false);

  /**
   * Which refusal this was.
   *
   * Three sentences rather than one, because the API tells them apart only once the
   * password has matched (ADR-049) — so repeating the distinction here reveals nothing,
   * and collapsing it would leave an applicant retyping a password that was right all
   * along.
   */
  protected readonly waiting = signal(false);
  protected readonly declined = signal(false);

  protected readonly form = inject(FormBuilder).nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  protected submit(): void {
    if (this.form.invalid || this.submitting()) {
      return;
    }
    this.submitting.set(true);
    this.failed.set(false);
    this.waiting.set(false);
    this.declined.set(false);
    this.accounts.signIn(this.form.getRawValue()).subscribe({
      next: (authenticated) => {
        this.auth.signIn(authenticated);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/';
        // Their language, not this device's (L6). Catalogues are fixed for the life of the
        // application (ADR-025), so adopting one means loading the page again — done as a
        // navigation so they still land where they were going.
        if (this.language.settle(authenticated)) {
          location.assign(returnUrl);
          return;
        }
        void this.router.navigateByUrl(returnUrl);
      },
      error: (refusal: HttpErrorResponse) => {
        this.submitting.set(false);
        // A 401 stays one message whatever went wrong behind it: the API deliberately
        // does not say whether the account exists, and saying more here would undo that.
        if (refusal.status !== 403) {
          this.failed.set(true);
          return;
        }
        // A 403 means the credentials were right and the door is not open. Which of the
        // two it is comes from the API, because only it knows.
        const declined = String(refusal.error?.detail ?? '').includes('declined');
        this.declined.set(declined);
        this.waiting.set(!declined);
      },
    });
  }
}
