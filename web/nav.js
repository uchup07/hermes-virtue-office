// Grid A* navigation with clearance around furniture. Doors are traversable links;
// the controller opens them before a character crosses their threshold.
export const STEP=.22, MINX=-5.95,MINZ=-5.4,MAXX=5.95,MAXZ=5.35;
export function blocked(x,z,obstacles,margin=.20){return x<MINX||x>MAXX||z<MINZ||z>MAXZ||obstacles.some(o=>Math.abs(x-o.x)<o.w/2+margin&&Math.abs(z-o.z)<o.d/2+margin);}
export function pathfind(from,to,obstacles){
 const nx=Math.floor((MAXX-MINX)/STEP)+1,nz=Math.floor((MAXZ-MINZ)/STEP)+1;
 const cell=p=>[Math.max(0,Math.min(nx-1,Math.round((p.x-MINX)/STEP))),Math.max(0,Math.min(nz-1,Math.round((p.z-MINZ)/STEP)))];
 const pos=(x,z)=>({x:MINX+x*STEP,z:MINZ+z*STEP});const id=(x,z)=>z*nx+x;
 const [sx,sz]=cell(from);let [tx,tz]=cell(to);
 if(blocked(to.x,to.z,obstacles))return null;
 if(blocked(pos(tx,tz).x,pos(tx,tz).z,obstacles)){let best=null;for(let dx=-2;dx<=2;dx++)for(let dz=-2;dz<=2;dz++){const p=pos(tx+dx,tz+dz);if(!blocked(p.x,p.z,obstacles)&&(!best||dx*dx+dz*dz<best.d))best={x:tx+dx,z:tz+dz,d:dx*dx+dz*dz};}if(!best)return null;tx=best.x;tz=best.z;}
 const start=id(sx,sz),goal=id(tx,tz),open=[start],closed=new Set(),g=new Map([[start,0]]),f=new Map([[start,0]]),came=new Map();
 const valid=(x,z)=>x>=0&&z>=0&&x<nx&&z<nz&&!blocked(pos(x,z).x,pos(x,z).z,obstacles);
 let steps=0;
 while(open.length&&steps++<6000){let bi=0;for(let i=1;i<open.length;i++)if(f.get(open[i])<f.get(open[bi]))bi=i;const cur=open.splice(bi,1)[0];if(cur===goal){const path=[];let q=cur;while(q!==start){path.push(pos(q%nx,Math.floor(q/nx)));q=came.get(q);}path.reverse();path.push({x:to.x,z:to.z});return path;}
 closed.add(cur);const x=cur%nx,z=Math.floor(cur/nx);
 for(const [dx,dz] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,1],[1,-1],[-1,-1]]){const xx=x+dx,zz=z+dz,n=id(xx,zz);if(closed.has(n)||!valid(xx,zz))continue;if(dx&&dz&&(!valid(x+dx,z)||!valid(x,z+dz)))continue;const score=g.get(cur)+(dx&&dz?1.414:1);if(score<(g.get(n)??Infinity)){came.set(n,cur);g.set(n,score);f.set(n,score+Math.hypot(tx-xx,tz-zz));if(!open.includes(n))open.push(n);}}
 }return null;
}
