import { Component, OnDestroy, WritableSignal, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { Observable, Subscription } from 'rxjs';
import { ParkingApi, parkingErrorMessage, UUID } from './parking-api';
import { ParkingObject, ParkingPage as Page, ParkingSession, Vehicle, PARKING_PAGE_SIZE } from './parking-models';

interface ListState<T> { page: number; size: number; data: Page<T> | null; loading: boolean; error: string; }
const empty = <T>(): ListState<T> => ({ page: 1, size: PARKING_PAGE_SIZE, data: null, loading: false, error: '' });
@Component({
  selector: 'app-parking-admin',
  imports: [DatePipe, RouterLink, ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatProgressBarModule, MatPaginatorModule],
  templateUrl: './parking-page.html', styleUrl: './parking-page.scss'
})
export class ParkingAdminPage implements OnDestroy {
  private readonly api = inject(ParkingApi);
  private token = '';
  private epoch = 0;
  private readonly requests = new Map<string,Subscription>();
  private readonly vehicleNames = new Map<string,string>();
  private readonly objectNames = new Map<string,string>();
  readonly connected = signal(false);
  readonly tokenInput = new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^\S+$/)] });
  readonly filterInput = new FormControl('', { nonNullable: true, validators: [Validators.pattern(UUID)] });
  readonly filter = signal('');
  readonly vehicles = signal<ListState<Vehicle>>(empty());
  readonly objects = signal<ListState<ParkingObject>>(empty());
  readonly sessions = signal<ListState<ParkingSession>>(empty());
  connect(): void {
    this.tokenInput.markAsTouched();
    if (this.tokenInput.invalid) return;
    const value=this.tokenInput.value;
    this.disconnect();this.token=value;this.tokenInput.reset();this.connected.set(true);this.reload();
  }
  disconnect(): void {
    this.epoch++;this.requests.forEach(r => r.unsubscribe());this.requests.clear();this.token='';
    this.connected.set(false);this.tokenInput.reset();this.filterInput.reset();this.filter.set('');
    this.vehicles.set(empty());this.objects.set(empty());this.sessions.set(empty());
    this.vehicleNames.clear();this.objectNames.clear();
  }
  reload(): void {
    if (!this.connected()) return;
    this.loadVehicles();this.loadObjects();this.loadSessions();
  }
  applyFilter(): void {
    this.filterInput.markAsTouched();if(this.filterInput.invalid)return;
    this.filter.set(this.filterInput.value);this.sessions.update(s => ({...s,page:1}));this.loadSessions();
  }
  vehicleName(id: string): string { return this.vehicleNames.get(id) ?? id; }
  objectName(id: string): string { return this.objectNames.get(id) ?? id; }
  private load<T>(key: string, state: WritableSignal<ListState<T>>, fetch: Observable<Page<T>>, received: (p: Page<T>) => void): void {
    if(!this.connected())return;
    this.requests.get(key)?.unsubscribe();const epoch=this.epoch;
    state.update(s => ({...s,data:null,loading:true,error:''}));
    this.requests.set(key,fetch.subscribe({
      next: p => { if(epoch!==this.epoch)return;received(p); },
      error: e => { if(epoch!==this.epoch)return;state.update(s => ({...s,data:null,loading:false,error:parkingErrorMessage(e)})); }
    }));
  }
  loadVehicles(event?: PageEvent): void {
    if(event)this.vehicles.update(s=>({...s,page:event.pageIndex+1,size:event.pageSize}));
    const s=this.vehicles();
    this.load('vehicles',this.vehicles,this.api.vehicles(this.token,s.page,s.size),p=>{
      p.items.forEach(v=>this.vehicleNames.set(v.id,v.registration+' · '+v.displayName));
      this.vehicles.update(s=>({...s,data:p,loading:false,error:''}));
    });
  }
  loadObjects(event?: PageEvent): void {
    if(event)this.objects.update(s=>({...s,page:event.pageIndex+1,size:event.pageSize}));
    const s=this.objects();
    this.load('objects',this.objects,this.api.objects(this.token,s.page,s.size),p=>{
      p.items.forEach(o=>this.objectNames.set(o.id,o.externalZoneId+' · '+o.displayName));
      this.objects.update(s=>({...s,data:p,loading:false,error:''}));
    });
  }
  loadSessions(event?: PageEvent): void {
    if(event)this.sessions.update(s=>({...s,page:event.pageIndex+1,size:event.pageSize}));
    const s=this.sessions();
    this.load('sessions',this.sessions,this.api.sessions(this.token,s.page,s.size,this.filter()),p=>{
      this.sessions.update(s=>({...s,data:p,loading:false,error:''}));
    });
  }
  ngOnDestroy(): void { this.disconnect(); }
}
