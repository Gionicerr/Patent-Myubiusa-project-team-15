# Parking sessions profile: verified, running

API on vm15: http://127.0.0.1:43221
SSH tunnel: ssh -N -p 10015 -L 18881:127.0.0.1:43221 team15@85.143.113.230
Local API: http://127.0.0.1:18881/api/vehicles

Supported operation_id and routes:
- listVehicles: GET /api/vehicles
- listObjects: GET /api/parking-objects?city=spb
- createSession: POST /api/vehicles/{vehicleId}/sessions
- listVehicleSessions: GET /api/vehicles/{vehicleId}/sessions
- confirmSession: POST /api/sessions/{sessionId}/confirm
- listAllSessions: GET /api/admin/sessions

Lists return items/page/pageSize/total (not arrays). POST input shapes, roles and responses are in the full source contract. Only the six listed operations are implemented. All other routes are absent.

Directory: /home/team15/rwb-parking-api-20261031
Runtime directory: runs/parking-sessions
Contract: runs/parking-sessions/project/contract/design.json
OpenAPI: runs/parking-sessions/project/contract/openapi.json
Explicit supported profile: runs/parking-sessions/project/contract/profile.json

Private runtime.env (0600): /home/team15/rwb-parking-api-20261031/runs/parking-sessions/runtime.env
Tokens: DEMO_TOKEN_A (driver-a), DEMO_TOKEN_B (driver-b), DEMO_TOKEN_ADMIN (admin).
Use Authorization: Bearer <token>. Authorized developers obtain only the necessary token via a private SSH session/secret channel. Never commit, archive or paste the token or runtime.env into shared logs. Accounts and owned vehicle IDs are in source-sample.json. Pipeline .env is not application configuration and is never passed to the API.

Reproduce generation with the existing protected Qwen configuration on vm15:
python generate_parking.py --design examples/parking-contracts-reviewed.json --analysis examples/parking-analysis-v2.json --openapi docs/stage2/openapi.json --source spb.json --output runs/parking-new --verify --sudo-docker
This intentionally performs two model calls in a new run: do not execute it just to start the already generated application.

For current application management, without model calls or smoke data creation:
cd /home/team15/rwb-parking-api-20261031/runs/parking-sessions
sudo -v
./manage.sh status
./manage.sh build
./manage.sh start
./manage.sh stop
./manage.sh restart

stop retains rwbgenda9ae29eb0d5_data; restart only restarts API. Do not remove the database volume. The API binds to loopback only. For browser clients with another origin use a development proxy to the SSH tunnel; no CORS, TLS, public ports or client configuration was added.

52/52 real HTTP/SQL checks passed. Includes concurrent idempotent create, replay after API restart, stale revision, conflicts, ownership, forbidden admin access, pagination, JSON response schema, exact persisted session and paymentConfirmed=false. application_verified=true refers ONLY to this profile. Provenance and call metrics are in generation-report.json and project/provenance.json. Existing analytical/notes servers were preserved.

Limits: two-object valid spb sample only; original tariff values, no interpretation. Optional derived geometryGeoJson is nullable JSONB; no spatial index, PostGIS, matching or coordinate operations. No expiry background worker, notifications, payments, industrial identity or full import. PostgreSQL17.9 is the Debian13 package, not Debian12. Angular/mobile integration is not performed.

The smoke run retains two active demo sessions (one per vehicle). These records are intentional evidence; new create on either vehicle currently returns the verified active-session conflict. Read/confirm the existing session, or use a separate fresh verification environment for another creation exercise. Do not delete the verified volume to simulate persistence.
