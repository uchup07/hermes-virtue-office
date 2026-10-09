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

import {desiredLocation,freeLoungeSpot,loungeSpots} from '../web/lounge.js';
test('idle rests in the lounge; work, thinking and approvals return to the desk',()=>{
 assert.equal(desiredLocation({status:'idle'}),'lounge');
 for(const status of ['working','thinking','waiting'])assert.equal(desiredLocation({status}),'desk');
 assert.equal(desiredLocation({status:'idle',approval:true}),'desk');
 assert.equal(liveActivity({status:'idle'},'to-lounge',true),'Saya menuju ruang santai.');
 assert.equal(liveActivity({status:'idle'},'lounging',false),'Saya beristirahat, siap untuk tugas baru.');
});
test('lounge spots are exclusive and sofa approaches avoid furniture',()=>{
 const occupants=loungeSpots.map((loungeSpot,i)=>({id:String(i),loungeSpot}));
 assert.equal(freeLoungeSpot(occupants),undefined);
 assert.equal(freeLoungeSpot(occupants,'2'),loungeSpots[2]);
 assert.equal(freeLoungeSpot(occupants.map(c=>c.id==='2'?{...c,exitComplete:true}:c)),loungeSpots[2]);
 const furniture=[{x:5.3,z:3.46,w:1.2,d:2.9},{x:3.61,z:3.42,w:.98,d:1.94},{x:5.22,z:.65,w:1.43,d:.6}];
 for(const spot of loungeSpots){assert.equal(blocked(spot.x,spot.z,furniture),false);assert.ok(pathfind({x:1.45,z:5.1},spot,furniture));}
});
