const assert = require('node:assert/strict');
const path = require('node:path');
const file = path.resolve(__dirname, '../proxy.conf.cjs');
process.env.NOTES_API_URL = 'http://127.0.0.1:18880';
process.env.PARKING_API_URL = 'http://127.0.0.1:18881';
let proxy = require(file);
assert.equal(proxy['/api/notes'].target, 'http://127.0.0.1:18880');
for (const key of ['/api/vehicles','/api/parking-objects','/api/admin/sessions']) assert.equal(proxy[key].target,'http://127.0.0.1:18881');
assert.equal(proxy['/api'], undefined);
for (const value of ['http://user:secret@example.invalid','http://localhost/api?token=x']) {
  delete require.cache[file];process.env.PARKING_API_URL=value;
  assert.throws(()=>require(file),/PARKING_API_URL must/);
}
console.log('Parking proxy tests passed: separate origins, explicit prefixes, invalid target rejection.');
