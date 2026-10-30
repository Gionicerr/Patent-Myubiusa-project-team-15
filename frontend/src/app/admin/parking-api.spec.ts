import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ParkingApi, ParkingError, parkingErrorMessage } from './parking-api';

describe('Parking readonly HTTP contract', () => {
  let api: ParkingApi;let http: HttpTestingController;
  beforeEach(()=>{
    TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});
    api=TestBed.inject(ParkingApi);http=TestBed.inject(HttpTestingController);
  });
  afterEach(()=>http.verify());
  it('uses paginated vehicles and only an explicit bearer header',()=>{
    let received=false;
    api.vehicles('unit-only',2,10).subscribe(p=>received=p.total===0);
    const r=http.expectOne(r=>r.url==='/api/vehicles');expect(r.request.method).toBe('GET');
    expect(r.request.params.get('page')).toBe('2');expect(r.request.params.get('pageSize')).toBe('10');
    expect(r.request.headers.get('Authorization')).toBe('Bearer unit-only');expect(r.request.body).toBeNull();
    r.flush({items:[],page:2,pageSize:10,total:0});expect(received).toBeTrue();
  });
  it('requires source city spb for objects',()=>{
    api.objects('unit-only',1,50).subscribe();const r=http.expectOne(r=>r.url==='/api/parking-objects');
    expect(r.request.params.get('city')).toBe('spb');r.flush({items:[],page:1,pageSize:50,total:0});
  });
  it('adds the optional vehicle filter and supports unfiltered sessions',()=>{
    const id='0f32d15d-2f95-5b5d-b2e2-d9fe14f1f848';
    api.sessions('unit-only',3,25,id).subscribe();let r=http.expectOne(r=>r.url==='/api/admin/sessions');
    expect(r.request.params.get('vehicleId')).toBe(id);r.flush({items:[],page:3,pageSize:25,total:0});
    api.sessions('unit-only',1,50).subscribe();r=http.expectOne(r=>r.url==='/api/admin/sessions');
    expect(r.request.params.has('vehicleId')).toBeFalse();r.flush({items:[],page:1,pageSize:50,total:0});
  });
  it('rejects invalid pagination/filter before sending requests',()=>{
    api.vehicles('unit-only',1,101).subscribe({error:e=>expect(e instanceof ParkingError).toBeTrue()});
    api.sessions('unit-only',1,50,'not-uuid').subscribe({error:e=>expect(e instanceof ParkingError).toBeTrue()});
    http.expectNone(()=>true);
  });
  for(const status of [0,401,403,503])it(`handles ${status} without raw messages, retry or mock fallback`,()=>{
    api.sessions('unit-only',1,50).subscribe({error:e=>{
      expect(e.status).toBe(status);expect(parkingErrorMessage(e)).not.toContain('RAW_PRIVATE_ERROR');
    }});
    const r=http.expectOne(r=>r.url==='/api/admin/sessions');
    if(status===0)r.error(new ProgressEvent('error'));else r.flush('RAW_PRIVATE_ERROR',{status,statusText:'Error'});
  });
  for(const body of [[],{items:[],page:1,pageSize:50,total:-1},{items:[{}],page:1,pageSize:50,total:1},
    {items:[],page:2,pageSize:50,total:0}])it('rejects a malformed page instead of inventing data',()=>{
    api.sessions('unit-only',1,50).subscribe({error:e=>expect(e.status).toBe(-1)});
    http.expectOne(r=>r.url==='/api/admin/sessions').flush(body);
  });
});
