(function () {
    'use strict';

    var root = document.querySelector('.st');
    if (!root) return;

    var drawer = root.querySelector('#stSidebar');
    var overlay = root.querySelector('#sidebarOverlay');
    var menuBtn = root.querySelector('#hamburgerBtn');
    var closeBtn = root.querySelector('#closeSidebarBtn');
    var desktop = window.matchMedia('(min-width: 960px)');

    // Keep sticky/fixed pieces clear of the app's top navbar and bottom bar.
    function syncBars() {
        var nav = document.getElementById('navbar');
        var bottom = document.querySelector('.bx-tabbar');
        if (nav) root.style.setProperty('--st-nav-h', nav.offsetHeight + 'px');
        if (bottom) root.style.setProperty('--st-bottom-h', (bottom.offsetHeight + 16) + 'px');
    }
    syncBars();
    window.addEventListener('resize', syncBars);

    /* ---------- Drawer (mobile) ---------- */
    function openDrawer() {
        if (desktop.matches) return;
        drawer.classList.add('show');
        overlay.classList.add('show');
        document.body.classList.add('st-lock');
        menuBtn.setAttribute('aria-expanded', 'true');
        closeBtn.focus();
    }
    function closeDrawer(returnFocus) {
        drawer.classList.remove('show');
        overlay.classList.remove('show');
        document.body.classList.remove('st-lock');
        menuBtn.setAttribute('aria-expanded', 'false');
        if (returnFocus) menuBtn.focus();
    }
    menuBtn.addEventListener('click', openDrawer);
    closeBtn.addEventListener('click', function () { closeDrawer(true); });
    overlay.addEventListener('click', function () { closeDrawer(true); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && drawer.classList.contains('show')) closeDrawer(true);
    });
    var onBreakpoint = function () { if (desktop.matches) closeDrawer(false); };
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpoint);
    else desktop.addListener(onBreakpoint);

    /* ---------- Tabs ---------- */
    var panels = root.querySelectorAll('.st-panel');
    var triggers = root.querySelectorAll('[data-tab]');
    var STORE = 'st-active-tab';

    function activate(name) {
        var found = false;
        panels.forEach(function (p) {
            var on = p.dataset.panel === name;
            p.classList.toggle('is-active', on);
            if (on) found = true;
        });
        if (!found) return false;
        triggers.forEach(function (t) {
            var on = t.dataset.tab === name;
            t.classList.toggle('is-active', on);
            if (on) t.setAttribute('aria-current', 'true');
            else t.removeAttribute('aria-current');
        });
        var chip = root.querySelector('.st-chip.is-active');
        var strip = chip && chip.parentElement;
        if (strip && strip.scrollWidth > strip.clientWidth) {
            strip.scrollTo({ left: chip.offsetLeft - (strip.clientWidth - chip.offsetWidth) / 2, behavior: 'smooth' });
        }
        return true;
    }

    root.addEventListener('click', function (e) {
        var t = e.target.closest('[data-tab]');
        if (!t) return;
        e.preventDefault();
        activate(t.dataset.tab);
        history.replaceState(null, '', '#' + t.dataset.tab);
        closeDrawer(false);
        if (!desktop.matches) {
            var top = root.querySelector('.st-content').getBoundingClientRect().top + window.scrollY - 130;
            window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        }
    });

    // After a form post the server redirects back here: reopen the tab the user was on.
    var remembered = null;
    try { remembered = sessionStorage.getItem(STORE); sessionStorage.removeItem(STORE); } catch (err) { /* storage unavailable */ }
    var wanted = (location.hash || '').slice(1) || remembered || 'profile';
    if (!activate(wanted)) activate('profile');
    window.addEventListener('hashchange', function () { activate((location.hash || '').slice(1)); });

    root.querySelectorAll('form[data-remember]').forEach(function (form) {
        form.addEventListener('submit', function () {
            try { sessionStorage.setItem(STORE, form.dataset.remember); } catch (err) { /* ignore */ }
        });
    });

    /* ---------- Profile: view <-> edit ---------- */
    var profileCard = root.querySelector('#profileCard');
    var editForm = root.querySelector('#profileEditForm');
    if (profileCard && editForm) {
        var setEditing = function (on) {
            profileCard.classList.toggle('is-editing', on);
            if (on) {
                var first = editForm.querySelector('.st-input');
                if (first) first.focus({ preventScroll: false });
            } else {
                editForm.reset();
            }
        };
        root.querySelector('#editProfileBtn').addEventListener('click', function () { setEditing(true); });
        root.querySelector('#cancelProfileEditBtn').addEventListener('click', function () { setEditing(false); });
        // Arriving from the dashboard progress card: open the form straight away.
        if (new URLSearchParams(location.search).get('edit') === 'profile') setEditing(true);
    }

    /* ---------- Profile photo: validate, then upload straight away ---------- */
    var avatarInput = root.querySelector('#avatarFileInput');
    var avatarMsg = root.querySelector('#avatarMsg');
    if (avatarInput) {
        var showAvatarError = function (text) {
            avatarMsg.textContent = text;
            avatarMsg.classList.add('show');
            avatarInput.value = '';
        };
        avatarInput.addEventListener('change', function () {
            var file = avatarInput.files[0];
            avatarMsg.classList.remove('show');
            if (!file) return;
            if (!file.type || file.type.indexOf('image/') !== 0) {
                showAvatarError('Please choose an image file (PNG, JPG, GIF or WEBP).');
                return;
            }
            if (file.size > 10 * 1024 * 1024) {
                showAvatarError('That image is too large. Please choose one under 10MB.');
                return;
            }
            if (typeof window.showLoading === 'function') window.showLoading('Uploading your photo...');
            root.querySelector('#avatarUploadForm').submit();
        });
    }

    /* ---------- Password: show/hide, strength, match ---------- */
    root.querySelectorAll('.st-eye').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var input = btn.parentElement.querySelector('input');
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.setAttribute('aria-pressed', show ? 'true' : 'false');
            btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            btn.firstElementChild.className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
        });
    });

    var pw = root.querySelector('#new_password');
    var pw2 = root.querySelector('#confirm_password');
    var meter = root.querySelector('#pwMeter');
    var meterText = root.querySelector('#pwMeterText');
    var matchText = root.querySelector('#pwMatchText');
    var labels = ['', 'Weak - add more characters', 'Fair - mix in upper case and numbers', 'Good', 'Strong'];

    function scorePassword(v) {
        if (!v) return 0;
        var s = 0;
        if (v.length >= 8) s++;
        if (/[a-z]/.test(v) && /[A-Z]/.test(v)) s++;
        if (/\d/.test(v)) s++;
        if (/[^A-Za-z0-9]/.test(v)) s++;
        if (v.length < 8) s = Math.min(s, 1);
        return Math.max(s, 1);
    }
    function checkMatch() {
        if (!pw2 || !matchText) return true;
        if (!pw2.value) { matchText.textContent = ''; return true; }
        var ok = pw.value === pw2.value;
        matchText.textContent = ok ? 'Passwords match' : 'Passwords do not match';
        matchText.style.color = ok ? 'var(--st-success)' : 'var(--st-danger)';
        return ok;
    }
    if (pw && meter) {
        pw.addEventListener('input', function () {
            var level = scorePassword(pw.value);
            meter.dataset.level = String(level);
            meterText.textContent = labels[level] || '';
            checkMatch();
        });
        pw2.addEventListener('input', checkMatch);
        root.querySelector('#passwordForm').addEventListener('submit', function (e) {
            if (!checkMatch()) { e.preventDefault(); if (typeof hideLoading === 'function') hideLoading(); pw2.focus(); }
        });
    }

    /* ---------- Verification: show the chosen file ---------- */
    var idInput = root.querySelector('#government_id');
    if (idInput) {
        idInput.addEventListener('change', function () {
            var drop = root.querySelector('#governmentIdLabel');
            var icon = root.querySelector('#governmentIdIcon');
            var text = root.querySelector('#governmentIdLabelText');
            var file = idInput.files && idInput.files[0];
            drop.classList.toggle('is-attached', !!file);
            icon.className = file ? 'fas fa-circle-check' : 'fas fa-id-card';
            text.textContent = file ? file.name : 'Tap to upload your government ID';
        });
    }

    /* ---------- Delete account: only enable once confirmed ---------- */
    var delForm = root.querySelector('#deleteForm');
    if (delForm) {
        var box = delForm.querySelector('#confirm_delete');
        var typed = delForm.querySelector('#confirm_username');
        var btn = delForm.querySelector('#deleteBtn');
        var expected = delForm.dataset.username;
        var refresh = function () { btn.disabled = !(box.checked && typed.value.trim() === expected); };
        box.addEventListener('change', refresh);
        typed.addEventListener('input', refresh);
        refresh();
        delForm.addEventListener('submit', function (e) {
            if (!window.confirm('Are you absolutely sure? This cannot be undone!')) {
                e.preventDefault();
                if (typeof hideLoading === 'function') hideLoading();
            }
        });
    }

    /* ---------- Dark mode ---------- */
    var theme = root.querySelector('#darkModeToggle');
    if (theme) {
        var paint = function () {
            var dark = document.documentElement.classList.contains('dark-mode');
            theme.setAttribute('aria-pressed', dark ? 'true' : 'false');
            theme.querySelector('i').className = dark ? 'fas fa-sun' : 'fas fa-moon';
            theme.querySelector('.st-label').textContent = dark ? 'Light mode' : 'Dark mode';
        };
        paint();
        theme.addEventListener('click', function (e) {
            e.preventDefault();
            if (window.darkModeManager) {
                window.darkModeManager.toggle();
                paint();
            }
        });
    }
})();
