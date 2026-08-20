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
    path: 'recipes',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/recipe-list.component').then((m) => m.RecipeListComponent),
  },
  {
    path: 'recipes/:id',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/recipe-detail.component').then((m) => m.RecipeDetailComponent),
  },
  { path: '', redirectTo: 'recipes', pathMatch: 'full' },
  { path: '**', redirectTo: 'recipes' },
];
