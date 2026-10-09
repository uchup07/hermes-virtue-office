import {visualState} from './live-state.js';
const messages = {
  waiting: 'Saya menunggu persetujuan.',
  leaving: 'Sesi saya sudah selesai.',
  typing: 'Saya sedang menulis kode.',
  reading: 'Saya sedang membaca file.',
  browsing: 'Saya sedang mencari informasi.',
  terminal: 'Saya menjalankan terminal.',
  delegating: 'Saya membagi tugas ke subagent.',
  working: 'Saya sedang mengerjakan tugas.',
  thinking: 'Saya sedang berpikir.',
  idle: 'Saya siap menerima tugas.'
};
export function liveActivity(agent, motion, moving) {
  const state = visualState(agent);
  // Approval and completed sessions remain visible even while a character moves.
  if (state === 'waiting' || state === 'leaving') return messages[state];
  if (motion === 'to-lounge') return 'Saya menuju ruang santai.';
  if (motion === 'lounging' && state === 'idle') return 'Saya beristirahat, siap untuk tugas baru.';
  if (moving && motion === 'arriving') return 'Saya menuju meja kerja.';
  return messages[state];
}
export function playgroundActivity(character) {
  if (character.state === 'walking' && character.pending?.kind === 'door') return 'Saya menuju pintu.';
  return {
    idle: 'Saya siap menerima tugas.', walking: 'Saya sedang berjalan.',
    sitting: 'Saya sedang duduk.', working: 'Saya mengerjakan tugas.',
    booting: 'Saya menyalakan komputer.'
  }[character.state] || 'Saya siap menerima tugas.';
}
