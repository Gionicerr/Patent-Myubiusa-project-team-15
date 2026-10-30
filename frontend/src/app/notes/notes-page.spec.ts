import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';
import { NotesPage } from './notes-page';
import { Note } from '../core/models';
import { NOTES_GATEWAY, NotesError, NotesGateway } from '../core/notes-api';
const note: Note = { id: 'one', ownerId: 'old-owner', title: 'Секрет старого сеанса', text: '<script>alert(1)</script>', createdAt: '2026-01-02T03:04:05Z' };

describe('Notes page behavior', () => {
  let fixture: ComponentFixture<NotesPage>;
  let page: NotesPage;
  let api: jasmine.SpyObj<NotesGateway>;
  beforeEach(async () => {
    api = jasmine.createSpyObj<NotesGateway>('api', ['list', 'create']);
    api.list.and.returnValue(of([])); api.create.and.returnValue(of(note));
    await TestBed.configureTestingModule({ imports: [NotesPage], providers: [{ provide: NOTES_GATEWAY, useValue: api }] }).compileComponents();
    fixture = TestBed.createComponent(NotesPage); page = fixture.componentInstance; fixture.detectChanges();
  });
  const connect = (page: NotesPage, token = 'test-token') => { page.tokenInput.setValue(token); page.connect(); };
  it('connects through the actual token form submit event', () => {
    page.tokenInput.setValue('test-form-token'); fixture.detectChanges();
    fixture.nativeElement.querySelector('.token-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    expect(page.connected()).toBeTrue(); expect(api.list).toHaveBeenCalledWith('test-form-token');
  });
  it('starts disconnected with no data requests', () => {
    expect(page.connected()).toBeFalse(); expect(api.list).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Подключите сеанс');
  });
  it('validates required/nonblank and exact title/text boundaries without silently trimming', () => {
    const title = page.form.controls.title, text = page.form.controls.text;
    for (const v of ['', '   ', '\t']) { title.setValue(v); expect(title.invalid).toBeTrue(); }
    for (const v of ['a', 'a'.repeat(100), ' a ']) { title.setValue(v); expect(title.valid).toBeTrue(); }
    title.setValue('a'.repeat(101)); expect(title.invalid).toBeTrue();
    text.setValue('x'.repeat(2000)); expect(text.valid).toBeTrue();
    text.setValue('x'.repeat(2001)); expect(text.invalid).toBeTrue();
    connect(page); page.form.setValue({ title: ' a ', text: ' text ' }); page.submit();
    expect(api.create).toHaveBeenCalledWith('test-token', { title: ' a ', text: ' text ' });
  });
  it('does not submit invalid forms or disconnected forms', () => {
    page.form.controls.title.setValue('Valid'); page.submit(); expect(api.create).not.toHaveBeenCalled();
    connect(page); page.form.controls.title.setValue('   '); page.submit(); expect(api.create).not.toHaveBeenCalled();
  });
  it('shows loading followed by an empty list', () => {
    const pending = new Subject<Note[]>(); api.list.and.returnValue(pending);
    connect(page); fixture.detectChanges(); expect(page.loading()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Загружаем заметки');
    pending.next([]); fixture.detectChanges();
    expect(page.loading()).toBeFalse(); expect(fixture.nativeElement.textContent).toContain('Начните с первой заметки');
  });
  it('prevents duplicate POST, then clears form and refreshes after confirmed creation', () => {
    const pending = new Subject<Note>(); api.create.and.returnValue(pending);
    connect(page); page.form.setValue({ title: 'Идея', text: 'Текст' }); page.submit(); page.submit();
    expect(api.create).toHaveBeenCalledTimes(1); expect(page.saving()).toBeTrue();
    api.list.and.returnValue(of([note])); pending.next(note);
    expect(page.saving()).toBeFalse(); expect(page.success()).toBe('Заметка создана.');
    expect(page.form.controls.title.value).toBe(''); expect(page.notes()).toEqual([note]);
  });
  it('distinguishes POST success from refresh failure', () => {
    connect(page); api.list.and.returnValue(throwError(() => new NotesError(500)));
    page.form.controls.title.setValue('Идея'); page.submit(); fixture.detectChanges();
    expect(page.success()).toBe('Заметка создана.'); expect(page.saveError()).toBe('');
    expect(fixture.nativeElement.textContent).toContain('Заметка создана, но список обновить не удалось');
    expect(page.form.controls.title.value).toBe('');
  });
  for (const status of [400, 401, 403, 500, 0, -1]) {
    it(`preserves input and exposes a useful POST error for ${status}`, () => {
      connect(page); api.create.and.returnValue(throwError(() => new NotesError(status)));
      page.form.setValue({ title: 'Не потерять', text: 'Черновик' }); page.submit(); fixture.detectChanges();
      expect(page.saveError()).not.toBe(''); expect(page.saving()).toBeFalse();
      expect(page.form.getRawValue()).toEqual({ title: 'Не потерять', text: 'Черновик' });
      expect(api.create).toHaveBeenCalledTimes(1);
      if ([0, -1, 500].includes(status)) {
        expect(page.mustCheckList()).toBeTrue(); page.submit(); expect(api.create).toHaveBeenCalledTimes(1);
        page.reload(); expect(page.mustCheckList()).toBeFalse();
      }
    });
    it(`shows a GET error rather than any test data for ${status}`, () => {
      api.list.and.returnValue(throwError(() => new NotesError(status))); connect(page); fixture.detectChanges();
      expect(page.notes()).toEqual([]); expect(page.listError()).not.toBe(''); expect(page.loaded()).toBeFalse();
      expect(fixture.nativeElement.querySelector('[role=alert]')).not.toBeNull();
      expect(api.list).toHaveBeenCalledTimes(1);
    });
  }
  it('clears previous data and ignores an old list response after token change', () => {
    api.list.and.returnValue(of([note])); connect(page); expect(page.notes()).toEqual([note]);
    const old = new Subject<Note[]>(); api.list.and.returnValue(old); page.reload();
    api.list.and.returnValue(of([])); connect(page, 'second-token'); old.next([note]);
    expect(page.notes()).toEqual([]); expect(page.tokenInput.value).toBe('');
    expect(api.list).toHaveBeenCalledWith('second-token');
  });
  it('cancels pending POST on disconnect and ignores its late success', () => {
    const old = new Subject<Note>(); api.create.and.returnValue(old); connect(page);
    page.form.controls.title.setValue('Текст'); page.submit(); page.disconnect(); old.next(note);
    expect(page.connected()).toBeFalse(); expect(page.notes()).toEqual([]); expect(page.success()).toBe('');
    expect(page.saving()).toBeFalse(); expect(page.form.controls.title.value).toBe('');
  });
  it('renders note contents as text, never executable HTML', () => {
    api.list.and.returnValue(of([note])); connect(page); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('<script>alert(1)</script>');
    expect(fixture.nativeElement.querySelector('article script')).toBeNull();
  });
});
