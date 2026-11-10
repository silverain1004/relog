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

  // ---- 메뉴 인터랙션: 핑크 바가 마우스를 따라가고, 벗어나면 현재 페이지로 돌아감
  if (nav) {
    var ink = document.createElement('span');
    ink.className = 'nav-ink';
    ink.setAttribute('aria-hidden', 'true');
    nav.appendChild(ink);
    nav.classList.add('has-ink');
    var navItems = $$('a, .nav-btn', nav);
    var navHome = $('a[aria-current=page]', nav);
    var moveInk = function (el) {
      if (!el) { ink.classList.remove('on'); return; }
      ink.style.width = el.offsetWidth + 'px';
      ink.style.transform = 'translateX(' + el.offsetLeft + 'px)';
      ink.classList.add('on');
    };
    navItems.forEach(function (el) {
      el.addEventListener('mouseenter', function () { moveInk(el); });
      el.addEventListener('focus', function () { moveInk(el); });
    });
    nav.addEventListener('mouseleave', function () { moveInk(navHome); });
    nav.addEventListener('focusout', function (e) { if (!nav.contains(e.relatedTarget)) moveInk(navHome); });
    var placeInk = function () {
      ink.style.transition = 'none';
      moveInk(navHome);
      void ink.offsetWidth;
      ink.style.transition = '';
    };
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(placeInk); else placeInk();
    window.addEventListener('resize', placeInk);
  }

  // ---- ABOUT: 수행 일정 (매월 1일 월간 · 매주 월요일 주간, 오늘 날짜 기준으로 완료/예정 자동 계산)
  // 회차별 Confluence 분석 보고서 공개 링크 (키: 'w주차' = 주간, 'm월' = 월간 / 분석 대상 기간 기준)
  var CONF = 'https://vntg.atlassian.net/wiki/external/';
  var REPORT_LINKS = {
    w32: 'MjViODA3ODIzZDY1NDY4Y2I5NWQzOWYzNWRiN2U5Njc',
    w33: 'OGNjNjk5YmZjZTE1NGFiMWJmYmI3NjgwNmE1MjQ3NTY',
    w34: 'ZTUwZGQ4N2E5MGExNDZhZTg4NTY3ZDI4OGZlMjI0NDA',
    w35: 'YWQxOTkwYjZhODRjNGRkNjkzOWM1ODdkNTY1ZTViN2U',
    m8: 'NWY5ZGYzMDRhOGU2NGJjNDhiMmVkMDUyOGQzNWNhZTI',
    w36: 'OWY0YzNjYjU0YmFhNGNkODkzZGEwMzdjZWJhZWZkNDQ',
    w37: 'OTRjODQ1NmFjNmY5NDA2ODhkZTZhZDdkNTkxYjk1MGY',
    w38: 'M2M0NzZlZmE1ZDc3NGZjMDk0Yjg3NDViNjgxZGI1NzM',
    w39: 'NmU2YzUwM2M0ODEwNGQ2N2I5NmJiYTk0OTJjYjE4MzQ',
    m9: 'MDIxNjc0ZGE5MzZjNGI4MjlmOTE2NDhmM2I5NmNkZDk',
    w40: 'MGIzNjBjYmM1ZTI0NDFlZTlhZjYzOGNjOTQ0MjVkMjI',
    w41: 'YjM3NjRiZGI3YzM1NGY0OGE1ZjYwMDlkNWYyMGM0Zjk',
    w42: 'ZTJlMzVjNGMwNDkyNGVlN2E2MGQ5ZGVlZmExYjQ5ZmM',
    w43: 'ZGM3MzliZGJiYzFlNGRlMmJjZDMxMWQzZTMwYTUxYTQ',
    m10: 'M2ZmOTkyMzY5MjgyNDk3ZDhlNTM4Y2YzYzU0MTQ4NmU',
    w44: 'MDRkNjkyYjk5ZTgzNDE2M2FlZjFlYTdiMDFhZGE1Yjg',
    w45: 'NTkxYmRiZWY4OTYyNDkwZThiYTcyNWFkMmUwNDU1OWQ'
  };
  function scheduleHTML() {
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var mmdd = function (d) { return pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
    var isoWeek = function (d) {
      var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
      t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
      return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
    };
    var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var start = new Date(2026, 5, 29);                          // 첫 정기 리포트: 2026-06-29 (26주)
    var end = new Date(today.getFullYear(), today.getMonth(), 1);   // 이번 달까지
    var months = (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth();
    if (months > 5) months = 5;                                 // 최근 6개월 (한 줄)
    var cols = '';
    for (var m = months; m >= 0; m--) {
      var first = new Date(end.getFullYear(), end.getMonth() - m, 1);
      var pm = new Date(first.getFullYear(), first.getMonth() - 1, 1).getMonth() + 1;
      var items = [{ d: first, label: '월간(' + pm + '월)', key: 'm' + pm }];
      var d = new Date(first);
      while (d.getDay() !== 1) d.setDate(d.getDate() + 1);
      for (; d.getMonth() === first.getMonth(); d.setDate(d.getDate() + 7)) {
        var prev = new Date(d); prev.setDate(prev.getDate() - 7);  // 월요일 리포트 = 지난주 분석
        var wk = isoWeek(prev);
        items.push({ d: new Date(d), label: wk + '주', key: 'w' + wk });
      }
      var before = items.length;
      items = items.filter(function (it) { return it.d >= start; });
      var isStart = items.length < before;                      // 시작 달: '⋮' 위에, 첫 회차는 아래쪽에
      var done = 0, lis = isStart ? '<li class="is-more" aria-label="이전 수작업 분석 기간">⋮</li>' : '';
      items.forEach(function (it) {
        var isDone = it.d <= today, url = isDone && first.getFullYear() === 2026 && REPORT_LINKS[it.key];
        if (!isDone) return;                                    // 예정 회차는 아래 '⋮' 하나로
        done++;
        var body = '<span class="sched-txt"><time>' + mmdd(it.d) + '</time>' + it.label + '</span>';
        lis += '<li class="' + (isDone ? 'is-done' : 'is-plan') + '">' +   // 링크 유무와 관계없이 같은 구조(.sched-cell)
          (url ? '<a class="sched-cell" href="' + CONF + url + '" target="_blank" rel="noopener" title="' + it.label + ' 분석 보고서">' + body + '<span class="sched-go" aria-hidden="true">↗</span></a>'
               : '<span class="sched-cell">' + body + '</span>') +
          '</li>';
      });
      if (done < items.length) lis += '<li class="is-more" aria-label="다음 회차 계속 진행 예정">⋮</li>';
      if (isStart) {                                            // 첫 회차를 맨 아래에서 4칸 위로 (같은 높이의 빈 칸 4개)
        var ghost = '<li class="is-ghost" aria-hidden="true"><span class="sched-cell"><span class="sched-txt"><time>00-00</time>-</span></span></li>';
        lis += ghost + ghost + ghost + ghost;
      }
      cols += '<div class="sched-month' + (isStart ? ' is-start' : '') + '"><h4>' + (first.getMonth() + 1) + '월</h4><ol>' + lis + '</ol></div>';
    }
    return '<section class="about-sched" aria-label="수행 일정">' +
        '<h3>Still running</h3>' +
        '<p class="sched-lead">매월 1일, 매주 월요일. 정기적으로 주간·월간 로그 분석 리포트가 자동으로 생성됩니다.</p>' +
        '<p class="sched-legend"><span aria-hidden="true">↗</span>클릭 시 분석 보고서를 볼 수 있습니다</p>' +
        '<p class="sched-note">Confluence 분석 보고서 자동 작성(2026.08) 이전 회차는 메일 리포트만 발송되어, 연결된 보고서가 없습니다.</p>' +
        '<div class="sched-grid">' + cols + '</div>' +
      '</section>';
  }

  // ---- ABOUT (개발자 정보 팝업)
  var ABOUT_HTML =
    '<div class="about-panel">' +
      '<button type="button" class="about-close" aria-label="닫기">' +
        '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>' +
      '</button>' +
      '<a class="about-source" href="https://github.com/silverain1004/relog" target="_blank" rel="noopener">GitHub Source ↗</a>' +
      '<span class="eyebrow">About the maker</span>' +
      '<h2 class="about-name" id="about-title" tabindex="-1" autofocus>Re<b>.</b>log</h2>' +
      '<p class="about-role">VNTG · ERP2팀 · <em>최은비 Ari</em></p>' +
      '<p class="about-intro">' +
        '평소 보안에 관심이 많아 시큐어코딩이나 최신 보안 취약점 동향 등을 꾸준히 찾아보곤 했습니다. ' +
        '그러다 2025년 5월 정보보호팀이 주관한 “모의해킹 및 인프라 취약점 조치계획 수립 및 이행”에서 로그 분석 항목을 접하게 됐습니다. ' +
        '하지만 회사에는 정기적인 로그 분석에 관한 규칙이 따로 없었습니다. ' +
        '그 필요성을 느껴 직접 작성한 ' +
        '<a href="https://docs.google.com/presentation/d/1UCtE4vVZwYF_fjeg2eyjnhybnukHRt9X/edit?usp=sharing&amp;ouid=108365588716953195308&amp;rtpof=true&amp;sd=true" target="_blank" rel="noopener">“내부 시스템 및 웹 서비스 보안을 위한 대응 전략 제안서” ↗</a>로 ' +
        '센터 내 전파교육을 진행했고, 그 당시 실제 담당했던 시스템의 보안 위협 사례를 보여주며 정기 로그 분석의 필요성을 공유했습니다.' +
      '</p>' +
      '<p class="about-intro">' +
        '이후 직접 정기적으로 로그를 들여다보기 시작했습니다. 쓸 만한 로그 분석 도구는 대부분 유료였기 때문에 ' +
        '매번 서버에 접속해 로그 파일을 대상으로 스크립트를 수동으로 돌리는 방식으로 진행해왔습니다. ' +
        '매주 이렇게 로그 파일을 직접 열어봐야 하나? 싶던 찰나, 깨달았습니다. ' +
      '</p>' +
      '<p class="about-intro about-punch">' +
        '네, 그렇습니다. 저는 “<em>없으면 만들면 되지</em>” 마인드로 살아온 개발자라는 사실을요. ' +
      '</p>' +
      '<p class="about-intro">' +
        '그렇게 시작한 자동화는 담당 시스템이 바뀌면서 Windows에서 Linux까지 분석 범위를 넓혔습니다. ' +
        '기존 업무를 이어받은 동료들에게도 메일이 갈 수 있도록 챙기고, 새로운 서버 환경에 맞춰 분석 기능도 확장했습니다.' +
      '</p>' +
      '<p class="about-intro">' +
        '처음엔 반복 작업이 귀찮아서 만든 도구였지만, 어느덧 몇 개월째 매주 리포트를 보내는 작은 서비스가 되었습니다. ' +
        '기획부터 개발, AI 요약, 리포트 발송, 웹 서비스 운영까지 직접 맡으며, ' +
        '규칙 없던 빈 자리를 이제는 매주 리포트로 채워 나가고 있습니다.' +
      '</p>' +
      '<div class="about-grid">' +
        '<div><h3>Project log</h3><ol class="about-log">' +
          '<li><time>2025.05</time>세아베스틸 대상 모의해킹 및 인프라 취약점 조치계획 수립 및 이행</li>' +
          '<li><time>2025.06</time>보안 위협 사례 및 로그 분석 중요성 전파교육</li>' +
          '<li><time>2025.07</time>매월·매주 정기 로그 분석 시작</li>' +
          '<li><time>2026.02</time>로그 분석 자동화 필요성 구상</li>' +
          '<li><time>2026.05</time>Windows · Linux 로그 분석 자동화 개발 착수</li>' +
          '<li><time>2026.06</time>Windows 분석기 완성 · 메일 자동 발송</li>' +
          '<li><time>2026.07</time>Linux 분석기 완성 · 통합 리포트 운영</li>' +
          '<li><time>2026.08</time>Confluence 분석 보고서 자동 작성</li>' +
          '<li><time>2026.10</time>정보보호팀 보안 검토 요청 · 침해 없음 확인</li>' +
          '<li><time>2026.11</time>AIVE Challenge 2026 하반기 출품</li>' +
        '</ol></div>' +
        '<div><h3>Built with</h3><ul class="about-tags">' +
          '<li>Python 3.6</li><li>Claude API</li><li>Nginx · Tomcat</li><li>Task Scheduler · cron</li><li>GitHub Pages</li><li>Apps Script</li><li>Claude Code</li>' +
        '</ul></div>' +
      '</div>' +
      scheduleHTML() +
      // 보안 검토 요청 (2026.10, 메일 4통 요약 — 담당자 이름·고객사 도메인·첨부 링크는 넣지 않음)
      '<section class="about-sec" aria-label="보안 검토 요청">' +
        '<h3>Beyond the report</h3>' +
        '<p class="sched-lead">분석에서 끝내지 않았습니다. 리포트만으로 판단하기 어려운 징후는 ' +
          '<em>정보보호팀에 직접 보안 검토를 요청</em>해, 실제 침해 여부를 끝까지 확인했습니다.</p>' +
        '<ol class="sec-thread">' +
          '<li class="is-me"><time>10.01</time><div><b>보안 검토 요청 <span>ERP2팀 → 정보보호팀</span></b>' +
            '<p>9월 정기 분석에서 이상 징후 3건을 정리해 IoC와 함께 전달했습니다.</p>' +
            '<ul><li>1분에 최대 448건, 337종 경로를 훑은 대량 스캔 (9/1~9/2)</li>' +
            '<li><code>/.claude/</code> · <code>/.cursor/mcp.json</code> 등 AI 도구 설정 파일 탐색 (9/28)</li>' +
            '<li>VPN 관리자 경로를 노린 상시 탐색 (주 50~70건)</li></ul></div></li>' +
          '<li><time>10.12</time><div><b>1차 회신 <span>정보보호팀</span></b>' +
            '<p>무작위 자동화 스캔으로 1차 판단. error.log는 실패 요청 위주라, 성공 요청 확인을 위해 access.log와 실제 출발지 IP를 추가로 요청받았습니다.</p></div></li>' +
          '<li class="is-me"><time>10.14</time><div><b>2차 자료 전달 <span>ERP2팀 → 정보보호팀</span></b>' +
            '<p>운영 서버 반출 권한을 협의해 access·error 로그 원본, VPN 스캔 129건 추출본, 실제 출발지 IP를 전달했습니다. 서버 간 로그 보존 기간 차이도 함께 공유했습니다.</p></div></li>' +
          '<li class="is-end"><time>10.15</time><div><b>최종 회신 · 종결 <span>정보보호팀</span></b>' +
            '<p>전 건 404, 접근에 성공한 요청 없음. <em>침해 없음으로 확인되어 종결</em>됐고, 프론트엔드 소스맵(.js.map) 외부 노출 점검이라는 추가 권고까지 받았습니다.</p></div></li>' +
        '</ol>' +
      '</section>' +
    '</div>';

  var aboutBtns = $$('[data-about]');
  if (aboutBtns.length) {
    var about = document.createElement('dialog');
    about.className = 'about';
    about.setAttribute('aria-labelledby', 'about-title');
    about.innerHTML = ABOUT_HTML;
    document.body.appendChild(about);
    var closeAbout = function () { if (about.close) about.close(); else about.removeAttribute('open'); };
    $('.about-close', about).addEventListener('click', closeAbout);
    about.addEventListener('click', function (e) { if (e.target === about) closeAbout(); });  // 바깥 클릭
    aboutBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        if (nav) { nav.classList.remove('open'); if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false'); }
        if (about.showModal) about.showModal(); else about.setAttribute('open', '');
      });
    });
    if (location.hash === '#about') aboutBtns[0].click();  // ...html#about 링크로 바로 열기
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
    var PLATFORM = { windows: 'Windows · E-OUT / IN-OUT', linux: 'Linux · WEB1 · WEB2 · WAS1 · WAS2' };
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    var NOTE = {
      demo: '합성 로그로 만든 리포트입니다. 시나리오는 10/29(목) 14시, DB 커넥션 풀 고갈로 주문 API 500 오류가 몰린 한 주. 스캐너 노이즈 속에서 이걸 찾아내는지 보세요.',
      'live-monthly': '실제 운영 서버에서 나온 리포트입니다. 건수·추이·분류는 그대로 두고 IP·도메인·계정 같은 식별 정보만 마스킹했습니다. 공개본이라 상세 로그 표는 일부만 보여 드립니다.'
    };
    NOTE.live = NOTE['live-monthly'];
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
        dd.innerHTML = v ? '<span class="pill ' + cls[v[1]] + '"><i>●</i> ' + v[1] + '</span>'
          : '<span class="pill pill-dim">AI 요약 없음</span>';
      }).catch(function () { dd.textContent = '—'; });
    }

    function render() {
      var m = state.m[state.source]; if (!m) return;
      var ks = kinds(state.source);
      if (ks.indexOf(state.kind) < 0) state.kind = ks[0];
      segBtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.source === state.source)); });

      // 탭(Windows/Linux)마다 원본 주차가 다를 수 있음 → 탭에 기간이 있으면 그 값을 우선
      var cur = m[state.kind] || {};
      var pm = { period_key: cur.period_key || m.period_key, period_label: cur.period_label || m.period_label };
      $('#r-title').innerHTML = title(pm);
      $('#r-note').textContent = NOTE[state.source];
      $('#v-period').textContent = period(pm);
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
      $('#mail-subject').textContent = (sec.email ? '' : '[리포트] ') + (sec.title || '') + ' — ' + (pm.period_label || '');
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
    // Google Apps Script 웹 앱 'Relog' (mailer/README.md)
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

  // ---- Impact: 배경 로그를 손전등처럼 비춰 읽기 (마우스 따라감 / 터치·대기 시 혼자 천천히 이동)
  var stage = $('[data-logstage]');
  if (stage) {
    var seed = 7;
    var rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var pick = function (a) { return a[Math.floor(rnd() * a.length)]; };
    var PATHS = ['/biz/odr/ODR040', '/biz/exs/EXS010', '/api/order/list', '/main', '/biz/ror/ROR010', '/static/js/app.js', '/api/stock/search', '/login'];
    var SCANS = ['/remote/fgt_lang?lang=/../../../..//////////dev/', '/wp-login.php', '/.env', '/cgi-bin/luci/;stok=/locale', '/wp-includes/wlwmanifest.xml', '/remote/login?lang=en'];
    var esc = function (s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;'); };
    var lines = [];
    for (var n = 0; n < 70; n++) {
      var scan = rnd() < 0.16, ip = (scan ? '198.51.100.' : '203.0.113.') + (1 + Math.floor(rnd() * 254));
      var t = '[02/Nov/2026:0' + Math.floor(rnd() * 10) + ':' + pad2(Math.floor(rnd() * 60)) + ':' + pad2(Math.floor(rnd() * 60)) + ' +0900]';
      var line = ip + ' - - ' + t + ' "' + (scan ? 'GET ' + pick(SCANS) : pick(['GET ', 'GET ', 'POST ']) + pick(PATHS)) +
        ' HTTP/1.1" ' + (scan ? 404 : pick([200, 200, 200, 304, 302])) + ' ' + Math.floor(rnd() * 9000 + 120) + ' "-" "' +
        (scan ? 'Mozilla/5.0 zgrab/0.x' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)') + '"';
      lines.push(scan ? '<span class="noise">' + esc(line) + '</span>' : esc(line));
    }
    var html = lines.join('\n');
    ['logs-base', 'logs-lit'].forEach(function (cls) {
      var pre = document.createElement('pre');
      pre.className = 'logs-layer ' + cls; pre.setAttribute('aria-hidden', 'true'); pre.innerHTML = html;
      stage.insertBefore(pre, stage.firstChild);
    });
    var lit = $('.logs-lit', stage);
    var setSpot = function (x, y) { lit.style.setProperty('--mx', x + 'px'); lit.style.setProperty('--my', y + 'px'); };
    var still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var hovering = false, visible = true, raf = 0, t0 = performance.now();
    var drift = function (now) {                                 // 마우스가 없을 때: 느린 8자 궤적
      raf = 0;
      if (hovering || !visible) return;
      var w = stage.clientWidth, h = stage.clientHeight, s = (now - t0) / 1000;
      setSpot(w * (0.5 + 0.38 * Math.sin(s * 0.23)), h * (0.5 + 0.32 * Math.sin(s * 0.41)));
      raf = requestAnimationFrame(drift);
    };
    var startDrift = function () { if (!still && !raf) raf = requestAnimationFrame(drift); };
    // 마우스가 멈추면 빛이 천천히 꺼짐 — 움직일 때만 읽고, 멈추면 쉰다
    var restTimer = 0;
    var wake = function () {
      lit.classList.remove('is-resting');
      clearTimeout(restTimer);
      restTimer = setTimeout(function () { lit.classList.add('is-resting'); }, 120);
    };
    stage.addEventListener('pointermove', function (e) {
      if (e.pointerType !== 'mouse') return;
      hovering = true;
      var r = stage.getBoundingClientRect(); setSpot(e.clientX - r.left, e.clientY - r.top);
      wake();
    });
    stage.addEventListener('pointerleave', function () {
      hovering = false; clearTimeout(restTimer); lit.classList.remove('is-resting');
      t0 = performance.now(); startDrift();
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) startDrift(); }).observe(stage);
    }
    if (still) setSpot(stage.clientWidth * 0.7, stage.clientHeight * 0.4); else startDrift();
  }
  // ---- Process: 다음 실행까지 카운트다운 (매주 월 08:00 주간 · 매월 1일 08:00 월간 중 가까운 쪽)
  var runBox = $('[data-nextrun]');
  if (runBox) {
    var big = $('[data-nextrun-big]', runBox), label = $('[data-nextrun-label]', runBox);
    var DAYS = ['일', '월', '화', '수', '목', '금', '토'];
    var nextRun = function (now) {
      var w = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 8);
      w.setDate(w.getDate() + ((8 - w.getDay()) % 7));            // 이번 주/다음 주 월요일 08:00
      if (w <= now) w.setDate(w.getDate() + 7);
      var m = new Date(now.getFullYear(), now.getMonth(), 1, 8);
      if (m <= now) m = new Date(now.getFullYear(), now.getMonth() + 1, 1, 8);
      var at = w < m ? w : m;
      var kind = +w === +m ? '주간·월간' : (at === w ? '주간' : '월간');
      return { at: at, text: (at.getMonth() + 1) + '/' + at.getDate() + ' (' + DAYS[at.getDay()] + ') 08:00 ' + kind + ' 리포트' };
    };
    var tick = function () {
      var now = new Date(), nr = nextRun(now), s = Math.max(0, Math.floor((nr.at - now) / 1000));
      big.textContent = Math.floor(s / 86400) + 'd ' + pad2(Math.floor(s / 3600) % 24) + ':' + pad2(Math.floor(s / 60) % 60) + ':' + pad2(s % 60);
      label.textContent = nr.text;
    };
    tick(); setInterval(tick, 1000);
  }

  // ---- Process: 스크롤을 따라 파이프라인이 채워지고, 닿은 단계가 켜짐
  var pipeline = $('[data-pipeline]');
  if (pipeline) {
    var bar = $('.pipe i', pipeline), steps = $$('.step', pipeline);
    var calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var update = function () {
      var r = pipeline.getBoundingClientRect(), mid = window.innerHeight * 0.6;
      var p = calm ? 1 : Math.min(1, Math.max(0, (mid - r.top) / r.height));
      bar.style.setProperty('--p', p.toFixed(4));
      var y = r.top + p * r.height;
      steps.forEach(function (s) {
        var idx = $('.idx', s).getBoundingClientRect();
        s.classList.toggle('is-live', y >= idx.top + idx.height / 2);
      });
    };
    var queued = false;
    var onScroll = function () { if (!queued) { queued = true; requestAnimationFrame(function () { queued = false; update(); }); } };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
})();
