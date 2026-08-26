import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideApi } from '@api';
import { WritePageComponent } from './write-page.component';

/**
 * Contributing a page to the Academy (UC-7.4, ADR-060).
 *
 * The screen's whole job beyond the form is to be honest about what happens next: a page
 * arrives unreviewed, and until somebody has read it, it is a page in the Academy and not
 * a word in anybody's recipe. A cook who is not told that will think the feature is broken
 * when their own recipe does not underline the word they just explained.
 */
describe('WritePageComponent', () => {
  let fixture: ComponentFixture<WritePageComponent>;
  let backend: HttpTestingController;
  /** Where the screen sent the cook. Stubbed so a real navigation does not go looking for
      a route this test module does not declare. */
  let went: ReturnType<typeof vi.spyOn>;

  const text = () => fixture.nativeElement.textContent as string;

  const set = (selector: string, value: string) => {
    const field: HTMLInputElement = fixture.nativeElement.querySelector(selector);
    field.value = value;
    field.dispatchEvent(new Event('input'));
  };

  const click = (name: string) => {
    const buttons: HTMLButtonElement[] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    );
    buttons.find((one) => one.textContent?.includes(name))!.click();
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [WritePageComponent],
      providers: [provideRouter([]), provideHttpClientTesting(), provideApi('http://testserver')],
    }).compileComponents();

    backend = TestBed.inject(HttpTestingController);
    went = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(WritePageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
  });

  afterEach(() => backend.verify());

  it('says what will happen to the page before it is written', () => {
    expect(text()).toContain('Nobody has read it yet');
  });

  it('will not send an empty page', () => {
    const save: HTMLButtonElement = fixture.nativeElement.querySelector('button[type="submit"]');
    expect(save.disabled).toBe(true);
  });

  it('sends what was typed', async () => {
    set('#name', 'spatchcock');
    set('#slug', 'spatchcock');
    set('#summary', 'Flatten a bird so it cooks evenly.');
    set('#explanation', 'Cut out the backbone and press down on the breastbone.');
    await fixture.whenStable();

    click('Write the page');
    await fixture.whenStable();

    const sent = backend.expectOne('http://testserver/api/v1/academy');
    expect(sent.request.method).toBe('POST');
    expect(sent.request.body.slug).toBe('spatchcock');
    expect(sent.request.body.summary).toBe('Flatten a bird so it cooks evenly.');
    sent.flush({ slug: 'spatchcock' });
  });

  it('offers a slug based on the name, so nobody has to invent one', async () => {
    set('#name', 'Spatchcock a Chicken');
    await fixture.whenStable();

    const slug: HTMLInputElement = fixture.nativeElement.querySelector('#slug');
    expect(slug.value).toBe('spatchcock-a-chicken');
  });

  it('leaves a slug alone once it has been edited by hand', async () => {
    set('#slug', 'spatchcock');
    set('#name', 'Butterflying a Chicken');
    await fixture.whenStable();

    const slug: HTMLInputElement = fixture.nativeElement.querySelector('#slug');
    expect(slug.value).toBe('spatchcock');
  });

  it('sends the spellings one per line', async () => {
    set('#name', 'spatchcock');
    set('#summary', 'Flatten a bird.');
    set('#explanation', 'Cut out the backbone.');
    set('#spellings', 'spatchcocked\nbutterflied\n');
    await fixture.whenStable();

    click('Write the page');
    await fixture.whenStable();

    const sent = backend.expectOne('http://testserver/api/v1/academy');
    expect(sent.request.body.spellings).toEqual(['spatchcocked', 'butterflied']);
    sent.flush({ slug: 'spatchcock' });
  });

  it('goes to the page it just wrote', async () => {
    set('#name', 'spatchcock');
    set('#summary', 'Flatten a bird.');
    set('#explanation', 'Cut out the backbone.');
    await fixture.whenStable();
    click('Write the page');
    await fixture.whenStable();

    backend.expectOne('http://testserver/api/v1/academy').flush({ slug: 'spatchcock' });
    await fixture.whenStable();

    expect(went).toHaveBeenCalledWith(['/academy', 'spatchcock']);
  });

  it('says plainly when the name is taken, rather than failing silently', async () => {
    set('#name', 'blanch');
    set('#summary', 'Into boiling water.');
    set('#explanation', 'Then straight into ice.');
    await fixture.whenStable();
    click('Write the page');
    await fixture.whenStable();

    backend
      .expectOne('http://testserver/api/v1/academy')
      .flush(
        { detail: 'There is already a page with that name.' },
        { status: 409, statusText: 'Conflict' },
      );
    await fixture.whenStable();

    expect(text()).toContain('already a page');
  });
});
