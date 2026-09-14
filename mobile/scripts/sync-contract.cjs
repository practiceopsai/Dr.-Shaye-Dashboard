const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, '../frontend/src/lib/api.ts'), 'utf8').replace(/\r\n/g, '\n').split('export const GOOGLE_CREDENTIAL_KEY')[0];
const target = path.join(root, 'src/types.ts');
const existing = fs.readFileSync(target, 'utf8');
const next = '// Synced from frontend/src/lib/api.ts by scripts/sync-contract.cjs.\n' + source + 'export type Approval' + existing.split('export type Approval')[1];
if (process.argv.includes('--check')) {
  if (next !== existing) { console.error('Mobile API types need synchronization. Run node scripts/sync-contract.cjs.'); process.exit(1); }
  console.log('Mobile API contract matches the web client.');
} else fs.writeFileSync(target, next);
