// Only the notes API is proxied; never forward the Python panel or model API.
const target = process.env.NOTES_API_URL;
if (!target) throw new Error('Set NOTES_API_URL to the actual ASP.NET API origin before npm start.');
const url = new URL(target);
if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
  throw new Error('NOTES_API_URL must be an HTTP(S) origin without credentials, path or query.');
}
module.exports = { '/api/notes': { target: url.origin, secure: true, changeOrigin: true } };
