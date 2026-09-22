(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let busy = false;
  let generation = 0;
  let latestData = null;
  let showActual = false;
  const demo = Object.freeze({views: 14286, visitors: 14031, today: 24, average: '4.8 / 5'});
  const number = value => Number(value).toLocaleString();
  async function request(path, data) {
    let response;
    try {
      response = await fetch(new URL(path, document.baseURI), {
        method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: data === undefined ? {} : {'Content-Type': 'application/json'},
        body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(10000)
      });
    } catch (error) {
      throw new Error(error.name === 'TimeoutError'
        ? 'The login service took too long to respond. Please try again.'
        : 'Could not reach the login service. Check your connection and try again.');
    }
    let result;
    try { result = await response.json(); } catch (_) {
      throw new Error('The admin service is not connected on this website yet. Your code cannot be checked until the website owner connects it.');
    }
    if (!response.ok) {
      const error = new Error(result.error || 'Could not load the dashboard. Please retry.');
      error.status = response.status;
      throw error;
    }
    return result;
  }
  function signedOut() {
    generation++;
    $('adminDashboard').hidden = true;
    $('adminLogin').hidden = false;
    $('feedbackInbox').replaceChildren();
    latestData = null;
    showActual = false;
    ['totalViews', 'totalVisitors', 'todayViews', 'averageRating'].forEach(id => $(id).textContent = '—');
  }
  function renderMetrics(data) {
    const metrics = showActual ? data : demo;
    $('totalViews').textContent = number(metrics.views);
    $('totalVisitors').textContent = number(metrics.visitors);
    $('todayViews').textContent = number(metrics.today);
    const count = data.ratings.reduce((sum, row) => sum + row.count, 0);
    const total = data.ratings.reduce((sum, row) => sum + row.rating * row.count, 0);
    $('averageRating').textContent = showActual ? (count ? `${(total / count).toFixed(1)} / 5` : '—') : demo.average;
    $('ratingCount').textContent = showActual ? (count ? `${number(count)} rating${count === 1 ? '' : 's'}` : 'No ratings yet') : 'Demo average rating';
    $('metricsLabel').textContent = showActual ? 'Actual traffic' : 'Demo numbers';
    $('metricsNote').textContent = showActual
      ? 'Counts include visitors who accepted analytics. Unique visitors are approximate browsers, not verified people. Dates use UTC.'
      : 'Sample figures for previewing the dashboard. These are not measured visits or submitted ratings.';
    $('metricsToggle').textContent = showActual ? 'View demo numbers' : 'View actual traffic';
    $('metricsToggle').setAttribute('aria-pressed', String(showActual));
    $('viewsNote').textContent = showActual ? 'Tracked page loads, including reloads' : 'Demo page opens';
    $('visitorsNote').textContent = showActual ? 'Browsers with an analytics cookie' : 'Demo visitors';
    $('todayNote').textContent = showActual ? 'Since midnight UTC' : 'Demo daily opens';
  }
  function render(data) {
    latestData = data;
    renderMetrics(data);
    $('inboxCount').textContent = data.feedbackCount ? `${number(data.feedbackCount)} submissions · showing the latest ${data.feedback.length}` : 'No feedback yet. New ratings and ideas will appear here.';
    $('feedbackInbox').replaceChildren();
    data.feedback.forEach(item => {
      const article = document.createElement('article');
      article.className = 'feedback-entry';
      const heading = document.createElement('strong');
      heading.textContent = item.rating ? `${'★'.repeat(item.rating)} · ${item.rating}/5` : 'A suggestion';
      const date = document.createElement('time');
      date.dateTime = item.created;
      date.textContent = new Date(item.created).toLocaleString();
      const message = document.createElement('p');
      message.textContent = item.message || 'Rating only';
      article.append(heading, date, message);
      $('feedbackInbox').append(article);
    });
    $('adminLogin').hidden = true;
    $('adminDashboard').hidden = false;
    $('adminStatus').textContent = `Connected · updated ${new Date().toLocaleTimeString()}. Feedback below contains actual submissions.`;
  }
  async function refresh(initial = false, afterLogin = false) {
    if (busy) return;
    busy = true;
    const currentGeneration = generation;
    if (initial) $('adminLoginButton').disabled = true;
    $('adminRefresh').disabled = true;
    $('adminStatus').textContent = 'Loading…';
    try {
      const data = await request('./api/admin/stats');
      if (currentGeneration === generation) {
        render(data);
        if (afterLogin) {
          $('dashboardHeading').focus();
          $('adminDashboard').scrollIntoView({block: 'start'});
        }
      }
    }
    catch (error) {
      if (currentGeneration !== generation) return;
      if (error.status === 401) {
        signedOut();
        $('adminLoginStatus').textContent = initial ? '' : afterLogin
          ? 'Your login session was not accepted. Allow cookies for this website, then try again.'
          : 'Your session expired. Please log in again.';
      } else {
        // A failed dashboard load after login must report its error on the visible form.
        $($('adminLogin').hidden ? 'adminStatus' : 'adminLoginStatus').textContent = error.message;
      }
    } finally {
      busy = false;
      $('adminRefresh').disabled = false;
      if (initial) $('adminLoginButton').disabled = false;
    }
  }
  $('adminLoginForm').addEventListener('submit', async event => {
    event.preventDefault();
    $('adminLoginButton').disabled = true;
    $('adminLoginStatus').textContent = 'Checking your code…';
    const code = $('adminCode').value.trim();
    $('adminCode').value = '';
    try {
      await request('./api/admin/login', {code});
      $('adminLoginStatus').textContent = '';
      await refresh(false, true);
    } catch (error) { $('adminLoginStatus').textContent = error.message; }
    finally { $('adminLoginButton').disabled = false; }
  });
  $('adminLogout').addEventListener('click', async () => {
    $('adminLogout').disabled = true;
    try {
      await request('./api/admin/logout', {});
      signedOut();
      $('adminLoginStatus').textContent = 'You are signed out.';
      $('adminCode').focus();
    } catch (error) {
      if (error.status === 401) signedOut();
      else $('adminStatus').textContent = 'Could not sign out. Please retry before leaving this device.';
    } finally { $('adminLogout').disabled = false; }
  });
  $('adminRefresh').addEventListener('click', () => refresh());
  $('metricsToggle').addEventListener('click', () => {
    if (!latestData) return;
    showActual = !showActual;
    renderMetrics(latestData);
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !$('adminDashboard').hidden) refresh(); });
  // Recheck server authorization regularly and after browser history restoration.
  setInterval(() => { if (!document.hidden && !$('adminDashboard').hidden) refresh(); }, 60000);
  window.addEventListener('pageshow', event => { if (event.persisted) { signedOut(); refresh(true); } });
  refresh(true);
})();
