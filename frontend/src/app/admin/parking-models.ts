// Types projected from contracts/parking-contracts-reviewed.json; UUID/date-time remain strings.
export interface Vehicle {
  id: string;
  driverId: string;
  registration: string;
  displayName: string;
  sourceCity: "spb" | "moscow_partner";
}
export interface ParkingObject {
  id: string;
  city: string;
  externalZoneId: string;
  displayName: string;
  geometry: string;
  price: number;
  priceDescription: string;
  minTime: number;
  timeStep: number;
  tariff: { hasHolidays: boolean; periods: ({ from: number | null; to: number | null; duration: number | null; price: number; type: string })[] };
  entityState: string;
  initDate: string;
  lastSyncedAt: string;
  importBatchId: string;
  geometryGeoJson?: unknown | null;
  geometryState: "valid" | "quarantined";
}
export interface ParkingSession {
  id: string;
  vehicleId: string;
  objectId: string;
  routeId?: string | null;
  startedAt: string;
  endAt: string;
  status: "active" | "expired";
  paymentConfirmed: false;
  revision: number;
}
export interface ParkingPage<T> { items: T[]; page: number; pageSize: number; total: number; }
export const PARKING_PAGE_SIZE = 50;
export const PARKING_MAX_PAGE_SIZE = 100;
