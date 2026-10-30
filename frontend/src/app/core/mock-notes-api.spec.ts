import { fakeAsync, tick } from '@angular/core/testing';
import { MockNotesGateway } from './mock-notes-api';
import { Note } from './models';
import { NotesError } from './notes-api';
describe('Explicit in-memory test transport', () => {
  it('starts empty, creates a conforming note and isolates token sessions', fakeAsync(() => {
    const api = new MockNotesGateway();
    let notes: Note[] = [];
    api.list('fictitious-a').subscribe(v => notes = v); tick(350); expect(notes).toEqual([]);
    let created!: Note;
    api.create('fictitious-a', { title: 'Идея' }).subscribe(v => created = v); tick(350);
    expect(created.text).toBe(''); expect(created.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(Number.isFinite(Date.parse(created.createdAt))).toBeTrue();
    api.list('fictitious-a').subscribe(v => notes = v); tick(350); expect(notes).toEqual([created]);
    api.list('fictitious-b').subscribe(v => notes = v); tick(350); expect(notes).toEqual([]);
  }));
  for (const status of [400, 401, 403, 500, 0]) {
    it(`reproduces ${status} explicitly`, () => {
      const api = new MockNotesGateway(); api.failNext('create', status);
      api.create('fictitious', { title: 'Идея' }).subscribe({ next: () => fail('expected error'), error: (e: NotesError) => expect(e.status).toBe(status) });
    });
  }
});
