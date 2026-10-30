import { inject, Injectable, InjectionToken } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, map, throwError } from 'rxjs';
import { ApiProblem, CreateNoteRequest, Note } from './models';

export interface NotesGateway {
  list(token: string): Observable<Note[]>;
  create(token: string, request: CreateNoteRequest): Observable<Note>;
}
export const NOTES_GATEWAY = new InjectionToken<NotesGateway>('NotesGateway');

export class NotesError extends Error {
  constructor(readonly status: number, readonly problem?: ApiProblem) {
    super('Notes request failed');
  }
}
function isNote(value: unknown): value is Note {
  if (!value || typeof value !== 'object') return false;
  const n = value as Record<string, unknown>;
  return ['id', 'ownerId', 'title', 'text', 'createdAt'].every(k => typeof n[k] === 'string')
    && Number.isFinite(Date.parse(n['createdAt'] as string));
}
function transportError(error: unknown): Observable<never> {
  // Raw server bodies may be HTML or contain sensitive information: never render or log them.
  return throwError(() => error instanceof NotesError ? error
    : new NotesError(error instanceof HttpErrorResponse && (error.status < 200 || error.status >= 300) ? error.status : -1));
}
@Injectable({ providedIn: 'root' })
export class HttpNotesGateway implements NotesGateway {
  private readonly http = inject(HttpClient);
  private headers(token: string) { return { Authorization: `Bearer ${token}` }; }
  list(token: string): Observable<Note[]> {
    return this.http.get<unknown>('/api/notes', { headers: this.headers(token) }).pipe(
      map(body => {
        if (!Array.isArray(body) || !body.every(isNote)) throw new NotesError(-1);
        return body;
      }), catchError(transportError));
  }
  create(token: string, request: CreateNoteRequest): Observable<Note> {
    // Explicit allowlist prevents accidental owner/id fields leaking into POST.
    const body: CreateNoteRequest = { title: request.title };
    if (request.text !== undefined) body.text = request.text;
    return this.http.post<unknown>('/api/notes', body, { headers: this.headers(token) }).pipe(
      map(body => { if (!isNote(body)) throw new NotesError(-1); return body; }),
      catchError(transportError));
  }
}
export function errorMessage(error: unknown): string {
  const status = error instanceof NotesError ? error.status : -1;
  switch (status) {
    case 400: return 'Сервер отклонил данные. Проверьте заголовок и текст заметки.';
    case 401: return 'Токен недействителен или истёк. Укажите действующий токен подключения.';
    case 403: return 'Нет доступа к заметкам. Обратитесь к владельцу сервера.';
    case 0: return 'Не удалось связаться с сервером. Проверьте подключение.';
    case -1: return 'Сервер вернул неожиданный ответ. Обратитесь к владельцу сервера.';
    default: return 'Ошибка сервера. Попробуйте обновить список позже.';
  }
}
