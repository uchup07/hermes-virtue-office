import {visualState} from './live-state.js';
// Approach points stay outside the sofa/table collision boxes. Sitting positions
// are reached only after arriving at the approach point, like taking a chair.
export const loungeSpots = [
  ...[2.43,3.46,4.49].map(z=>({x:4.4,z,sitX:5.12,sitZ:z,height:.15,angle:-Math.PI/2,sitting:true})),
  {x:2.2,z:3.45,angle:Math.PI/2,sitting:true},
  {x:1.6,z:2.05,angle:Math.PI/2},
  {x:2.6,z:2,angle:0},
  {x:3.6,z:1.8,angle:0},
  {x:4.6,z:1.6,angle:-Math.PI/4},
  {x:1.5,z:4.55,angle:Math.PI/2},
  {x:2.4,z:4.65,angle:Math.PI},
  {x:3.4,z:4.8,angle:Math.PI},
  {x:4.4,z:5.2,angle:Math.PI}
];
export function desiredLocation(agent) {return visualState(agent)==='idle'?'lounge':'desk';}
export function freeLoungeSpot(characters, excludeId) {
  const occupied=new Set([...characters].filter(c=>c.id!==excludeId&&!c.exitComplete).map(c=>c.loungeSpot));
  return loungeSpots.find(spot=>!occupied.has(spot));
}
