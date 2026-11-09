/* Re.log — site behaviour (menu, reveal, report viewer, mail form) */
(function () {
  'use strict';
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // ---- mobile menu
  var menuBtn = $('.menu-btn'), nav = $('.nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', String(open));
    });
  }

  // ---- reveal on scroll (+ chart bars grow)
  var reveals = $$('.reveal');
  var bars = $$('.bars i');
  bars.forEach(function (b) { b.style.transform = 'scaleY(0)'; });
  function show(el) {
    el.classList.add('in');
    $$('.bars i', el).forEach(function (b) { b.style.transform = 'scaleY(1)'; });
  }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { show(e.target); io.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(show);
  }

  // ---- report viewer (report.html)
  var viewer = $('#viewer');
  if (viewer) initViewer();

  function initViewer() {
    var SOURCES = ['demo', 'live', 'live-monthly'];
    var KIND = { windows: 'Windows', linux: 'Linux' };
    var PLATFORM = { windows: 'Windows · E-OUT / IN-OUT', linux: 'Linux · WEB×2 / WAS×2' };
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    var NOTE = {
      demo: '합성 로그로 만든 리포트입니다. 시나리오는 10/29(목) 14시, DB 커넥션 풀 고갈로 주문 API 500 오류가 몰린 한 주. 스캐너 소음 속에서 이걸 찾아내는지 보세요.',
      live: '실제 운영 서버에서 나온 리포트입니다. 건수·추이·분류는 그대로 두고 IP·도메인·계정 같은 식별 정보만 마스킹했습니다. 공개본이라 상세 로그 표는 일부만 보여 드립니다.'
    };
    NOTE['live-monthly'] = NOTE.live;
    var state = { source: 'demo', kind: 'windows', m: {} };
    var segBtns = $$('#source-seg button');

    function title(m) {
      var k = m.period_key || '';
      var w = /^\d{4}W(\d{1,2})$/.exec(k);
      if (w) return 'Week ' + Number(w[1]);
      var mo = /^(\d{4})(\d{2})$/.exec(k);
      if (mo) return MONTHS[Number(mo[2]) - 1] + '<span class="serif"> ' + mo[1] + '</span>';
      return k;
    }
    function period(m) {
      var p = /\((\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})\)/.exec(m.period_label || '');
      return p ? p[1] + ' — ' + p[2].slice(5) : (m.period_label || '');
    }
    function kinds(src) {
      var m = state.m[src]; if (!m) return [];
      return ['windows', 'linux'].filter(function (k) { return m[k] && (m[k].email || (m[k].reports || []).length); });
    }
    function verdict(url) {
      var dd = $('#v-verdict');
      dd.innerHTML = '<span class="pill pill-dim">확인 중</span>';
      fetch(url, { cache: 'no-cache' }).then(function (r) { return r.text(); }).then(function (t) {
        var v = /종합:\s*(정상|주의|위험)/.exec(t);
        var cls = { '정상': 'pill-ok', '주의': 'pill-warn', '위험': 'pill-bad' };
        dd.innerHTML = v ? '<span class="pill ' + cls[v[1]] + '">● ' + v[1] + '</span>'
          : '<span class="pill pill-dim">AI 요약 없음</span>';
      }).catch(function () { dd.textContent = '—'; });
    }

    function render() {
      var m = state.m[state.source]; if (!m) return;
      var ks = kinds(state.source);
      if (ks.indexOf(state.kind) < 0) state.kind = ks[0];
      segBtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.source === state.source)); });

      $('#r-title').innerHTML = title(m);
      $('#r-note').textContent = NOTE[state.source];
      $('#v-period').textContent = period(m);
      $('#v-platform').textContent = PLATFORM[state.kind];
      $('#v-source').textContent = state.source === 'demo' ? '합성 로그' : '운영 서버 · 마스킹';

      var tabs = $('#kind-tabs'); tabs.textContent = '';
      ks.forEach(function (k) {
        var b = document.createElement('button');
        b.type = 'button'; b.setAttribute('role', 'tab'); b.textContent = KIND[k];
        b.setAttribute('aria-selected', String(k === state.kind));
        b.addEventListener('click', function () { state.kind = k; render(); });
        tabs.appendChild(b);
      });

      var sec = m[state.kind] || {};
      var path = sec.email || (sec.reports && sec.reports[0] && sec.reports[0].href);
      var url = state.source + '/' + path;
      $('#mail-frame').src = url;
      $('#mail-subject').textContent = (sec.email ? '' : '[리포트] ') + (sec.title || '') + ' — ' + (m.period_label || '');
      $('#frame-note').textContent = sec.email
        ? '실제로 발송되는 HTML 메일 본문입니다. 상세 리포트는 ZIP으로 첨부됩니다.'
        : '이 기간은 메일 원본 대신 대표 리포트를 보여 드립니다.';
      verdict(url);
      $('#get-this').href = 'contact.html?src=' + state.source;

      var files = $('#files'); files.textContent = ''; var n = 0;
      ['windows', 'linux'].forEach(function (k) {
        ((m[k] && m[k].reports) || []).forEach(function (r) {
          var a = document.createElement('a');
          a.href = state.source + '/' + r.href; a.target = '_blank'; a.rel = 'noopener';
          n += 1;
          a.innerHTML = '<span class="no">' + (n < 10 ? '0' : '') + n + '</span><span class="t"></span><span class="k">' + KIND[k] + '</span><span aria-hidden="true">↗</span>';
          a.querySelector('.t').textContent = r.title;
          files.appendChild(a);
        });
      });
    }

    segBtns.forEach(function (b) {
      b.addEventListener('click', function () { if (!b.disabled) { state.source = b.dataset.source; render(); } });
    });

    var q = /[?&]src=([\w-]+)/.exec(location.search);
    if (q && SOURCES.indexOf(q[1]) >= 0) state.source = q[1];

    Promise.all(SOURCES.map(function (src) {
      return fetch(src + '/manifest.json', { cache: 'no-cache' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (m) { state.m[src] = m; })
        .catch(function () {
          var b = $('#source-seg button[data-source="' + src + '"]');
          if (b) { b.disabled = true; b.textContent += ' · 준비 중'; }
          if (state.source === src) state.source = 'demo';
        });
    })).then(render);
  }

  // ---- mail form (contact.html)
  var form = $('#mail-form');
  if (form) initMail();

  function initMail() {
    // Google Apps Script 웹 앱 (apps-script/README.md)
    var MAIL_ENDPOINT = 'https://script.google.com/a/macros/vntgcorp.com/s/AKfycbwRoXw2rW_LGw6AywT-fGd53JEk1L9oWL-6GERTML2LgHxwAKcEMtpgAyD1Prryr3UQ/exec';
    var ALLOWED_DOMAIN = 'vntgcorp.com';
    var msg = $('#mail-msg'), send = $('#mail-send'), mode = 'inline';
    function say(text, cls) { msg.textContent = text; msg.className = 'msg' + (cls ? ' ' + cls : ''); }

    var q = /[?&]src=([\w-]+)/.exec(location.search);
    var pre = q && form.querySelector('input[name=source][value="' + q[1] + '"]');
    if (pre) pre.checked = true;

    // 공개되지 않은 출처는 고를 수 없게
    ['live', 'live-monthly'].forEach(function (src) {
      fetch(src + '/manifest.json', { method: 'HEAD', cache: 'no-cache' }).then(function (r) {
        if (r.ok) return;
        var radio = form.querySelector('input[name=source][value="' + src + '"]');
        if (radio) { radio.disabled = true; if (radio.checked) form.querySelector('input[name=source][value=demo]').checked = true; }
      }).catch(function () {});
    });

    // 배포 액세스 확인: 익명 호출이 되면 페이지 안에서(inline), 막혀 있으면 새 탭(tab)
    fetch(MAIL_ENDPOINT, { method: 'POST', body: JSON.stringify({ probe: true }) })
      .then(function (r) { return r.json(); })
      .then(function (res) { mode = res && res.ok ? 'inline' : 'tab'; })
      .catch(function () { mode = 'tab'; });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var to = String(fd.get('email') || '').trim().toLowerCase();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) return say('이메일 주소를 확인해 주세요.', 'err');
      if (to.split('@')[1] !== ALLOWED_DOMAIN) return say('사내 메일(@' + ALLOWED_DOMAIN + ')로만 받을 수 있어요.', 'err');
      var payload = { email: to, source: fd.get('source'), kind: fd.get('kind'), website: fd.get('website') || '' };

      if (mode === 'tab') {
        var f = document.createElement('form');
        f.method = 'POST'; f.action = MAIL_ENDPOINT; f.target = '_blank'; f.style.display = 'none';
        Object.keys(payload).forEach(function (k) {
          var i = document.createElement('input'); i.type = 'hidden'; i.name = k; i.value = payload[k]; f.appendChild(i);
        });
        document.body.appendChild(f); f.submit(); f.remove();
        return say('새 탭에서 발송 결과를 확인해 주세요. (회사 구글 계정 로그인 필요)', 'ok');
      }

      send.disabled = true; say('보내는 중…');
      fetch(MAIL_ENDPOINT, { method: 'POST', body: JSON.stringify(payload) })  // text/plain → CORS preflight 없음
        .then(function (r) { return r.json(); })
        .then(function (res) { say(res.message, res.ok ? 'ok' : 'err'); })
        .catch(function () { mode = 'tab'; say('연결 방식을 바꿨어요. [보내기]를 한 번 더 눌러 주세요.', 'err'); })
        .then(function () { send.disabled = false; });
    });
  }
})();
