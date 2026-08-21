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
    // `import` before `:id`: they share a shape, and the first match wins.
    path: 'recipes/import',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/import-recipe.component').then((m) => m.ImportRecipeComponent),
  },
  {
    path: 'recipes/:id',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/recipe-detail.component').then((m) => m.RecipeDetailComponent),
  },
  {
    path: 'household',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/household/household.component').then((m) => m.HouseholdComponent),
  },
  {
    // `new` before `:id`: they share a shape, and the first match wins.
    path: 'household/new',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/household/eater-form.component').then((m) => m.EaterFormComponent),
  },
  {
    path: 'household/:id',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/household/eater-form.component').then((m) => m.EaterFormComponent),
  },
  {
    path: 'pantry',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/pantry/pantry.component').then((m) => m.PantryComponent),
  },
  {
    // `add` before any `:id`-shaped route: they share a shape, and the first match wins.
    path: 'pantry/add',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/pantry/receive-stock.component').then((m) => m.ReceiveStockComponent),
  },
  {
    path: 'pantry/lots/:id',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/pantry/lot.component').then((m) => m.LotComponent),
  },
  {
    path: 'setup',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/setup/setup.component').then((m) => m.SetupComponent),
  },
  {
    path: 'settings',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/settings/settings.component').then((m) => m.SettingsComponent),
  },
  { path: '', redirectTo: 'recipes', pathMatch: 'full' },
  { path: '**', redirectTo: 'recipes' },
];
