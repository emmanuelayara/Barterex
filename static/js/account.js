/* Account pages: the tiny bit of behaviour the Bootstrap-style markup expects
   (collapsible FAQ items and the settings section menu). */
(function () {
    'use strict';

    document.querySelectorAll('.ac [data-toggle="collapse"]').forEach(function (btn) {
        var target = document.querySelector(btn.getAttribute('data-target'));
        if (!target) return;
        btn.setAttribute('aria-expanded', 'false');
        btn.addEventListener('click', function () {
            var open = !target.classList.contains('show');
            var parent = target.getAttribute('data-parent') && document.querySelector(target.getAttribute('data-parent'));
            if (parent) {
                parent.querySelectorAll('.collapse.show').forEach(function (el) { el.classList.remove('show'); });
                parent.querySelectorAll('[data-toggle="collapse"]').forEach(function (b) { b.setAttribute('aria-expanded', 'false'); });
            }
            target.classList.toggle('show', open);
            btn.setAttribute('aria-expanded', String(open));
        });
    });

    var links = Array.prototype.slice.call(document.querySelectorAll('.ac a[data-toggle="list"]'));
    if (!links.length) return;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function activate(link) {
        links.forEach(function (l) { l.classList.toggle('active', l === link); });
        if (link.scrollIntoView && link.parentElement.scrollWidth > link.parentElement.clientWidth) {
            link.parentElement.scrollTo({ left: link.offsetLeft - 24, behavior: reduce ? 'auto' : 'smooth' });
        }
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (e) {
            var section = document.querySelector(link.getAttribute('href'));
            if (!section) return;
            e.preventDefault();
            section.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
            activate(link);
        });
    });

    // keep the active chip in sync while scrolling
    var sections = links.map(function (l) { return document.querySelector(l.getAttribute('href')); });
    if ('IntersectionObserver' in window) {
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) activate(links[sections.indexOf(en.target)]);
            });
        }, { rootMargin: '-120px 0px -60% 0px' });
        sections.forEach(function (s) { if (s) io.observe(s); });
    }
})();
