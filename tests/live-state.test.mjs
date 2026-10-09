import test from 'node:test';
import assert from 'node:assert/strict';
import {visualState,describe,chooseAvatar,validSnapshot,MAX_VISIBLE} from '../web/live-state.js';
import {pathfind,blocked} from '../web/nav.js';
test('approval takes precedence over work and maps to waiting',()=>{assert.equal(visualState({status:'working',approval:true,activity:'typing'}),'waiting');});
test('every lifecycle maps to a supported visual state',()=>{for(const status of ['idle','working','thinking','waiting','done','gone'])assert.ok(describe({status}));assert.equal(visualState({status:'done'}),'leaving');});
test('avatars are stable for a session and cover only the five models',()=>{for(let i=0;i<100;i++){let n=chooseAvatar('session-'+i);assert.equal(n,chooseAvatar('session-'+i));assert.ok(n>=0&&n<5);}});
test('reject foreign state services and malformed agents',()=>{assert.equal(validSnapshot({service:'other',agents:[]}),false);assert.equal(validSnapshot({service:'hermes-virtue-office',agents:[{}]}),false);assert.equal(validSnapshot({service:'hermes-virtue-office',agents:[{id:'abc',status:'working'}]}),true);assert.equal(MAX_VISIBLE,12);});
test('navigation routes around furniture without diagonal corner cuts',()=>{const obs=[{x:0,z:0,w:.2,d:5}],p=pathfind({x:-2,z:0},{x:2,z:0},obs);assert.ok(p?.length);for(const v of p)assert.equal(blocked(v.x,v.z,obs),false);for(let i=1;i<p.length;i++){const a=p[i-1],b=p[i];for(let t=.1;t<1;t+=.1)assert.equal(blocked(a.x+(b.x-a.x)*t,a.z+(b.z-a.z)*t,obs),false);}});
test('unreachable and blocked goals do not teleport characters',()=>{assert.equal(pathfind({x:-2,z:0},{x:0,z:0},[{x:0,z:0,w:1,d:1}]),null);assert.equal(pathfind({x:-2,z:0},{x:2,z:0},[{x:0,z:0,w:1,d:20}]),null);});

import {liveActivity,playgroundActivity} from '../web/activity-text.js';
test('activity bubbles preserve approval and completion while moving',()=>{
 assert.equal(liveActivity({status:'working',approval:true},'arriving',true),'Saya menunggu persetujuan.');
 assert.equal(liveActivity({status:'done'},'leaving',true),'Sesi saya sudah selesai.');
 assert.equal(liveActivity({status:'working',activity:'reading'},'arriving',true),'Saya menuju meja kerja.');
 assert.equal(liveActivity({status:'working',activity:'reading'},'seated',false),'Saya sedang membaca file.');
});
test('manual bubbles explain booting, work and approaching a door',()=>{
 assert.equal(playgroundActivity({state:'booting'}),'Saya menyalakan komputer.');
 assert.equal(playgroundActivity({state:'working'}),'Saya mengerjakan tugas.');
 assert.equal(playgroundActivity({state:'walking',pending:{kind:'door'}}),'Saya menuju pintu.');
});
