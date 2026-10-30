import { Component, OnDestroy, ViewChild, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormControl, FormGroup, ReactiveFormsModule, Validators, AbstractControl, FormGroupDirective } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Subscription } from 'rxjs';
import { Note } from '../core/models';
import { NOTES_GATEWAY, NotesError, errorMessage } from '../core/notes-api';
import { environment } from '../../environments/environment';

export function nonBlank(control: AbstractControl) {
  return typeof control.value === 'string' && !control.value.trim() ? { blank: true } : null;
}
@Component({
  selector: 'app-notes-page',
  imports: [DatePipe, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatProgressBarModule],
  templateUrl: './notes-page.html', styleUrl: './notes-page.scss'
})
export class NotesPage implements OnDestroy {
  private readonly api = inject(NOTES_GATEWAY);
  readonly mock = environment.mock;
  readonly connected = signal(false);
  readonly notes = signal<Note[]>([]);
  readonly loading = signal(false);
  readonly loaded = signal(false);
  readonly saving = signal(false);
  readonly listError = signal('');
  readonly saveError = signal('');
  readonly success = signal('');
  readonly mustCheckList = signal(false);
  readonly tokenInput = new FormControl('', { nonNullable: true, validators: [Validators.required, nonBlank] });
  readonly form = new FormGroup({
    title: new FormControl('', { nonNullable: true, validators: [Validators.required, nonBlank, Validators.maxLength(100)] }),
    text: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(2000)] })
  });
  @ViewChild(FormGroupDirective) private formDirective?: FormGroupDirective;
  private resetDraft(): void {
    if (this.formDirective) this.formDirective.resetForm(); else this.form.reset();
  }
  private token = '';
  private epoch = 0;
  private listSub?: Subscription;
  private saveSub?: Subscription;

  connect(): void {
    this.tokenInput.markAsTouched();
    const token = this.tokenInput.value;
    if (this.tokenInput.invalid || /[\r\n]/.test(token)) return;
    this.changeSession(token);
  }
  startDemo(): void { this.changeSession('fictitious-demo-token'); }
  disconnect(): void { this.changeSession(''); }
  private changeSession(token: string): void {
    this.epoch++;
    this.listSub?.unsubscribe(); this.saveSub?.unsubscribe();
    this.token = token; this.tokenInput.reset();
    this.notes.set([]); this.loaded.set(false); this.loading.set(false); this.saving.set(false);
    this.listError.set(''); this.saveError.set(''); this.success.set(''); this.mustCheckList.set(false);
    this.resetDraft(); this.connected.set(!!token);
    if (token) this.reload();
  }
  reload(): void {
    if (!this.connected() || this.saving()) return;
    this.listSub?.unsubscribe();
    const epoch = this.epoch;
    this.loading.set(true); this.listError.set('');
    this.listSub = this.api.list(this.token).subscribe({
      next: notes => {
        if (epoch !== this.epoch) return;
        this.notes.set(notes); this.loaded.set(true); this.loading.set(false); this.mustCheckList.set(false);
      },
      error: error => {
        if (epoch !== this.epoch) return;
        this.notes.set([]); this.loaded.set(false); this.loading.set(false);
        this.listError.set(errorMessage(error));
      }
    });
  }
  submit(): void {
    if (!this.connected() || this.saving() || this.mustCheckList()) return;
    this.form.markAllAsTouched();
    if (this.form.invalid) return;
    const epoch = this.epoch;
    this.saving.set(true); this.saveError.set(''); this.success.set('');
    this.saveSub = this.api.create(this.token, this.form.getRawValue()).subscribe({
      next: () => {
        if (epoch !== this.epoch) return;
        this.saving.set(false); this.resetDraft();
        this.success.set('Заметка создана.');
        this.reload();
      },
      error: error => {
        if (epoch !== this.epoch) return;
        this.saving.set(false);
        const uncertain = !(error instanceof NotesError) || error.status === 0 || error.status === -1 || error.status >= 500;
        this.mustCheckList.set(uncertain);
        this.saveError.set(errorMessage(error) + (uncertain
          ? ' Результат создания неизвестен. Обновите список перед новой отправкой, чтобы избежать дубликата.' : ''));
      }
    });
  }
  ngOnDestroy(): void {
    this.epoch++; this.listSub?.unsubscribe(); this.saveSub?.unsubscribe(); this.token = '';
  }
}
