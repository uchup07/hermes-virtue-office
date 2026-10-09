// Pure state mapping shared by the UI and tests. No network or rendering side effects.
export const MAX_VISIBLE=12;
export function visualState(agent){
 if(['gone','done'].includes(agent.status))return 'leaving';
 if(agent.approval||agent.status==='waiting')return 'waiting';
 if(agent.status==='working')return ['typing','reading','browsing','terminal','delegating'].includes(agent.activity)?agent.activity:'working';
 return agent.status==='thinking'?'thinking':'idle';
}
export function describe(agent){
 return {leaving:'Sesi selesai',waiting:'Perlu persetujuan',typing:'Menulis kode',reading:'Membaca',browsing:'Menjelajah web',terminal:'Menjalankan terminal',delegating:'Mendelegasikan',working:'Bekerja',thinking:'Berpikir',idle:'Siap / menunggu'}[visualState(agent)];
}
export function chooseAvatar(id){let h=0;for(const ch of id)h=(Math.imul(h,31)+ch.codePointAt(0))>>>0;return h%5;}
export function validSnapshot(data){return data?.service==='hermes-virtue-office'&&Array.isArray(data.agents)&&data.agents.every(a=>a&&typeof a.id==='string'&&typeof a.status==='string');}
