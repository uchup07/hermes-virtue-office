import {Vector3} from 'three';
const projection = new Vector3();
export function createBubble(container) {
  const element = document.createElement('div');
  element.className = 'activity-bubble';
  const name = document.createElement('strong');
  const message = document.createElement('span');
  element.append(name, message);
  container.append(element);
  return {element, name, message};
}
export function updateBubble(bubble, name, message, {selected=false, waiting=false, subagent=false}={}) {
  if (bubble.name.textContent !== name) bubble.name.textContent = name;
  if (bubble.message.textContent !== message) bubble.message.textContent = message;
  bubble.element.classList.toggle('selected', selected);
  bubble.element.classList.toggle('waiting', waiting);
  bubble.element.classList.toggle('subagent', subagent);
}
export function placeBubbles(characters, camera, canvas) {
  const bounds = canvas.getBoundingClientRect();
  const placed = [];
  // Selected character gets its preferred position when bubbles cluster together.
  const ordered = [...characters].sort((a,b) => Number(b.bubble.element.classList.contains('selected')) - Number(a.bubble.element.classList.contains('selected')));
  for (const character of ordered) {
    const element = character.bubble.element;
    projection.copy(character.root.position);
    projection.y += 1.78;
    projection.project(camera);
    if (!character.root.visible || Math.abs(projection.x)>1 || Math.abs(projection.y)>1 || Math.abs(projection.z)>1) {
      element.hidden = true;
      continue;
    }
    element.hidden = false;
    const width = element.offsetWidth, height = element.offsetHeight;
    const anchorX = bounds.left + (projection.x+1)*bounds.width/2;
    const anchorY = bounds.top + (1-projection.y)*bounds.height/2;
    const clampX = value => Math.max(bounds.left+width/2+4, Math.min(bounds.right-width/2-4,value));
    const preferredX = clampX(anchorX);
    const preferredBottom = Math.max(bounds.top+height+4, anchorY);
    const intersects = (x,bottom) => placed.some(box => x-width/2 < box.right+5 && x+width/2 > box.left-5 && bottom-height < box.bottom+5 && bottom > box.top-5);
    const xs = [preferredX, ...placed.flatMap(box => [clampX(box.left-width/2-7),clampX(box.right+width/2+7)])];
    const bottoms = [preferredBottom, ...placed.map(box => box.top-7).filter(value => value<=preferredBottom && value-height>=bounds.top+4)];
    let x=preferredX, bottom=preferredBottom, best=Infinity;
    for(const candidateX of xs) for(const candidateBottom of bottoms) {
      const cost=Math.abs(candidateX-preferredX)+Math.abs(candidateBottom-preferredBottom)*.8;
      if(cost<best && !intersects(candidateX,candidateBottom)) {x=candidateX;bottom=candidateBottom;best=cost;}
    }
    element.style.left = x+'px';
    element.style.top = bottom+'px';
    element.style.setProperty('--tail-left', Math.max(10, Math.min(width-10, width/2+anchorX-x))+'px');
    placed.push({left:x-width/2, right:x+width/2, top:bottom-height, bottom});
  }
}
