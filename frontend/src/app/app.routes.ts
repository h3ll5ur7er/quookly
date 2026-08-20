import { Routes } from '@angular/router';
import { requireSignedIn } from './core/auth/auth.guard';
import { requireClaimedInstance, requireUnclaimedInstance } from './core/auth/entry.guard';

export const routes: Routes = [
  {
    path: 'bootstrap',
    canActivate: [requireUnclaimedInstance],
    loadComponent: () =>
      import('./features/bootstrap/bootstrap.component').then((m) => m.BootstrapComponent),
  },
  {
    path: 'sign-in',
    canActivate: [requireClaimedInstance],
    loadComponent: () =>
      import('./features/sign-in/sign-in.component').then((m) => m.SignInComponent),
  },
  {
    path: 'dashboard',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
  },
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: '**', redirectTo: 'dashboard' },
];
