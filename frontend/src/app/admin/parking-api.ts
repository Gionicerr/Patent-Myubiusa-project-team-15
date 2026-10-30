import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Observable, catchError, map, throwError } from 'rxjs';
import { ParkingObject, ParkingPage, ParkingSession, Vehicle, PARKING_MAX_PAGE_SIZE } from './parking-models';

export class ParkingError extends Error {
  constructor(readonly status: number) { super('Parking request failed'); }
}
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const record = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const strings = (x: Record<string, unknown>, keys: string[]) => keys.every(k => typeof x[k] === 'string');
const id = (x: unknown): x is string => typeof x === 'string' && UUID.test(x);
function vehicle(x: unknown): x is Vehicle {
  return record(x) && id(x['id']) && id(x['driverId']) && strings(x, ['registration','displayName'])
    && ['spb','moscow_partner'].includes(x['sourceCity'] as string);
}
function object(x: unknown): x is ParkingObject {
  return record(x) && id(x['id']) && strings(x, ['city','externalZoneId','displayName','geometry','priceDescription'])
    && Number.isSafeInteger(x['price']) && record(x['tariff']);
}
function session(x: unknown): x is ParkingSession {
  return record(x) && ['id','vehicleId','objectId'].every(k => id(x[k]))
    && (x['routeId'] === undefined || x['routeId'] === null || id(x['routeId']))
    && ['startedAt','endAt'].every(k => typeof x[k] === 'string' && Number.isFinite(Date.parse(x[k] as string)))
    && ['active','expired'].includes(x['status'] as string) && x['paymentConfirmed'] === false
    && Number.isSafeInteger(x['revision']) && (x['revision'] as number) >= 1;
}
function page<T>(value: unknown, item: (x: unknown) => x is T, requestedPage: number, requestedSize: number): ParkingPage<T> {
  if (!record(value) || Object.keys(value).some(k => !['items','page','pageSize','total'].includes(k))
    || !Array.isArray(value['items']) || !value['items'].every(item)
    || value['page'] !== requestedPage || value['pageSize'] !== requestedSize
    || !Number.isSafeInteger(value['total']) || (value['total'] as number) < 0
    || value['items'].length > requestedSize) throw new ParkingError(-1);
  return value as unknown as ParkingPage<T>;
}
@Injectable({ providedIn: 'root' })
export class ParkingApi {
  private readonly http = inject(HttpClient);
  private get<T>(path: string, token: string, current: number, size: number, item: (x: unknown) => x is T, extra: Record<string,string> = {}): Observable<ParkingPage<T>> {
    if (!Number.isInteger(current) || current < 1 || !Number.isInteger(size) || size < 1 || size > PARKING_MAX_PAGE_SIZE) {
      return throwError(() => new ParkingError(-1));
    }
    const params = new HttpParams({ fromObject: { ...extra, page: String(current), pageSize: String(size) } });
    return this.http.get<unknown>(path, { params, headers: { Authorization: `Bearer ${token}` } }).pipe(
      map(value => page(value, item, current, size)),
      catchError(error => throwError(() => error instanceof ParkingError ? error
        : new ParkingError(error instanceof HttpErrorResponse ? error.status : -1))));
  }
  vehicles(token: string, current: number, size: number) {
    return this.get('/api/vehicles',token,current,size,vehicle);
  }
  objects(token: string, current: number, size: number) {
    return this.get('/api/parking-objects',token,current,size,object,{ city: 'spb' });
  }
  sessions(token: string, current: number, size: number, vehicleId = '') {
    if (vehicleId && !UUID.test(vehicleId)) return throwError(() => new ParkingError(-1));
    return this.get('/api/admin/sessions',token,current,size,session,vehicleId ? { vehicleId } : {});
  }
}
export function parkingErrorMessage(error: unknown): string {
  const status = error instanceof ParkingError ? error.status : -1;
  if (status === 401) return 'Токен недействителен. Подключитесь с действующим токеном.';
  if (status === 403) return 'Доступ запрещён. Для списка всех сессий нужен токен администратора.';
  if (status === 0) return 'Нет связи с парковочным API. Проверьте SSH-туннель и dev-proxy.';
  if (status === -1) return 'Неожиданный формат ответа парковочного API.';
  return 'Не удалось загрузить данные. Попробуйте обновить список.';
}
