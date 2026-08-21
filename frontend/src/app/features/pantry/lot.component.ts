import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { PantryEntry, PantryService, StockLotView, WasteReason } from '@api';
import { WASTE_REASONS, day, urgency, wasteReasonLabel } from './pantry.labels';

/** One packet: how much is left, what was thrown away, or that it was never here. */
@Component({
  selector: 'app-lot',
  imports: [ReactiveFormsModule],
  templateUrl: './lot.component.html',
  styleUrl: './lot.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LotComponent {
  private readonly pantry = inject(PantryService);
  private readonly router = inject(Router);
  private readonly lotId = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));

  protected readonly entry = signal<PantryEntry | null>(null);
  protected readonly lot = signal<StockLotView | null>(null);
  protected readonly missing = signal(false);
  protected readonly failed = signal(false);
  protected readonly held = signal(false);
  protected readonly saving = signal(false);
  /** Which question the screen is asking. One at a time, so one action is filled. */
  protected readonly wasting = signal(false);

  protected readonly reasons = WASTE_REASONS;
  protected readonly wasteReasonLabel = wasteReasonLabel;
  protected readonly urgency = urgency;
  protected readonly day = day;

  protected readonly unit = computed(() => this.lot()?.unit ?? '');

  protected readonly form = inject(FormBuilder).nonNullable.group({
    magnitude: ['', [Validators.required, Validators.pattern(/^\d*\.?\d+$/)]],
  });

  protected readonly wasteForm = inject(FormBuilder).nonNullable.group({
    wasted: ['', [Validators.required, Validators.pattern(/^\d*\.?\d+$/)]],
    reason: [WasteReason.spoiled, Validators.required],
    note: ['', Validators.maxLength(200)],
  });

  constructor() {
    /*
     * The whole shelf, rather than an endpoint for one lot.
     *
     * The screen needs the ingredient's name and the packet's siblings anyway, and a
     * pantry is tens of entries. A second endpoint returning the same thing sliced
     * differently would be a second answer to keep in agreement with the first.
     */
    this.pantry.listPantry().subscribe({
      next: (shelf) => this.settle(shelf),
      error: () => this.failed.set(true),
    });
  }

  private settle(shelf: PantryEntry[]): void {
    for (const entry of shelf) {
      const found = entry.lots.find((one) => one.id === this.lotId);
      if (found !== undefined) {
        this.entry.set(entry);
        this.lot.set(found);
        // Pre-filled with what is recorded, so correcting it is an edit rather than a
        // re-entry — and so a cook who opened this by mistake can leave without harm.
        this.form.setValue({ magnitude: found.magnitude });
        return;
      }
    }
    this.missing.set(true);
  }

  protected startWasting(): void {
    this.failed.set(false);
    this.held.set(false);
    this.wasting.set(true);
  }

  protected stopWasting(): void {
    this.wasting.set(false);
  }

  protected save(): void {
    if (this.form.invalid || this.saving()) {
      return;
    }
    this.begin();
    this.pantry
      .adjustLot(this.lotId, { magnitude: this.form.getRawValue().magnitude })
      .subscribe({ next: () => this.done(), error: () => this.stumble() });
  }

  protected recordWaste(): void {
    if (this.wasteForm.invalid || this.saving()) {
      return;
    }
    const { wasted, reason, note } = this.wasteForm.getRawValue();
    this.begin();
    this.pantry
      .recordWaste(this.lotId, {
        magnitude: wasted,
        reason,
        note: note.trim() === '' ? null : note.trim(),
      })
      .subscribe({ next: () => this.done(), error: () => this.stumble() });
  }

  protected discard(): void {
    if (this.saving()) {
      return;
    }
    this.begin();
    this.pantry.discardLot(this.lotId).subscribe({
      next: () => this.done(),
      error: (refusal: { status?: number }) => {
        this.saving.set(false);
        // A packet with waste against it is held rather than gone: deleting it would
        // leave that record pointing at nothing. Said in those words, because "could not
        // delete" would read as a fault rather than as a reason.
        if (refusal.status === 409) {
          this.held.set(true);
        } else {
          this.failed.set(true);
        }
      },
    });
  }

  private begin(): void {
    this.saving.set(true);
    this.failed.set(false);
    this.held.set(false);
  }

  private done(): void {
    void this.router.navigateByUrl('/pantry');
  }

  private stumble(): void {
    this.saving.set(false);
    this.failed.set(true);
  }
}
