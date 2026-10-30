import { Routes } from '@angular/router';
import { NotesPage } from './notes/notes-page';
export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'notes' },
  { path: 'notes', component: NotesPage },
  { path: '**', redirectTo: 'notes' }
];
