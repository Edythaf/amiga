export const USERS = [
  {id:'owner-a', name:'Nadia • Owner A', roles:['OWNER'], clients:['A']},
  {id:'backup-a', name:'Bima • Backup A', roles:['BACKUP'], clients:['A']},
  {id:'finance', name:'Rani • Finance Reviewer', roles:['REVIEWER'], clients:['A','B']},
  {id:'lead', name:'Dimas • Service Lead', roles:['LEAD'], clients:['A','B']},
  {id:'admin', name:'Sinta • System Admin', roles:['ADMIN'], clients:['A','B']},
  {id:'owner-b', name:'Arif • Owner B', roles:['OWNER'], clients:['B']}
];
export function user(id) { const u = USERS.find(x=>x.id===id); if(!u) throw Error('Identitas demo tidak dikenal.'); return u; }
export function assertTenant(state, actor, client) {
  const u = user(actor);
  if((state.disabledUsers??[]).includes(actor)) throw Error('Akses ditolak: akun demo dinonaktifkan oleh Admin.');
  if(!u.clients.includes(client) || (u.roles.includes('BACKUP') && !state.backupActive)) throw Error('Akses ditolak: klien di luar penugasan atau delegasi Backup tidak aktif.');
  return u;
}
export function access(state, actor, id) {
  const r=state.requests.find(x=>x.id===id); if(!r) throw Error('Request tidak ditemukan.'); assertTenant(state,actor,r.client); return r;
}
export function assertUpload(state, actor, client) {
  const u=assertTenant(state,actor,client); if(!u.roles.some(x=>['OWNER','BACKUP','REVIEWER'].includes(x))) throw Error('Peran ini tidak memiliki hak unggah.'); return u;
}
export function assertEdit(state, actor, request) {
  const u=assertTenant(state,actor,request.client); if(!u.roles.some(x=>['OWNER','BACKUP','REVIEWER'].includes(x))) throw Error('Peran ini tidak dapat mengoreksi draft.'); return u;
}
export function assertReviewer(state, actor, request) {
  const u=assertTenant(state,actor,request.client);
  if(!u.roles.includes('REVIEWER') || u.roles.includes('ADMIN')) throw Error('Persetujuan hanya untuk Finance Reviewer yang berwenang.');
  if(request.uploader===actor || request.documents.some(d=>d.uploadedBy===actor)) throw Error('Pemisahan tugas: pengunggah tidak boleh menyetujui dokumennya sendiri.');
  return u;
}
export function assertFinance(state, actor, request) {
  const u=assertTenant(state,actor,request.client); if(!u.roles.includes('REVIEWER') || u.roles.includes('ADMIN')) throw Error('Tindakan ini memerlukan Finance Reviewer.'); return u;
}
