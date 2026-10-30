import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HttpNotesGateway, NotesError } from './notes-api';
import { Note } from './models';
const note: Note = { id: '7ba43c22-c24b-43e1-8ae4-894d40507ccf', ownerId: 'employee-a', title: 'Идея', text: '', createdAt: '2026-01-02T03:04:05Z' };

describe('HTTP notes contract', () => {
  let api: HttpNotesGateway;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(HttpNotesGateway); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('GET returns the direct array and sends Bearer only to the notes API', () => {
    let result: Note[] = [];
    api.list('test-only').subscribe(value => result = value);
    const req = http.expectOne('/api/notes');
    expect(req.request.method).toBe('GET'); expect(req.request.body).toBeNull();
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-only');
    req.flush([note]); expect(result).toEqual([note]);
    TestBed.inject(HttpClient).get('/asset.json').subscribe();
    const asset = http.expectOne('/asset.json'); expect(asset.request.headers.has('Authorization')).toBeFalse();
    asset.flush({});
  });
  it('POST allowlists title/text, preserves input, and never sends server-owned fields', () => {
    api.create('test-only', { ...note, title: ' Идея ' }).subscribe(value => expect(value).toEqual(note));
    const req = http.expectOne('/api/notes');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ title: ' Идея ', text: '' });
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-only'); req.flush(note, { status: 201, statusText: 'Created' });
  });
  it('allows optional text to be omitted', () => {
    api.create('test-only', { title: 'Идея' }).subscribe();
    const req = http.expectOne('/api/notes'); expect(req.request.body).toEqual({ title: 'Идея' }); req.flush(note);
  });
  for (const status of [400, 401, 403, 500]) {
    it(`reports ${status} without retry or fallback`, () => {
      api.create('test-only', { title: 'Идея' }).subscribe({ error: (e: NotesError) => expect(e.status).toBe(status) });
      http.expectOne('/api/notes').flush({ code: 'test', message: 'safe test' }, { status, statusText: 'Error' });
      http.expectNone('/api/notes');
    });
  }
  it('handles non-JSON gateway error without exposing its contents', () => {
    api.list('test-only').subscribe({ error: (e: NotesError) => {
      expect(e.status).toBe(500); expect(JSON.stringify(e)).not.toContain('private-gateway-body');
    }});
    http.expectOne('/api/notes').flush('<html>private-gateway-body</html>', { status: 500, statusText: 'Error' });
  });
  it('reports network failure without retry', () => {
    api.create('test-only', { title: 'Идея' }).subscribe({ error: (e: NotesError) => expect(e.status).toBe(0) });
    http.expectOne('/api/notes').error(new ProgressEvent('error')); http.expectNone('/api/notes');
  });
  it('rejects a success response in a wrong envelope', () => {
    api.list('test-only').subscribe({ next: () => fail('wrong contract accepted'), error: (e: NotesError) => expect(e.status).toBe(-1) });
    http.expectOne('/api/notes').flush({ items: [note] });
  });
  it('rejects malformed created note', () => {
    api.create('test-only', { title: 'Идея' }).subscribe({ next: () => fail('wrong contract accepted'), error: (e: NotesError) => expect(e.status).toBe(-1) });
    http.expectOne('/api/notes').flush({ ...note, createdAt: 'not-a-date' });
  });
});
