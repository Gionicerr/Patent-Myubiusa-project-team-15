import { Injectable } from '@angular/core';
import { Observable, defer, of, delay, throwError } from 'rxjs';
import { CreateNoteRequest, Note } from './models';
import { NotesError, NotesGateway } from './notes-api';

/** Explicit test transport. Data and fictitious identities live only in this tab. */
@Injectable({ providedIn: 'root' })
export class MockNotesGateway implements NotesGateway {
  private readonly notes = new Map<string, Note[]>();
  private nextFailure: { operation: 'list' | 'create'; status: number } | null = null;
  // Test seam for deterministic 400/401/403/500/network scenarios; never used as HTTP fallback.
  failNext(operation: 'list' | 'create', status: number): void {
    this.nextFailure = { operation, status };
  }
  private run<T>(operation: 'list' | 'create', work: () => T): Observable<T> {
    return defer(() => {
      const failure = this.nextFailure;
      if (failure?.operation === operation) {
        this.nextFailure = null;
        return throwError(() => new NotesError(failure.status));
      }
      return of(work()).pipe(delay(350));
    });
  }
  list(token: string): Observable<Note[]> {
    return this.run('list', () => structuredClone(this.notes.get(token) ?? []));
  }
  create(token: string, request: CreateNoteRequest): Observable<Note> {
    return this.run('create', () => {
      if (!request.title.trim() || request.title.length > 100 || (request.text?.length ?? 0) > 2000) {
        throw new NotesError(400);
      }
      const note: Note = { id: crypto.randomUUID(), ownerId: 'test-employee',
        title: request.title, text: request.text ?? '', createdAt: new Date().toISOString() };
      this.notes.set(token, [...(this.notes.get(token) ?? []), note]);
      return structuredClone(note);
    });
  }
}
