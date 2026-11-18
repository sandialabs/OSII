'use strict';
const api = window.osiiDesktop;
const byId = id => document.getElementById(id);
let existing = false;
let ready = false;
let busy = false;

function feedback(error) {
  byId('error').hidden = !error;
  byId('error').textContent = error ? String(error.message ?? error).replace(/^Error invoking remote method '[^']+': (Error: )?/, '') : '';
}
function setBusy(value) {
  busy = value;
  byId('fields').disabled = !ready || busy;
  for (const button of document.querySelectorAll('.saved-library,.choice')) button.disabled = busy;
  byId('status').textContent = value ? 'Starting your library…' : ready ? 'Ready. Choose a library to begin.' : 'Starting OSII…';
}
async function open(identifier) {
  feedback(); setBusy(true);
  try { await api.openProfile(identifier); }
  catch (error) { feedback(error); setBusy(false); }
}
async function refresh() {
  const profiles = await api.profiles();
  byId('saved').replaceChildren();
  byId('saved-section').hidden = !profiles.length;
  for (const profile of profiles) {
    const button = document.createElement('button');
    button.className = 'saved-library';
    const title = document.createElement('strong'); title.textContent = profile.name;
    const source = document.createElement('span'); source.textContent = profile.source;
    button.append(title, source);
    button.addEventListener('click', () => open(profile.id));
    byId('saved').append(button);
  }
}
function mode(value) {
  existing = value;
  byId('existing-fields').hidden = !value;
  byId('library').required = value;
  for (const [id, selected] of [['existing-mode', value], ['new-mode', !value]]) {
    byId(id).classList.toggle('selected', selected);
    byId(id).setAttribute('aria-pressed', String(selected));
  }
  byId('submit').textContent = value ? 'Open library' : 'Create and open library';
  feedback();
}
byId('new-mode').addEventListener('click', () => mode(false));
byId('existing-mode').addEventListener('click', () => mode(true));
for (const button of document.querySelectorAll('[data-choose]')) {
  button.addEventListener('click', async () => {
    try { const selected = await api.chooseFolder(); if (selected) byId(button.dataset.choose).value = selected; }
    catch (error) { feedback(error); }
  });
}
byId('profile-form').addEventListener('submit', async event => {
  event.preventDefault();
  feedback(); setBusy(true);
  try {
    const profile = await api.createProfile({ name: byId('name').value, source: byId('source').value,
      library: existing ? byId('library').value : '', config: existing ? byId('config').value : '', existing });
    await refresh();
    await open(profile.id);
  } catch (error) { feedback(error); setBusy(false); }
});
byId('help').addEventListener('click', () => byId('help-dialog').showModal());
byId('close-help').addEventListener('click', () => byId('help-dialog').close());
byId('diagnostics').addEventListener('click', () => api.diagnostics().catch(feedback));
api.onStatus(async value => {
  if (value.error) { feedback(value.error); setBusy(false); }
  if (value.starting) setBusy(true);
  if (value.ready) {
    ready = true; setBusy(false);
    try { await refresh(); } catch (error) { feedback(error); }
  }
});
// Handles both a fast runtime and returning from an already-open library.
api.profiles().then(async () => {
  ready = true; setBusy(false); await refresh();
}).catch(error => {
  if (!String(error.message).includes('No handler registered')) feedback(error);
});
api.information().then(value => { byId('version').textContent = 'v' + value.version; }).catch(() => {});
