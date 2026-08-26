import { Routes } from '@angular/router';
import { requireSignedIn, whileSignedOut } from './core/auth/auth.guard';
import { requireClaimedInstance, requireUnclaimedInstance } from './core/auth/entry.guard';

export const routes: Routes = [
  {
    path: 'bootstrap',
    canActivate: [requireUnclaimedInstance],
    loadComponent: () =>
      import('./features/bootstrap/bootstrap.component').then((m) => m.BootstrapComponent),
  },
  {
    // Public, like sign-in: somebody applying has no account by definition. Guarded the
    // same way, because an instance nobody has claimed wants its first admin rather than
    // an applicant with nobody to answer them.
    path: 'apply',
    canActivate: [requireClaimedInstance],
    loadComponent: () => import('./features/apply/apply.component').then((m) => m.ApplyComponent),
  },
  {
    path: 'sign-in',
    canActivate: [requireClaimedInstance],
    loadComponent: () =>
      import('./features/sign-in/sign-in.component').then((m) => m.SignInComponent),
  },
  {
    // The front door for somebody who has not signed in. Same address as home: a visitor
    // and a cook arrive at the same place and are shown what is useful to each.
    path: '',
    pathMatch: 'full',
    canMatch: [whileSignedOut],
    canActivate: [requireClaimedInstance],
    loadComponent: () =>
      import('./features/landing/landing.component').then((m) => m.LandingComponent),
  },
  {
    // What is happening now: what wants eating, what is on tonight, what to do next.
    path: '',
    pathMatch: 'full',
    canActivate: [requireSignedIn],
    loadComponent: () => import('./features/home/home.component').then((m) => m.HomeComponent),
  },
  {
    // Its own destination rather than a section of the plan. A cook holding a basket has
    // one hand and thirty seconds.
    path: 'shopping',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/shopping/shopping.component').then((m) => m.ShoppingComponent),
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
    // Before `:id`, like `import`: they share a shape and the first match wins.
    path: 'recipes/new',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/recipe-form.component').then((m) => m.RecipeFormComponent),
  },
  {
    path: 'recipes/:id/edit',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/recipe-form.component').then((m) => m.RecipeFormComponent),
  },
  {
    // Before `:id`, like `import`: they share a shape and the first match wins.
    path: 'recipes/invent',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/recipes/invent-recipe.component').then((m) => m.InventRecipeComponent),
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
    // One entry, whole. Before `settings/registry` would be wrong — they do not share a
    // shape — but it goes with it, so it lives here.
    path: 'settings/registry/:slug',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/registry/ingredient.component').then((m) => m.IngredientComponent),
  },
  {
    // Before `academy/:slug` for the same reason as the term route below: they share a
    // shape and the first match wins.
    path: 'academy/new',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/academy/write-page.component').then((m) => m.WritePageComponent),
  },
  {
    // Where a step's word sends a reader: the *term*, not a page. One claimant opens it and
    // several offer a chooser, so nothing picks arbitrarily (ADR-058). Before `:slug`,
    // because they share a shape and the first match wins.
    path: 'academy/terms/:term',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/academy/page.component').then((m) => m.AcademyPageComponent),
  },
  {
    path: 'academy/:slug',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/academy/page.component').then((m) => m.AcademyPageComponent),
  },
  {
    path: 'academy',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/academy/academy.component').then((m) => m.AcademyComponent),
  },
  {
    // Under settings for the same reason as the applications queue: reference material a
    // cook looks something up in, or corrects, rather than a place they go daily.
    path: 'settings/registry',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/registry/registry.component').then((m) => m.RegistryComponent),
  },
  {
    // Under settings rather than in the navigation: an admin answers this when somebody
    // tells them they applied, not several times a day.
    path: 'settings/applications',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/applications/applications.component').then((m) => m.ApplicationsComponent),
  },
  {
    path: 'settings',
    canActivate: [requireSignedIn],
    loadComponent: () =>
      import('./features/settings/settings.component').then((m) => m.SettingsComponent),
  },
  { path: '**', redirectTo: '' },
];
