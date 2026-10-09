import * as T from 'three';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {mergeGeometries} from './vendor/BufferGeometryUtils.js';
export const people=[
 {name:'Navy',role:'Manajer',color:'#304e69',file:'01_Manager_Navy.glb',start:[-3.6,-2.70],station:0},
 {name:'Amber',role:'Desainer',color:'#d49a36',file:'02_Worker_Orange_Yellow.glb',start:[-4.7,1.30],station:1},
 {name:'Midnight',role:'Developer',color:'#42404b',file:'03_Worker_Dark_Purple.glb',start:[-2.15,1.30],station:2},
 {name:'Moss',role:'Operasional',color:'#719445',file:'04_Worker_Brown_Green.glb',start:[-4.7,3.90],station:3},
 {name:'Charcoal',role:'Analis',color:'#65716e',file:'05_Worker_Black_Charcoal.glb',start:[-2.15,3.90],station:4}
];
function mergePart(list,pivot,name){if(!list.length)return;const byMat=new Map();for(const mesh of list){const key=mesh.material.uuid;if(!byMat.has(key))byMat.set(key,{m:mesh.material,g:[]});const geo=mesh.geometry.clone().applyMatrix4(mesh.matrixWorld);for(const a of Object.keys(geo.attributes))if(!['position','normal'].includes(a))geo.deleteAttribute(a);geo.translate(-pivot.x,-pivot.y,-pivot.z);byMat.get(key).g.push(geo);}const group=new T.Group();group.name=name;group.position.copy(pivot);for(const {m,g} of byMat.values()){const mesh=new T.Mesh(mergeGeometries(g),m);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);g.forEach(x=>x.dispose());}return group;}
const modelCache=new Map();
export async function loadCharacter(info){if(!modelCache.has(info.file))modelCache.set(info.file,new GLTFLoader().loadAsync('./assets/'+info.file));const gltf=await modelCache.get(info.file);gltf.scene.updateMatrixWorld(true);const meshes=[];gltf.scene.traverse(o=>{if(o.isMesh)meshes.push(o);});
 const root=new T.Group();root.name=info.name;const body=new T.Group();root.add(body);body.scale.setScalar(.62);
 const parts={torso:[],la:[],ra:[],lf:[],rf:[],ll:[],rl:[],ls:[],rs:[]};let legMat;
 for(const m of meshes){const n=m.name.replaceAll('_',' ').toLowerCase();const bounds=new T.Box3().setFromObject(m);const side=bounds.getCenter(new T.Vector3()).x<0?'l':'r';
 if(n.startsWith('upper sleeve'))parts[side+'a'].push(m);
 else if(['lower sleeve','cuff','hand','thumb'].some(s=>n.startsWith(s)))parts[side+'f'].push(m);
 else if(n.startsWith('trouser leg')){legMat=m.material;}
 else if(n.startsWith('pressed trouser'))continue;
 else if(n.startsWith('shorts'))parts[side+'l'].push(m);
 else if(['shoe','trouser cuff','bare shin'].some(s=>n.startsWith(s)))parts[side+'s'].push(m);
 else parts.torso.push(m);
 }
 const torso=mergePart(parts.torso,new T.Vector3(),'Torso and head');body.add(torso);const limbs={};
 for(const [side,x] of [['l',-.423],['r',.423]]){
 const arm=mergePart(parts[side+'a'],new T.Vector3(x,1.49,0),side+' shoulder');body.add(arm);
 const fore=mergePart(parts[side+'f'],new T.Vector3(x,1.16,0),side+' elbow');body.add(fore);body.updateMatrixWorld(true);arm.attach(fore);
 let thigh=mergePart(parts[side+'l'],new T.Vector3(Math.sign(x)*.185,.83,0),side+' hip');if(!thigh){thigh=new T.Group();thigh.position.set(Math.sign(x)*.185,.83,0);}
 if(legMat){const t=new T.Mesh(new T.BoxGeometry(.254,.33,.32),legMat);t.position.y=-.165;t.castShadow=true;thigh.add(t);}
 body.add(thigh);let shin=mergePart(parts[side+'s'],new T.Vector3(Math.sign(x)*.185,.5,0),side+' knee');body.add(shin);
 if(legMat){const s=new T.Mesh(new T.BoxGeometry(.254,.25,.32),legMat);s.position.y=-.125;s.castShadow=true;shin.add(s);}
 body.updateMatrixWorld(true);thigh.attach(shin);limbs[side]={arm,fore,thigh,shin};
 }
 root.position.set(...[info.start[0],0,info.start[1]]);root.rotation.y=0;
 return {...info,root,body,limbs,state:'idle',path:[],pending:null,seat:null,progress:0,done:0,phase:0,bootTime:0};
}
export function animateCharacter(c,dt,t){const walk=c.state==='walking',sit=['sitting','working','booting'].includes(c.state),work=c.state==='working',boot=c.state==='booting';const lerp=(obj,target)=>{obj.rotation.x=T.MathUtils.damp(obj.rotation.x,target,13,dt);};c.phase+=dt*(walk?10:3);for(const [side,sign] of [['l',1],['r',-1]]){const l=c.limbs[side];lerp(l.thigh,sit?-Math.PI/2:walk?Math.sin(c.phase)*.48*sign:0);lerp(l.shin,sit?Math.PI/2:walk?Math.max(0,-Math.sin(c.phase)*sign)*.40:0);lerp(l.arm,work?-.92+(Math.sin(t*10+sign)*.035):boot?(side==='r'?-1.35:-.4):sit?-.5:walk?-Math.sin(c.phase)*.42*sign:0);lerp(l.fore,work?-1.0+Math.sin(t*13+sign)*.10:boot?(side==='r'?-.25:0):sit?-.5:0);}
 c.body.position.y=T.MathUtils.damp(c.body.position.y,sit?.045:walk?Math.abs(Math.sin(c.phase))*.025:Math.sin(t*2+c.station)*.004,12,dt);
}
