(function () {
  'use strict';

  var pageInfo = (function () {
    var el = document.querySelector('[data-filter-page]');
    if (!el) return null;
    return { page: el.dataset.filterPage, at: el.dataset.filterAt || null };
  })();

  if (!pageInfo) return; // not a filterable page

  var meta = null;
  var allGroupKeys = null; // Set populated after meta loads
  var filter = { authors: null, year: 'all' };
  var origData = {};
  var origNBuilds = '';

  // ── URL hash ──────────────────────────────────────────────────────────────

  function parseHash() {
    var f = { authors: null, year: 'all' };
    location.hash.slice(1).split(',').forEach(function (part) {
      var kv = part.split(':');
      if (kv[0] === 'authors' && kv[1]) f.authors = new Set(kv[1].split('-'));
      if (kv[0] === 'year'    && kv[1]) f.year    = kv[1];
    });
    return f;
  }

  function setHash(f) {
    var authorIsAll = !f.authors || f.authors.size === allGroupKeys.size;
    if (authorIsAll && f.year === 'all') {
      history.replaceState(null, '', location.pathname + location.search);
      return;
    }
    var parts = [];
    if (!authorIsAll) parts.push('authors:' + Array.from(f.authors).sort().join('-'));
    if (f.year !== 'all') parts.push('year:' + f.year);
    location.hash = parts.join(',');
  }

  function authorKey(f) {
    if (!f.authors || f.authors.size === allGroupKeys.size) return 'all';
    return Array.from(f.authors).sort().join('-');
  }

  function jsonUrl(f) {
    var base = '/data/' + authorKey(f) + '_' + f.year + '/';
    return pageInfo.page === 'pools' ? base + 'pools.json'
                                     : base + 'at_' + pageInfo.at + '.json';
  }

  // ── DOM snapshot (save before first filter change) ────────────────────────

  function saveOriginals() {
    var nbEl = document.querySelector('[data-n-builds]');
    if (nbEl) origNBuilds = nbEl.innerHTML;

    document.querySelectorAll('details.power[data-power]').forEach(function (pwrEl) {
      var fn      = pwrEl.dataset.power;
      var metaEl  = pwrEl.querySelector('[data-pwr-meta]');
      var statDiv = pwrEl.querySelector('[data-stats]');
      var layUl   = statDiv && statDiv.querySelector('[data-layouts]');
      var enhUl   = statDiv && statDiv.querySelector('[data-enhs]');
      origData[fn] = {
        nTaken:      parseInt(pwrEl.dataset.nTaken) || 0,
        metaHtml:    metaEl  ? metaEl.innerHTML : 'no data',
        metaEmpty:   metaEl  ? metaEl.classList.contains('empty') : true,
        statsHidden: statDiv ? statDiv.style.display === 'none' : true,
        layoutsHtml: layUl   ? layUl.innerHTML : '',
        enhsHtml:    enhUl   ? enhUl.innerHTML : '',
      };
    });
  }

  // ── Apply data to DOM ─────────────────────────────────────────────────────

  function applyData(data) {
    var nbEl = document.querySelector('[data-n-builds]');
    if (nbEl && data.n_builds != null) {
      nbEl.innerHTML = data.n_builds.toLocaleString() +
        ' builds in archive. <a href="' + nbEl.querySelector('a').href + '">Take-rate &amp; statistics →</a>';
    }

    document.querySelectorAll('details.powerset[data-ps]').forEach(function (psEl) {
      var total = 0;

      psEl.querySelectorAll('details.power[data-power]').forEach(function (pwrEl) {
        var fn      = pwrEl.dataset.power;
        var stats   = data.powers[fn];
        var metaEl  = pwrEl.querySelector('[data-pwr-meta]');
        var statDiv = pwrEl.querySelector('[data-stats]');
        var layUl   = statDiv && statDiv.querySelector('[data-layouts]');
        var enhUl   = statDiv && statDiv.querySelector('[data-enhs]');

        if (stats && stats.n_taken > 0) {
          total += stats.n_taken;
          if (metaEl) {
            metaEl.textContent = stats.n_taken + ' times · mean ' +
              stats.mean_slots.toFixed(2) + ' · median ' +
              stats.median_slots.toFixed(0) + ' slots';
            metaEl.classList.remove('empty');
          }
          if (statDiv) statDiv.style.display = '';
          if (layUl)   layUl.innerHTML  = stats.layouts_html;
          if (enhUl)   enhUl.innerHTML  = stats.enhs_html;
        } else {
          if (metaEl) { metaEl.textContent = 'no data'; metaEl.classList.add('empty'); }
          if (statDiv) statDiv.style.display = 'none';
        }
      });

      var totalEl = psEl.querySelector('[data-ps-total]');
      if (totalEl) totalEl.textContent = total > 0 ? total.toLocaleString() + ' slottings' : '';
    });
  }

  function restoreOriginals() {
    var nbEl = document.querySelector('[data-n-builds]');
    if (nbEl) nbEl.innerHTML = origNBuilds;

    document.querySelectorAll('details.power[data-power]').forEach(function (pwrEl) {
      var fn      = pwrEl.dataset.power;
      var orig    = origData[fn];
      if (!orig) return;
      var metaEl  = pwrEl.querySelector('[data-pwr-meta]');
      var statDiv = pwrEl.querySelector('[data-stats]');
      var layUl   = statDiv && statDiv.querySelector('[data-layouts]');
      var enhUl   = statDiv && statDiv.querySelector('[data-enhs]');

      if (metaEl) {
        metaEl.innerHTML = orig.metaHtml;
        orig.metaEmpty ? metaEl.classList.add('empty') : metaEl.classList.remove('empty');
      }
      if (statDiv) statDiv.style.display = orig.statsHidden ? 'none' : '';
      if (layUl)   layUl.innerHTML  = orig.layoutsHtml;
      if (enhUl)   enhUl.innerHTML  = orig.enhsHtml;
    });

    document.querySelectorAll('details.powerset[data-ps]').forEach(function (psEl) {
      var total = 0;
      psEl.querySelectorAll('details.power[data-power]').forEach(function (pwrEl) {
        total += parseInt(pwrEl.dataset.nTaken) || 0;
      });
      var totalEl = psEl.querySelector('[data-ps-total]');
      if (totalEl) totalEl.textContent = total > 0 ? total.toLocaleString() + ' slottings' : '';
    });
  }

  // ── Persistent state (localStorage) ──────────────────────────────────────

  var STORAGE_KEY = 'cohFilter';

  function saveFilter(f) {
    try {
      if (isBaseline(f)) {
        localStorage.removeItem(STORAGE_KEY);
      } else {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          authors: f.authors ? Array.from(f.authors) : null,
          year: f.year,
        }));
      }
    } catch (e) {}
  }

  function loadFilter() {
    try {
      var s = localStorage.getItem(STORAGE_KEY);
      if (!s) return null;
      var d = JSON.parse(s);
      var f = { authors: null, year: d.year || 'all' };
      if (Array.isArray(d.authors)) f.authors = new Set(d.authors);
      return f;
    } catch (e) { return null; }
  }

  // ── Filter application ────────────────────────────────────────────────────

  var savedOrig = false;

  function isBaseline(f) {
    return (!f.authors || f.authors.size === allGroupKeys.size) && f.year === 'all';
  }

  function applyFilter(f, updateHash) {
    if (!f.authors && allGroupKeys) f = { authors: new Set(allGroupKeys), year: f.year };
    if (updateHash) { setHash(f); saveFilter(f); }
    filter = f;
    updateUI();

    if (isBaseline(f)) {
      restoreOriginals();
      return;
    }

    if (!savedOrig) { saveOriginals(); savedOrig = true; }

    fetch(jsonUrl(f))
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(applyData)
      .catch(function (e) { console.warn('Filter JSON load failed:', e); });
  }

  // ── Build filter UI ───────────────────────────────────────────────────────

  function updateUI() {
    if (!allGroupKeys || !meta) return;

    document.querySelectorAll('[data-filter-author]').forEach(function (cb) {
      cb.checked = !filter.authors || filter.authors.has(cb.dataset.filterAuthor);
    });

    // "All" → "All others" when any named author is unchecked
    var othersSpan = document.querySelector('.filter-others-label');
    if (othersSpan && filter.authors) {
      var allNamedOn = meta.authors.every(function (a) {
        return filter.authors.has(a.toLowerCase().replace(/ /g, '_'));
      });
      othersSpan.textContent = allNamedOn ? 'All' : 'All others';
    }

    document.querySelectorAll('[data-filter-year]').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.filterYear === filter.year);
    });
  }

  function buildUI(m) {
    meta = m;
    var bar = document.getElementById('filter-bar');
    if (!bar) return;

    allGroupKeys = new Set(
      ['others'].concat(meta.authors.map(function (a) {
        return a.toLowerCase().replace(/ /g, '_');
      }))
    );
    filter.authors = new Set(allGroupKeys);

    var html = '<div class="filter-section"><span class="filter-label">Builders:</span>';
    html += '<label class="filter-check">'
          + '<input type="checkbox" data-filter-author="others" checked>'
          + ' <span class="filter-others-label">All</span></label>';
    meta.authors.forEach(function (a) {
      var key = a.toLowerCase().replace(/ /g, '_');
      html += '<label class="filter-check">'
            + '<input type="checkbox" data-filter-author="' + key + '" checked>'
            + ' ' + a + '</label>';
    });
    html += '</div>';

    html += '<div class="filter-section"><span class="filter-label">Since:</span>';
    html += '<button class="filter-btn active" data-filter-year="all">All time</button>';
    meta.years.forEach(function (y) {
      html += '<button class="filter-btn" data-filter-year="' + y + '">' + y + '</button>';
    });
    html += '</div>';

    bar.innerHTML = html;

    bar.addEventListener('change', function (e) {
      var cb = e.target;
      if (!cb.dataset || !cb.dataset.filterAuthor) return;
      var f = { authors: new Set(filter.authors), year: filter.year };
      if (cb.checked) {
        f.authors.add(cb.dataset.filterAuthor);
      } else {
        f.authors.delete(cb.dataset.filterAuthor);
        if (f.authors.size === 0) { cb.checked = true; return; } // prevent all-off
      }
      applyFilter(f, true);
    });

    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-filter-year]');
      if (!btn) return;
      applyFilter({ authors: new Set(filter.authors), year: btn.dataset.filterYear }, true);
    });

    updateUI();
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  fetch('/data/filter-meta.json')
    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
    .then(function (m) {
      buildUI(m);
      var initial = parseHash();
      // Hash takes priority; fall back to localStorage if no hash is present.
      if (!initial.authors && initial.year === 'all') {
        initial = loadFilter() || initial;
      }
      if (initial.authors || initial.year !== 'all') {
        applyFilter(initial, false);
      }
    })
    .catch(function (e) { console.warn('Filter meta load failed:', e); });

  window.addEventListener('hashchange', function () {
    applyFilter(parseHash(), false);
  });
})();
