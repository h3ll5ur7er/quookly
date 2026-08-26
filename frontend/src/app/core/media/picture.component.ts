import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { HttpClient } from '@angular/common/http';

/**
 * A stored picture.
 *
 * Fetched through `HttpClient` rather than pointed at with `<img src>`, because the media
 * endpoint wants the bearer token and an `<img>` does not carry one — it would 401 in
 * silence and show a broken image. The bytes come back as a blob and the object URL is
 * released when this leaves the screen, or a page full of pictures leaks one per picture.
 *
 * Alt text is an input rather than optional: a picture without it is an accessibility
 * failure, and there is nowhere in this component to default it from.
 */
@Component({
  selector: 'app-picture',
  imports: [],
  template: `
    @if (source(); as src) {
      <img [src]="src" [alt]="description()" />
    } @else if (failed()) {
      <p class="picture__missing" i18n="@@pictureMissing">That picture could not be loaded.</p>
    }
  `,
  styles: `
    img {
      display: block;
      width: 100%;
      max-width: 100%;
      height: auto;
      border-radius: var(--radius-md);
    }
    .picture__missing {
      color: var(--on-surface-muted);
      font-size: var(--text-sm);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PictureComponent {
  readonly mediaId = input.required<string>();
  readonly description = input.required<string>();

  private readonly http = inject(HttpClient);
  protected readonly source = signal<string | null>(null);
  protected readonly failed = signal(false);

  /**
   * The object URL currently held, as a plain field rather than read back from the signal.
   *
   * Reading `source()` inside the effect made it a dependency *of* the effect: setting it
   * re-ran the effect, which released what had just been set, and the picture never
   * appeared. A field is not a signal and does not do that.
   */
  private held: string | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.release());

    effect(() => {
      const id = this.mediaId();
      this.release();
      this.failed.set(false);
      this.http.get(`/api/v1/media/${id}`, { responseType: 'blob' }).subscribe({
        next: (bytes) => {
          this.held = URL.createObjectURL(bytes);
          this.source.set(this.held);
        },
        error: () => this.failed.set(true),
      });
    });
  }

  private release(): void {
    if (this.held !== null) {
      URL.revokeObjectURL(this.held);
      this.held = null;
    }
    this.source.set(null);
  }
}
