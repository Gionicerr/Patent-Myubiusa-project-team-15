// Explicit API prefixes only: notes and parking use different local SSH tunnels.
const target = process.env.NOTES_API_URL;
if (!target) throw new Error('Set NOTES_API_URL to the actual ASP.NET API origin before npm start.');
const url = new URL(target);
if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
  throw new Error('NOTES_API_URL must be an HTTP(S) origin without credentials, path or query.');
}
const parking = new URL(process.env.PARKING_API_URL || 'http://127.0.0.1:18881');
if (!['http:', 'https:'].includes(parking.protocol) || parking.username || parking.password || parking.pathname !== '/' || parking.search || parking.hash) {
  throw new Error('PARKING_API_URL must be an HTTP(S) origin without credentials, path or query.');
}
module.exports = {
  '/api/notes': { target: url.origin, secure: true, changeOrigin: true },
  ...Object.fromEntries(['/api/vehicles','/api/parking-objects','/api/admin/sessions'].map(path =>
    [path, { target: parking.origin, secure: true, changeOrigin: true }]))
};
