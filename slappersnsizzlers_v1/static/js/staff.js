// Slappers n Sizzlers - back-office JS
document.addEventListener('DOMContentLoaded', function () {

  var FETCH_HEADERS = { 'X-Requested-With': 'fetch' };
  var TOAST_MS = 2400;

  // Toast
  var toastRoot = document.getElementById('toast-root');

  function dismiss(el) {
    el.classList.add('is-leaving');
    setTimeout(function () { el.remove(); }, 200);
  }

  function toast(message, isError) {
    if (!toastRoot) return;
    var el = document.createElement('div');
    el.className = 'adm-toast' + (isError ? ' adm-toast--error' : '');
    el.setAttribute('role', 'status');
    var icon = document.createElement('i');
    icon.className = isError ? 'ri-error-warning-line' : 'ri-check-line';
    icon.setAttribute('aria-hidden', 'true');
    el.appendChild(icon);
    el.appendChild(document.createTextNode(message));
    toastRoot.appendChild(el);
    setTimeout(function () { dismiss(el); }, TOAST_MS);
  }

  // Server-rendered flash messages (the no-JS path, and every full-page POST) get the same auto-dismiss
  if (toastRoot) {
    toastRoot.querySelectorAll('.adm-toast').forEach(function (el) {
      setTimeout(function () { dismiss(el); }, TOAST_MS);
    });
  }

  // Apply { selector: html } updates from the server
  function applyUpdates(updates) {
    Object.keys(updates || {}).forEach(function (selector) {
      var html = updates[selector];
      document.querySelectorAll(selector).forEach(function (el) {
        if (html === '') {
          if (el.id === 'drawer-root') { closeDrawer(); } else { el.remove(); }
          return;
        }
        // <tr>/<tbody> can't be parsed inside a <div>, so pick a parser context that matches the target
        var tag = el.tagName === 'TR' ? 'tbody' : el.tagName === 'TBODY' ? 'table' : 'div';
        var host = document.createElement(tag);
        host.innerHTML = html;
        var fresh = host.firstElementChild;
        if (fresh) el.replaceWith(fresh);
      });
    });
  }

  // fetch() a form
  function submitForm(form) {
    if (form.dataset.busy) return;
    form.dataset.busy = '1';
    var body = new FormData(form);
    return fetch(form.action, { method: 'POST', body: body, headers: FETCH_HEADERS, credentials: 'same-origin' })
      .then(function (response) {
        return response.json().then(function (data) { return { status: response.status, data: data }; });
      })
      .then(function (result) {
        var data = result.data;
        if (data.html !== undefined && !data.ok) {
          openDrawerHtml(data.html);
        }
        applyUpdates(data.updates);
        if (data.message) toast(data.message, !data.ok);
        if (data.ok && form.hasAttribute('data-reset-on-success') && document.body.contains(form)) form.reset();
      })
      .catch(function () {
        toast("Couldn't reach the server — try again.", true);
      })
      .finally(function () {
        delete form.dataset.busy;
      });
  }

  // Delegated so forms swapped in by applyUpdates() work without re-binding
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-ajax')) return;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) { event.preventDefault(); return; }
    event.preventDefault();
    submitForm(form);
  });

  // Autosave: a price box or a name field posts the moment it changes (blur or Enter)
  document.addEventListener('change', function (event) {
    var form = event.target.closest && event.target.closest('form[data-autosave]');
    if (form) submitForm(form);
  });

  // Drawer
  var drawerRoot = document.getElementById('drawer-root');
  var drawerTrigger = null;

  function openDrawerHtml(html) {
    drawerRoot.innerHTML = html;
    var dialog = drawerRoot.querySelector('[role="dialog"]');
    if (dialog) {
      var first = dialog.querySelector('input:not([type=hidden]), select, textarea, button');
      if (first) first.focus();
    }
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    if (!drawerRoot) return;
    drawerRoot.innerHTML = '';
    document.body.style.overflow = '';
    if (drawerTrigger && document.body.contains(drawerTrigger)) drawerTrigger.focus();
    drawerTrigger = null;
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[data-drawer]');
    if (link && drawerRoot) {
      event.preventDefault();
      drawerTrigger = link;
      fetch(link.href, { headers: FETCH_HEADERS, credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) { openDrawerHtml(data.html); })
        .catch(function () { window.location.href = link.href; });
      return;
    }
    if (event.target.closest && event.target.closest('[data-drawer-close]')) {
      event.preventDefault();
      closeDrawer();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && drawerRoot && drawerRoot.firstElementChild) closeDrawer();
  });

  if (drawerRoot && drawerRoot.firstElementChild) document.body.style.overflow = 'hidden';
  // Pill toggles in the item drawer: the checkbox is real; the visible word follows it
  document.addEventListener('change', function (event) {
    var input = event.target;
    var label = input.closest && input.closest('.adm-pill-toggle');
    if (!label || input.type !== 'checkbox') return;
    var word = label.querySelector('[data-on]');
    if (word) word.textContent = input.checked ? word.dataset.on : word.dataset.off;
  });

  // Queue polling
  var POLL_MS = 10000;
  var pointerDown = false;
  document.addEventListener('pointerdown', function () { pointerDown = true; });
  document.addEventListener('pointerup', function () { pointerDown = false; });
  document.addEventListener('pointercancel', function () { pointerDown = false; });

  function pollBoard() {
    var board = document.getElementById('queue-board');
    if (!board || !board.dataset.poll) return;
    var settled = !pointerDown && !board.contains(document.activeElement) && !board.querySelector('form[data-busy]');
    if (!settled || document.hidden) { setTimeout(pollBoard, 1500); return; }
    fetch(board.dataset.poll, { headers: FETCH_HEADERS, credentials: 'same-origin' })
      .then(function (r) { return r.text(); })
      .then(function (html) { applyUpdates({ '#queue-board': html }); })
      .catch(function () { })
      .finally(function () { setTimeout(pollBoard, POLL_MS); });
  }
  if (document.getElementById('queue-board')) setTimeout(pollBoard, POLL_MS);
});
