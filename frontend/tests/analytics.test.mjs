import test from 'node:test';import assert from 'node:assert/strict';
import {summarize,dateKey} from '../portal/src/js/analytics.js';
const NOW=new Date('2026-10-12T08:00:00Z');
function request(id,status='READY_FOR_REVIEW',pic='owner-a',date='2026-10-12T03:00:00Z'){
  return {id,status,pic,versions:[{number:1}],reviews:[],vouchers:[],audit:[{action:'Unggah invoice',at:date,detail:'invoice.pdf'}]};
}
function complete(r,at='2026-10-12T04:00:00Z'){
  r.status='SENT_TO_CLIENT';r.reviews=[{id:'review-'+r.id,status:'APPROVED',version:1}];r.vouchers=[{id:'voucher-'+r.id,reviewId:'review-'+r.id,superseded:false}];r.audit.push({action:'Unduhan resmi / handover',at,detail:'voucher-'+r.id+'; downloaded'});return r;
}
test('Completion is handover, not mere review approval; zero states contain no fake metrics',()=>{const s=summarize([request('1'),request('2','AMIGA_REVIEWED'),complete(request('3')),request('4','EXCEPTION')],{now:NOW});assert.equal(s.total,4);assert.equal(s.completed,1);assert.equal(s.remaining,3);assert.equal(s.percent,25);assert.equal(s.buckets.find(b=>b.key==='handover').count,1);const empty=summarize([],{now:NOW});assert.equal(empty.percent,0);assert.equal(empty.activityDays.length,7);assert.equal(empty.activityCompleted,0);});
test('Repeated downloads count one completion and dates use Asia/Jakarta',()=>{const r=complete(request('1'));r.audit.push({action:'Unduhan resmi / handover',at:'2026-10-12T05:00:00Z',detail:'voucher-1; repeat'});const s=summarize([r],{now:NOW});assert.equal(s.activityCompleted,1);assert.equal(s.activityCreated,1);assert.equal(dateKey('2026-10-11T18:00:00Z'),'2026-10-12');});
test('Charts only summarize records supplied by authorized service scope',()=>{const a=[request('A','EXCEPTION','owner-a')],b=[complete(request('B','READY_FOR_REVIEW','owner-b'))];const scoped=summarize(a,{now:NOW});assert.equal(scoped.completed,0);assert.ok(scoped.team.every(t=>t.pic==='owner-a'));const all=summarize([...a,...b],{now:NOW});assert.equal(all.completed,1);assert.equal(all.team.length,2);});
test('Activity range 7/30 excludes old events without inventing history',()=>{const r=request('1','READY_FOR_REVIEW','owner-a','2026-09-20T03:00:00Z');const week=summarize([r],{now:NOW,range:'7'}),month=summarize([r],{now:NOW,range:'30'});assert.equal(week.activityCreated,0);assert.equal(month.activityCreated,1);assert.equal(month.activityDays.length,30);});
test('Superseded approval cannot inflate current completion analytics',()=>{const r=complete(request('1'));r.versions.push({number:2});r.status='READY_FOR_REVIEW';r.vouchers[0].superseded=true;assert.equal(summarize([r],{now:NOW}).activityCompleted,0);complete(r);r.reviews[0].version=2;assert.equal(summarize([r],{now:NOW}).completed,1);});
