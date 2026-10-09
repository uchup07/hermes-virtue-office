const logout = document.getElementById('logout');
logout?.addEventListener('click', async () => {
  logout.disabled = true;
  try {
    const response = await fetch('/logout', {method: 'POST', headers: {'X-Virtue-Logout': '1'}});
    if (!response.ok) throw new Error('logout failed');
    location.replace('/login');
  } catch {
    logout.disabled = false;
    logout.textContent = 'Coba keluar lagi';
  }
});
// Restore from browser history only after checking that this session is still valid.
window.addEventListener('pageshow', async event => {
  if (!event.persisted) return;
  try {
    const response = await fetch('/state', {cache: 'no-store'});
    if (response.status === 401) location.replace('/login');
  } catch {}
});
