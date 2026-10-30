import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, Subject, of, throwError } from 'rxjs';
import { ParkingApi, ParkingError } from './parking-api';
import { ParkingAdminPage } from './parking-page';
import { ParkingPage, Vehicle } from './parking-models';

describe('Parking admin page',()=>{
  let api:jasmine.SpyObj<ParkingApi>;
  beforeEach(async()=>{
    api=jasmine.createSpyObj<ParkingApi>('ParkingApi',['vehicles','objects','sessions']);
    api.vehicles.and.returnValue(of({items:[],page:1,pageSize:50,total:0}));
    api.objects.and.returnValue(of({items:[],page:1,pageSize:50,total:0}));
    api.sessions.and.returnValue(of({items:[],page:1,pageSize:50,total:0}));
    await TestBed.configureTestingModule({imports:[ParkingAdminPage],providers:[provideRouter([]),{provide:ParkingApi,useValue:api}]}).compileComponents();
  });
  function setup(){const fixture=TestBed.createComponent(ParkingAdminPage);fixture.detectChanges();return fixture;}
  it('does not load until explicitly connected; clears token input',()=>{
    const f=setup(),c=f.componentInstance;expect(api.sessions).not.toHaveBeenCalled();
    c.tokenInput.setValue('unit-only');c.connect();f.detectChanges();
    expect(c.tokenInput.value).toBe('');expect(api.sessions).toHaveBeenCalledOnceWith('unit-only',1,50,'');
    expect(f.nativeElement.textContent).toContain('Сессии не найдены.');
  });
  it('connects through the actual HTML form submission without reloading',()=>{
    const f=setup();f.componentInstance.tokenInput.setValue('unit-only');
    const event=new Event('submit',{bubbles:true,cancelable:true});
    f.nativeElement.querySelector('form').dispatchEvent(event);
    expect(event.defaultPrevented).toBeTrue();expect(api.sessions).toHaveBeenCalled();
    expect(f.componentInstance.tokenInput.value).toBe('');
  });
  it('uses requested session pagination, refresh and optional UUID filter',()=>{
    const c=setup().componentInstance;c.tokenInput.setValue('unit-only');c.connect();
    c.loadSessions({pageIndex:1,pageSize:10,length:30});expect(api.sessions).toHaveBeenCalledWith('unit-only',2,10,'');
    c.filterInput.setValue('0f32d15d-2f95-5b5d-b2e2-d9fe14f1f848');c.applyFilter();
    expect(api.sessions).toHaveBeenCalledWith('unit-only',1,10,c.filterInput.value);
    c.loadSessions();expect(api.sessions.calls.count()).toBe(4);
  });
  it('renders 403 and never falls back to mock sessions',()=>{
    api.sessions.and.returnValue(throwError(()=>new ParkingError(403)));
    const f=setup(),c=f.componentInstance;c.tokenInput.setValue('driver-unit');c.connect();f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Доступ запрещён');expect(c.sessions().data).toBeNull();
  });
  it('shows loading then empty or a safe error',()=>{
    const pending=new Subject<ParkingPage<Vehicle>>();api.vehicles.and.returnValue(pending);
    const f=setup(),c=f.componentInstance;c.tokenInput.setValue('unit-only');c.connect();f.detectChanges();
    expect(f.nativeElement.textContent).toContain('Загружаем автомобили');
    pending.error(new ParkingError(0));f.detectChanges();expect(f.nativeElement.textContent).toContain('Нет связи');
    expect(c.vehicles().loading).toBeFalse();
  });
  it('cancels pending requests and clears data on disconnect',()=>{
    let cancelled=false;api.sessions.and.returnValue(new Observable(()=>()=>{cancelled=true;}));
    const c=setup().componentInstance;c.tokenInput.setValue('unit-only');c.connect();c.disconnect();
    expect(cancelled).toBeTrue();expect(c.connected()).toBeFalse();expect(c.sessions().data).toBeNull();
    expect(c.tokenInput.value).toBe('');
  });
  it('does not send an invalid filter',()=>{
    const c=setup().componentInstance;c.tokenInput.setValue('unit-only');c.connect();
    c.filterInput.setValue('bad');c.applyFilter();expect(api.sessions.calls.count()).toBe(1);
  });
});
