import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NgOptimizedImage } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { ActivatedRoute } from '@angular/router';
import { AccountsService } from '@api';
import { AuthStore } from '../../core/auth/auth.store';
import { isLocale, preferredLocale, storeLocale } from '../../core/locale/locale.store';

@Component({
  selector: 'app-sign-in',
  imports: [ReactiveFormsModule, NgOptimizedImage],
  templateUrl: './sign-in.component.html',
  styleUrl: './sign-in.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SignInComponent {
  private readonly accounts = inject(AccountsService);
  private readonly auth = inject(AuthStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly submitting = signal(false);
  protected readonly failed = signal(false);

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
    this.accounts.signIn(this.form.getRawValue()).subscribe({
      next: (authenticated) => {
        this.auth.signIn(authenticated);
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl') ?? '/';
        const theirs = authenticated.cook.locale;
        if (isLocale(theirs) && theirs !== preferredLocale()) {
          // Their language, not this device's. Catalogues are fixed for the life of the
          // application (ADR-025), so adopting one means loading the page again — done as
          // a navigation so they still land where they were going.
          storeLocale(theirs);
          location.assign(returnUrl);
          return;
        }
        void this.router.navigateByUrl(returnUrl);
      },
      error: () => {
        // One message for every failure: the API deliberately does not say whether the
        // account exists, and repeating that distinction here would undo it.
        this.submitting.set(false);
        this.failed.set(true);
      },
    });
  }
}
