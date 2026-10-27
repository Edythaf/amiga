import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
const project=fileURLToPath(new URL('../../',import.meta.url)),portal=path.join(project,'frontend','portal'),target=path.join(project,'frontend','dist');
if(path.dirname(target)!==path.join(project,'frontend')||path.basename(target)!=='dist')throw Error('Unsafe build target.');
for(const name of ['api-client.js','portal-policy.js','demo-adapter.js','analytics.js','login-view.js'])await import(new URL('../portal/src/js/'+name,import.meta.url));
for(const name of ['index.html','src/js/portal.js','src/css/portal.css','public/fixtures/manifest.json'])await fs.access(path.join(portal,name));
await fs.rm(target,{recursive:true,force:true});await fs.cp(portal,target,{recursive:true});console.log('Frontend build OK: frontend/dist. Backend tidak diubah.');
