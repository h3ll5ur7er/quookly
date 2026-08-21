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
    path: 'plans',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/plans/plans.component').then((m) => m.PlansComponent),
  },
  {
    // `meal` before `:id`-shaped routes: they share a shape, and the first match wins.
    path: 'plans/:id/meal',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/plans/meal.component').then((m) => m.MealComponent),
  },
  {
    path: 'plans/:id',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/plans/plan.component').then((m) => m.PlanComponent),
  },
  {
    // Its own route rather than a mode of the plan screen. Cooking is a different
    // posture with different rules — bigger, low-slung, and with the app's own
    // navigation out of the way (NFR-12).
    path: 'cook/:id',
    canActivate: [requireSignedIn],
    data: { chrome: false },
    loadComponent: () => import('./features/cooking/cook.component').then((m) => m.CookComponent),
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
