export const BUBBLE_DURATION_MS = 2000;
// Only a new activity/event refreshes the deadline. Repeated rendering/polling
// and selection changes do not count as new commands.
export function refreshBubble(timer, key, now) {
  if (timer.activityKey !== key) {
    timer.activityKey = key;
    timer.visibleUntil = now + BUBBLE_DURATION_MS;
  }
  return now < timer.visibleUntil;
}
export function liveBubbleKey(agent) {
  return JSON.stringify([agent.updated_at, agent.tools_completed]);
}
