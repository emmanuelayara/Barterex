(function () {
    'use strict';

    var root = document.querySelector('.au');
    if (!root) return;

    // Show / hide password buttons.
    root.querySelectorAll('.au-eye').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var input = btn.parentElement.querySelector('input');
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.setAttribute('aria-pressed', show ? 'true' : 'false');
            btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            btn.firstElementChild.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
        });
    });

    /* ---------- Password strength, requirements and match ---------- */
    var pw = root.querySelector('[data-pw]');
    var pw2 = root.querySelector('[data-pw-confirm]');
    var meter = root.querySelector('.au-meter');
    var meterText = root.querySelector('.au-meter-text');
    var reqs = root.querySelectorAll('.au-req');
    var matchHint = root.querySelector('[data-match-hint]');
    var labels = ['', 'Weak password', 'Fair - keep going', 'Good password', 'Strong password'];

    var rules = {
        length: function (v) { return v.length >= 8; },
        upper: function (v) { return /[A-Z]/.test(v); },
        lower: function (v) { return /[a-z]/.test(v); },
        number: function (v) { return /[0-9]/.test(v); },
        special: function (v) { return /[^A-Za-z0-9]/.test(v); }
    };

    function evaluate() {
        var v = pw.value;
        var met = 0;
        reqs.forEach(function (li) {
            var ok = !!v && rules[li.dataset.rule](v);
            li.classList.toggle('is-met', ok);
            li.querySelector('i').className = ok ? 'fas fa-circle-check' : 'far fa-circle';
            if (ok) met++;
        });
        if (meter) {
            var level = !v ? 0 : met <= 2 ? 1 : met === 3 ? 2 : met === 4 ? 3 : 4;
            meter.dataset.level = String(level);
            if (meterText) meterText.textContent = labels[level] || '';
        }
        checkMatch();
    }

    function checkMatch() {
        if (!pw2 || !matchHint) return true;
        if (!pw2.value) { matchHint.textContent = 'Must match your password exactly'; matchHint.style.color = ''; pw2.classList.remove('is-invalid', 'is-valid'); return true; }
        var ok = pw.value === pw2.value;
        matchHint.textContent = ok ? 'Passwords match' : 'Passwords do not match';
        matchHint.style.color = ok ? 'var(--bx-success)' : 'var(--bx-danger)';
        pw2.classList.toggle('is-invalid', !ok);
        pw2.classList.toggle('is-valid', ok);
        return ok;
    }

    if (pw) {
        pw.addEventListener('input', evaluate);
        if (pw2) pw2.addEventListener('input', checkMatch);
        evaluate();
    }

    /* ---------- Submit: validate, then show progress ---------- */
    var form = root.querySelector('form[data-auth-form]');
    if (form) {
        form.addEventListener('submit', function (e) {
            var firstBad = null;

            form.querySelectorAll('input[required]').forEach(function (input) {
                if (input.type === 'checkbox') return;
                var bad = !input.value.trim();
                input.classList.toggle('is-invalid', bad);
                var out = input.closest('.au-field') && input.closest('.au-field').querySelector('.au-error[data-client]');
                if (out) out.textContent = bad ? 'This field is required.' : '';
                if (bad && !firstBad) firstBad = input;
            });

            var terms = form.querySelector('#terms');
            if (terms && !terms.checked) {
                if (typeof warningToast === 'function') warningToast('Please accept the Terms and Privacy Policy to continue.');
                if (!firstBad) firstBad = terms;
            }

            if (pw2 && !checkMatch() && !firstBad) firstBad = pw2;

            if (firstBad) {
                e.preventDefault();
                if (typeof hideLoading === 'function') hideLoading();
                firstBad.focus();
                return;
            }

            var btn = form.querySelector('[type="submit"]');
            if (btn) {
                var label = form.dataset.busy || 'Please wait...';
                btn.disabled = true;
                if (btn.tagName === 'INPUT') btn.value = label; else btn.textContent = label;
            }
            if (typeof window.showLoading === 'function') window.showLoading(form.dataset.busy || 'Please wait...');
        });

        // Clear a field's error as soon as the user edits it.
        form.querySelectorAll('.au-input').forEach(function (input) {
            input.addEventListener('input', function () {
                input.classList.remove('is-invalid');
                var out = input.closest('.au-field') && input.closest('.au-field').querySelector('.au-error[data-client]');
                if (out) out.textContent = '';
            });
        });
    }

    // If the server sent errors back, make sure the global loader isn't left covering the page.
    if (root.querySelector('.au-error:not([data-client])') && typeof window.hideLoading === 'function') window.hideLoading();
})();
