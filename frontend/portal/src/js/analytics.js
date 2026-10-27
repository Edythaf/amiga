// Metrics use only service.list(actor) records supplied by the UI. No synthetic trends.
export const ANALYTIC_BUCKETS=[
  {key:'done',label:'Selesai / diserahkan',statuses:['SENT_TO_CLIENT'],color:'#57d9ab'},
  {key:'handover',label:'Siap diserahkan',statuses:['AMIGA_REVIEWED'],color:'#8ccad2'},
  {key:'review',label:'Menunggu review',statuses:['READY_FOR_REVIEW'],color:'#9ba7ef'},
  {key:'exception',label:'Perlu tindakan',statuses:['EXCEPTION'],color:'#e6b77d'},
  {key:'processing',label:'Dalam proses',statuses:['QUEUED','PROCESSING'],color:'#87929d'}
];
export function dateKey(value){const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Jakarta',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));return ['year','month','day'].map(k=>parts.find(p=>p.type===k).value).join('-');}
function shiftedDate(key,offset){return new Date(Date.parse(`${key}T12:00:00Z`)+offset*86400000).toISOString().slice(0,10);}
export function summarize(requests,{range='7',now=new Date()}={}){
  const today=dateKey(now),days=range==='30'?30:7,start=shiftedDate(today,1-days);
  const buckets=ANALYTIC_BUCKETS.map(b=>({...b,count:requests.filter(r=>b.statuses.includes(r.status)).length}));
  const completed=buckets[0].count,total=requests.length,remaining=total-completed;
  const activityDays=Array.from({length:days},(_,i)=>({date:shiftedDate(start,i),created:0,completed:0}));
  const activityByDate=new Map(activityDays.map(d=>[d.date,d]));
  for(const r of requests){
    const upload=r.audit.find(e=>e.action==='Unggah invoice');
    if(upload){const point=activityByDate.get(dateKey(upload.at));if(point)point.created++;}
    // One completion per request, latest still-valid voucher review. Repeated downloads never inflate it.
    if(r.status==='SENT_TO_CLIENT'){
      const currentVersion=r.versions.at(-1)?.number;
      const latestReview=r.reviews.findLast(x=>x.status==='APPROVED'&&x.version===currentVersion);
      const issued=r.vouchers.find(x=>x.reviewId===latestReview?.id&&!x.superseded);
      const handover=r.audit.find(e=>e.action==='Unduhan resmi / handover'&&issued&&e.detail.includes(issued.id));
      if(handover){const point=activityByDate.get(dateKey(handover.at));if(point)point.completed++;}
    }
  }
  const team=Array.from(new Set(requests.map(r=>r.pic))).map(pic=>{const items=requests.filter(r=>r.pic===pic);return {pic,total:items.length,completed:items.filter(r=>r.status==='SENT_TO_CLIENT').length,blocked:items.filter(r=>r.status==='EXCEPTION').length};}).sort((a,b)=>b.total-a.total||a.pic.localeCompare(b.pic));
  return {total,completed,remaining,percent:total?Math.round(completed/total*100):0,buckets,activityDays,team,activityCreated:activityDays.reduce((n,d)=>n+d.created,0),activityCompleted:activityDays.reduce((n,d)=>n+d.completed,0)};
}
