(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const key = 'betterassist:cookie-choice:v1';
  const banner = byId('cookieBanner');
  let choice = null;
  let tracked = false;
  let trafficPending = null;
  let eventId = crypto.randomUUID();
  let feedbackId = crypto.randomUUID();
  let feedbackAttempt = '';
  try { choice = localStorage.getItem(key); } catch (_) { /* Choice lasts for this page. */ }
  banner.hidden = choice === 'accepted' || choice === 'declined';

  async function post(path, data) {
    const response = await fetch(new URL(path, document.baseURI), {
      method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data), signal: AbortSignal.timeout(10000)
    });
    let result;
    try { result = await response.json(); } catch (_) { throw new Error('This feature is not connected yet. Please try again later.'); }
    if (!response.ok) throw new Error(result.error || 'Could not save that. Please try again.');
    return result;
  }

  async function track() {
    if (choice !== 'accepted' || tracked || trafficPending) return;
    trafficPending = post('./api/traffic', {consent: true, eventId});
    try { await trafficPending; tracked = true; } catch (_) { /* Planning works even if analytics is unavailable. */ }
    finally { trafficPending = null; }
  }

  async function setChoice(next) {
    choice = next;
    try { localStorage.setItem(key, choice); } catch (_) { /* Do not block the planner. */ }
    banner.hidden = true;
    byId('cookieSettings').focus({preventScroll: true});
    if (choice === 'accepted') {
      track();
    } else {
      // Finish any in-flight opt-in request before removing its server-set cookie.
      try { await trafficPending; } catch (_) { /* Still revoke after a failed request. */ }
      try { await post('./api/privacy', {}); } catch (_) { /* No more tracking requests will be sent. */ }
    }
  }

  byId('acceptCookies').addEventListener('click', () => setChoice('accepted'));
  byId('declineCookies').addEventListener('click', () => setChoice('declined'));
  byId('cookieSettings').addEventListener('click', () => {
    banner.hidden = false;
    byId('declineCookies').focus();
  });
  window.addEventListener('storage', event => {
    if (event.key === key) {
      choice = event.newValue;
      banner.hidden = choice === 'accepted' || choice === 'declined';
      if (choice === 'accepted') track();
    }
  });
  window.addEventListener('online', track);
  track();

  const form = byId('feedbackForm');
  const status = byId('feedbackStatus');
  const message = byId('feedbackMessage');
  message.addEventListener('input', () => { byId('feedbackLength').textContent = `${message.value.length} / 2,000`; });
  form.addEventListener('change', () => {
    const value = form.elements.rating.value;
    byId('ratingHint').textContent = value ? `${value} out of 5 selected` : 'Choose 1 to 5 stars';
    form.querySelectorAll('.star-option').forEach(label => {
      label.classList.toggle('filled', Number(label.querySelector('input').value) <= Number(value));
    });
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const rating = Number(form.elements.rating.value) || null;
    if (!rating && !message.value.trim()) {
      status.textContent = 'Choose a star rating or tell us what could be better.';
      message.focus();
      return;
    }
    const button = byId('feedbackSubmit');
    const content = JSON.stringify({rating, message: message.value.trim()});
    if (feedbackAttempt && feedbackAttempt !== content) feedbackId = crypto.randomUUID();
    feedbackAttempt = content;
    button.disabled = true;
    form.querySelectorAll('input, textarea').forEach(input => { input.disabled = true; });
    status.textContent = 'Sending your feedback…';
    try {
      await post('./api/feedback', {id: feedbackId, rating, message: message.value.trim()});
      status.textContent = 'Thanks! Your feedback helps Harkeerat make Better Assist better.';
      form.reset();
      form.dispatchEvent(new Event('change'));
      byId('feedbackLength').textContent = '0 / 2,000';
      feedbackId = crypto.randomUUID();
      feedbackAttempt = '';
    } catch (error) {
      status.textContent = error.name === 'TimeoutError' ? 'That took too long. Your feedback is still here—please try again.' : error.message;
    } finally {
      button.disabled = false;
      form.querySelectorAll('input, textarea').forEach(input => { input.disabled = false; });
    }
  });
})();
