// Slappers n Sizzlers - storefront JS
document.addEventListener('DOMContentLoaded', function () {

  // Mobile menu toggle
  var menuToggle = document.querySelector('.menu-toggle');
  var mobileDrawer = document.getElementById('mobile-drawer');
  var iconMenu = document.querySelector('.icon-menu');
  var iconClose = document.querySelector('.icon-close');

  if (menuToggle && mobileDrawer) {
    menuToggle.addEventListener('click', function () {
      var isOpen = mobileDrawer.classList.toggle('open');
      menuToggle.setAttribute('aria-expanded', isOpen);
      mobileDrawer.setAttribute('aria-hidden', !isOpen);
      if (iconMenu && iconClose) {
        iconMenu.style.display  = isOpen ? 'none'  : 'block';
        iconClose.style.display = isOpen ? 'block' : 'none';
      }
    });
  }

  // Auto-dismiss flash messages after 4s
  document.querySelectorAll('.alert').forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.4s';
      alert.style.opacity = '0';
      setTimeout(function () { alert.remove(); }, 400);
    }, 4000);
  });

  // Customise modal
  document.querySelectorAll('[data-modal]').forEach(function (trigger) {
    trigger.addEventListener('click', function () {
      var dialog = document.getElementById(trigger.dataset.modal);
      if (!dialog || typeof dialog.showModal !== 'function') return;
      dialog.showModal();
      var first = dialog.querySelector('input:checked, input');
      if (first) first.focus();
    });
  });
  document.querySelectorAll('.customise-modal').forEach(function (dialog) {
    dialog.querySelectorAll('[data-modal-close]').forEach(function (btn) {
      btn.addEventListener('click', function () { dialog.close(); });
    });
    dialog.addEventListener('click', function (e) {
      if (e.target === dialog) dialog.close();
    });
  });

  // Quantity stepper + live line total (dish page, modal)
  function money(n) { return 'R' + n.toFixed(2); }
  function clamp(v) { if (isNaN(v)) return 1; return Math.min(10, Math.max(1, v)); }

  document.querySelectorAll('[data-live-total]').forEach(function (form) {
    var unit = parseFloat(form.dataset.unitPrice) || 0;
    var qtyInput = form.querySelector('[data-qty]');
    var hiddenQty = form.querySelector('input[name="quantity"][type="hidden"]');
    var totalEl = form.querySelector('[data-total]');

    function qty() {
      if (qtyInput) return clamp(parseInt(qtyInput.value, 10));
      if (hiddenQty) return clamp(parseInt(hiddenQty.value, 10));
      return 1;
    }
    function render() {
      var deltas = 0;
      form.querySelectorAll('input[data-delta]:checked').forEach(function (input) {
        deltas += parseFloat(input.dataset.delta) || 0;
      });
      if (qtyInput) qtyInput.value = qty();
      if (totalEl) totalEl.textContent = money((unit + deltas) * qty());
    }

    form.querySelectorAll('[data-qty-step]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!qtyInput) return;
        qtyInput.value = clamp(parseInt(qtyInput.value, 10) + parseInt(btn.dataset.qtyStep, 10));
        render();
      });
    });
    if (qtyInput) {
      qtyInput.addEventListener('input', render);
      qtyInput.addEventListener('change', render);
    }
    form.addEventListener('change', render);
    render();
  });

  // Checkout: the pay total follows the tip tick
  var payBtn = document.querySelector('[data-goods-total]');
  var tipBox = document.querySelector('input[data-tip]');
  if (payBtn && tipBox) {
    var goods = parseFloat(payBtn.dataset.goodsTotal) || 0;
    var payEl = payBtn.querySelector('[data-pay-total]');
    var renderPay = function () {
      var tip = tipBox.checked ? (parseFloat(tipBox.dataset.tip) || 0) : 0;
      if (payEl) payEl.textContent = money(goods + tip);
    };
    tipBox.addEventListener('change', renderPay);
    renderPay();
  }

  // Live order status: poll, reload on change
  var statusPage = document.querySelector('[data-status-page]');
  if (statusPage && window.fetch) {
    var current = statusPage.dataset.status;
    var terminal = { collected: true, cancelled: true };
    if (!terminal[current]) {
      var timer = setInterval(function () {
        fetch(statusPage.dataset.statusUrl, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            if (data && data.status && data.status !== current) {
              clearInterval(timer);
              window.location.reload();
            }
          })
          .catch(function () { });
      }, 8000);
    }
  }

});
