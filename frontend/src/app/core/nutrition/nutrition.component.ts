import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Nutrient, NutrientView, NutritionView } from '@api';
import { ENERGY, NUTRIENTS, OF_WHICH, nutrientLabel } from './labels';

/** One row of the panel: a name, and what it comes to in each column. */
interface Row {
  readonly nutrient: Nutrient;
  readonly label: string;
  readonly indented: boolean;
  readonly perServing: string | null;
  readonly perRecipe: string | null;
}

/**
 * What a recipe contains, laid out the way a packet in this part of the world lays it out.
 *
 * Energy first, saturates indented under fat, sugars under carbohydrate, salt rather than
 * sodium — EU Regulation 1169/2011's order and vocabulary. A cook reading this has read a
 * hundred of them, and an unfamiliar arrangement would cost attention for no gain.
 *
 * The figures come from a published composition table and the panel says which one. That
 * is not a courtesy: the Swiss grant makes attribution mandatory (FR-20, ADR-045).
 */
@Component({
  selector: 'app-nutrition',
  templateUrl: './nutrition.component.html',
  styleUrl: './nutrition.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NutritionComponent {
  readonly nutrition = input.required<NutritionView>();

  protected readonly hasServing = computed(() => this.nutrition().per_serving !== null);

  protected readonly rows = computed<Row[]>(() => {
    const shown = this.nutrition();
    const serving = index(shown.per_serving ?? []);
    const recipe = index(shown.per_recipe);

    // Energy is one row carrying both figures — "1722 kJ / 412 kcal" — because that is how
    // a packet prints it. Two rows both labelled "Energy" read as two different facts.
    const energy: Row = {
      nutrient: Nutrient.energy_kj,
      label: nutrientLabel(Nutrient.energy_kj),
      indented: false,
      perServing: both(serving),
      perRecipe: both(recipe),
    };

    const rest = NUTRIENTS.filter(
      (nutrient) => !ENERGY.has(nutrient) && (recipe.has(nutrient) || serving.has(nutrient)),
    ).map((nutrient) => ({
      nutrient,
      label: nutrientLabel(nutrient),
      indented: OF_WHICH.has(nutrient),
      perServing: serving.get(nutrient) ?? null,
      perRecipe: recipe.get(nutrient) ?? null,
    }));

    return energy.perRecipe === null && energy.perServing === null ? rest : [energy, ...rest];
  });

  /** Whether there are figures at all, as opposed to only a list of what was missed. */
  protected readonly counted = computed(() => this.nutrition().per_recipe.length > 0);
}

/** The figures by nutrient, already rendered with their unit. */
function index(views: NutrientView[]): Map<Nutrient, string> {
  return new Map(views.map((view) => [view.nutrient, `${view.amount} ${view.unit}`]));
}

/** Energy as a label writes it, in whichever of the two units are published. */
function both(figures: Map<Nutrient, string>): string | null {
  const shown = [figures.get(Nutrient.energy_kj), figures.get(Nutrient.energy_kcal)].filter(
    (one): one is string => one !== undefined,
  );
  return shown.length > 0 ? shown.join(' / ') : null;
}
