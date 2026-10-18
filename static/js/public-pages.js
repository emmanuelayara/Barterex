(function () {
    'use strict';

    var root = document.querySelector('.pp');
    if (!root) return;
    root.classList.add('pp-js');

    // Keep sticky elements below the fixed navbar, whatever its height is.
    function syncNavHeight() {
        var nav = document.getElementById('navbar');
        if (nav) root.style.setProperty('--pp-nav-h', nav.offsetHeight + 'px');
    }
    syncNavHeight();
    window.addEventListener('resize', syncNavHeight);

    // Fade-in on scroll.
    var reveals = root.querySelectorAll('.pp-reveal');
    if ('IntersectionObserver' in window) {
        var revealObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.08 });
        reveals.forEach(function (el) { revealObserver.observe(el); });
    } else {
        reveals.forEach(function (el) { el.classList.add('is-visible'); });
    }

    // Table of contents: highlight the section being read and keep the chip in view.
    var toc = root.querySelector('.pp-toc');
    if (toc && 'IntersectionObserver' in window) {
        var links = Array.prototype.slice.call(toc.querySelectorAll('a[href^="#"]'));
        var byId = {};
        links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });

        var spy = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                links.forEach(function (a) { a.classList.remove('is-active'); a.removeAttribute('aria-current'); });
                var active = byId[entry.target.id];
                if (!active) return;
                active.classList.add('is-active');
                active.setAttribute('aria-current', 'true');
                var list = active.closest('ul');
                if (list && list.scrollWidth > list.clientWidth) {
                    list.scrollTo({ left: active.offsetLeft - 16, behavior: 'smooth' });
                }
            });
        }, { rootMargin: '-25% 0px -65% 0px' });

        Object.keys(byId).forEach(function (id) {
            var section = document.getElementById(id);
            if (section) spy.observe(section);
        });
    }

    // FAQ search: filter questions and answers as the user types.
    var search = root.querySelector('#faq-search');
    if (search) {
        var items = Array.prototype.slice.call(root.querySelectorAll('.pp-faq-item'));
        var empty = root.querySelector('.pp-empty');
        search.addEventListener('input', function () {
            var q = search.value.trim().toLowerCase();
            var shown = 0;
            items.forEach(function (item) {
                var match = !q || item.textContent.toLowerCase().indexOf(q) !== -1;
                item.hidden = !match;
                if (match) shown++;
                item.open = !!q && match && shown === 1;
            });
            if (empty) empty.classList.toggle('show', shown === 0);
        });
    }

    // Contact form: inline validation, live counter, and double-submit guard.
    var form = root.querySelector('#contact-form');
    if (form) {
        var message = form.querySelector('#message');
        var counter = form.querySelector('#char-count');
        if (message && counter) {
            message.addEventListener('input', function () { counter.textContent = message.value.length; });
        }

        var rules = {
            name: function (v) { return v.length >= 2 ? '' : 'Please enter your name (at least 2 characters).'; },
            email: function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? '' : 'Please enter a valid email address.'; },
            message: function (v) { return v.length >= 10 ? '' : 'Please enter a message (at least 10 characters).'; }
        };

        var check = function (field) {
            var rule = rules[field.name];
            if (!rule) return true;
            var error = rule(field.value.trim());
            var box = field.closest('.pp-field');
            var out = box && box.querySelector('.pp-error');
            field.classList.toggle('is-invalid', !!error);
            field.setAttribute('aria-invalid', error ? 'true' : 'false');
            if (out) out.textContent = error;
            return !error;
        };

        Array.prototype.forEach.call(form.querySelectorAll('.pp-input'), function (field) {
            field.addEventListener('blur', function () { check(field); });
            field.addEventListener('input', function () { if (field.classList.contains('is-invalid')) check(field); });
        });

        form.addEventListener('submit', function (e) {
            var firstInvalid = null;
            Array.prototype.forEach.call(form.querySelectorAll('.pp-input'), function (field) {
                if (!check(field) && !firstInvalid) firstInvalid = field;
            });
            if (firstInvalid) {
                e.preventDefault();
                if (typeof hideLoading === 'function') hideLoading();
                firstInvalid.focus();
                return;
            }
            var btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Sending...';
            }
        });
    }
})();
