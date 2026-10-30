import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { routes } from './app.routes';
import { NOTES_GATEWAY, HttpNotesGateway } from './core/notes-api';
import { MockNotesGateway } from './core/mock-notes-api';
import { environment } from '../environments/environment';
export const appConfig: ApplicationConfig = {
  providers: [provideBrowserGlobalErrorListeners(), provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes), provideHttpClient(),
    { provide: NOTES_GATEWAY, useClass: environment.mock ? MockNotesGateway : HttpNotesGateway }]
};
