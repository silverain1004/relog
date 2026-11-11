/* Re.log — site behaviour (menu, reveal, report viewer, mail form) */
(function () {
  'use strict';
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // ---- 버튼그룹 공통: 선택 표시(알약)가 고른 항목으로 미끄러져 이동. update()를 선택이 바뀔 때마다 호출
  function slideThumb(box, activeSel) {
    if (!box) return function () {};
    var t = document.createElement('span');
    t.className = 'slide-thumb'; t.setAttribute('aria-hidden', 'true');
    box.insertBefore(t, box.firstChild); box.classList.add('has-thumb');
    var placed = false;
    function update(instant) {
      var on = box.querySelector(activeSel);
      if (!on || !on.offsetWidth) { t.style.opacity = '0'; placed = false; return; }
      var jump = instant || !placed;
      if (jump) t.style.transition = 'none';
      t.style.opacity = '';
      t.style.width = on.offsetWidth + 'px';
      t.style.height = on.offsetHeight + 'px';
      t.style.transform = 'translate(' + on.offsetLeft + 'px,' + on.offsetTop + 'px)';
      if (jump) { void t.offsetWidth; t.style.transition = ''; }
      placed = true;
    }
    window.addEventListener('resize', function () { update(true); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { update(true); });
    update(true);
    return update;
  }

  // ---- 드래그(텍스트 선택·이미지 끌기)와 우클릭 막기 — 입력 칸은 예외
  var editable = function (el) { return el && el.closest && el.closest('input, textarea, select, [contenteditable]'); };
  ['contextmenu', 'dragstart', 'selectstart'].forEach(function (type) {
    document.addEventListener(type, function (e) { if (!editable(e.target)) e.preventDefault(); });
  });

  // ---- mobile menu
  var menuBtn = $('.menu-btn'), nav = $('.nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', String(open));
    });
  }

  // ---- 헤더: 아래로 스크롤하면 숨고, 위로 올리면 상단에 고정된 채 다시 나타남
  var head = $('.site-head');
  if (head) {
    var spacer = document.createElement('div');
    spacer.className = 'head-spacer';
    spacer.setAttribute('aria-hidden', 'true');
    head.parentNode.insertBefore(spacer, head);
    var lastY = window.scrollY, headTop = 0, headH = 0;
    var measure = function () {
      if (head.classList.contains('is-float')) { headTop = spacer.getBoundingClientRect().top + window.scrollY; }
      else { var r = head.getBoundingClientRect(); headTop = r.top + window.scrollY; headH = r.height; }
    };
    var setFloat = function (on) {
      if (on === head.classList.contains('is-float')) return;
      if (on) {
        spacer.style.height = headH + 'px';
        head.classList.add('is-float', 'is-hidden');
        void head.offsetWidth;            // 숨은 상태로 먼저 자리 잡고 나서 애니메이션 켜기
        head.classList.add('is-anim');
      } else {
        head.classList.remove('is-float', 'is-hidden', 'is-anim');
        spacer.style.height = '';
      }
    };
    var headTick = function () {
      var y = Math.max(0, window.scrollY), dy = y - lastY;
      if (y <= headTop) setFloat(false);
      else if (y > headTop + headH) setFloat(true);
      if (head.classList.contains('is-float') && Math.abs(dy) > 4) {
        var menuOpen = nav && nav.classList.contains('open');
        head.classList.toggle('is-hidden', dy > 0 && !menuOpen);
      }
      if (Math.abs(dy) > 4 || y <= headTop) lastY = y;
    };
    var headQueued = false;
    window.addEventListener('scroll', function () {
      if (!headQueued) { headQueued = true; requestAnimationFrame(function () { headQueued = false; headTick(); }); }
    }, { passive: true });
    window.addEventListener('resize', function () { measure(); if (head.classList.contains('is-float')) spacer.style.height = head.offsetHeight + 'px'; });
    measure(); headTick();
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
      el.addEventListener('focus', function () {  // 키보드 이동일 때만 (팝업 닫힐 때 ABOUT으로 돌아오는 포커스는 무시)
        var kb = true; try { kb = el.matches(':focus-visible'); } catch (e) {}
        if (kb) moveInk(el);
      });
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
    var mmdd = function (d) { return pad(d.getMonth() + 1) + '/' + pad(d.getDate()); };
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
        var ghost = '<li class="is-ghost" aria-hidden="true"><span class="sched-cell"><span class="sched-txt"><time>00/00</time>-</span></span></li>';
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
      // 상단 바: 스크롤하면 로고가 나타나고 배경이 깔린 채 위에 고정 (is-stuck)
      '<div class="about-bar">' +
        '<span class="about-bar-logo" aria-hidden="true">Re<b>.</b>log</span>' +
        '<a class="about-source" href="https://github.com/silverain1004/relog" target="_blank" rel="noopener">GitHub ↗</a>' +
        '<button type="button" class="about-close" aria-label="닫기">' +
          '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>' +
        '</button>' +
      '</div>' +
      '<span class="eyebrow">About the maker</span>' +
      '<h2 class="about-name" id="about-title" tabindex="-1" autofocus>Re<b>.</b>log</h2>' +
      '<p class="about-role">VNTG · ERP2팀 · <em>최은비 Ari</em></p>' +
      '<p class="about-intro">' +
        '평소 보안에 관심이 많아 시큐어코딩이나 최신 동향 등을 꾸준히 찾아보곤 했습니다. ' +
        '그러다 2025년 5월 정보보호팀이 주관한 <strong class="about-hl">“모의해킹 및 인프라 취약점 조치계획 수립 및 이행”</strong>에서 로그 분석 항목을 접하게 됐습니다. ' +
        '하지만 회사에는 정기적인 로그 분석에 관한 규칙이 따로 없었고, 그 필요성을 느껴 직접 작성한 ' +
        '<a href="https://docs.google.com/presentation/d/1UCtE4vVZwYF_fjeg2eyjnhybnukHRt9X/edit?usp=sharing&amp;ouid=108365588716953195308&amp;rtpof=true&amp;sd=true" target="_blank" rel="noopener">“내부 시스템 및 웹 서비스 보안을 위한 대응 전략 제안서” ↗</a>로 ' +
        '센터 내 전파교육을 진행하며, 그 당시 실제 담당했던 시스템의 보안 위협 사례와 함께 정기 로그 분석의 필요성을 공유했습니다.' +
      '</p>' +
      '<p class="about-intro">' +
        '이후 직접 담당 시스템들의 로그를 들여다보기 시작했습니다. 쓸 만한 로그 분석 도구는 대부분 유료였기 때문에 ' +
        '매번 서버에 직접 접속해 로그 파일을 대상으로 스크립트를 수동으로 돌리는 방식이었죠. ' +
        '매주 이렇게 로그 파일을 직접 열어봐야 하나? 싶던 찰나,<br>문득 깨달았습니다.' +
      '</p>' +
      '<p class="about-intro about-punch">' +
        '네, 저는 “<em>없으면 만들면 되지</em>” 마인드로 살아온 개발자라는 사실을요. ' +
      '</p>' +
      '<p class="about-intro">' +
        '그렇게 자동화 개발을 시작하게 됐고, 담당 시스템이 추가되면서 Windows에서 Linux까지 분석 범위를 넓혔습니다. ' +
        '이후 기존 업무를 이어받은 동료들에게도 해당 서비스를 안내하고 메일을 받을 수 있도록 챙기고 조금씩 고도화해나갔습니다.' +
      '</p>' +
      '<p class="about-intro">' +
        '처음엔 반복 작업이 귀찮아서 만든 기능이, 어느덧 몇 개월째 매주 리포트를 보내는 작은 서비스가 되었습니다. ' +
        '기획부터 개발, AI 요약, 리포트 발송, 웹 서비스 운영까지 직접 맡으며, ' +
        '규칙 없던 빈 자리를 이제는 매주 리포트로 채워 나가고 있습니다.' +
      '</p>' +
      '<div class="about-grid">' +
        '<div><h3>Project log</h3><ol class="about-log">' +
          '<li><time>2025.05</time>세아베스틸 대상 모의해킹 및 인프라 취약점 조치계획 수립 및 이행</li>' +
          '<li><time>2025.06</time>보안 위협 사례 및 로그 분석 중요성 전파교육</li>' +
          '<li><time>2025.07</time>매월·매주 정기 로그 분석 시작</li>' +
          '<li><time>2026.02</time>로그 분석 자동화 기획 · 설계</li>' +
          '<li><time>2026.05</time>Windows · Linux 로그 분석 자동화 개발 착수</li>' +
          '<li><time>2026.06</time>Windows 분석기 완성 · 메일 자동 발송</li>' +
          '<li><time>2026.07</time>Linux 분석기 완성 · 통합 리포트 운영</li>' +
          '<li><time>2026.08</time>Confluence 분석 보고서 자동 작성</li>' +
          '<li><time>2026.10</time>정보보호팀 보안 검토 요청 · 침해 없음 확인</li>' +
          '<li><time>2026.11</time>AIVE Challenge 2026 하반기 출품</li>' +
        '</ol></div>' +
        '<div><h3>Built with</h3><ul class="about-tags">' +
          '<li>Python 3.6</li><li>Paramiko</li><li>PyInstaller</li><li>pytest</li><li>Claude API</li><li>Claude Code</li><li>Nginx</li><li>Tomcat</li><li>Task Scheduler</li><li>cron</li><li>SMTP</li><li>Apps Script</li><li>GitHub Pages</li>' +
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
            '<p>access·error 로그와 VPN 로그를 함께 분석한 결과, 9월 탐지 건은 모두 인터넷상 자동화 도구에 의한 스캔으로 판단되었습니다.</p>' +
            '<ul><li>대량 스캔 (9/1~9/2): 단일 출발지에서 수십 초간 무작위 경로 탐색</li>' +
            '<li>AI 도구 설정 파일 탐색 (9/28): 4건의 단순 탐색</li>' +
            '<li>VPN 관리자 경로 탐색: 인터넷 조사용 스캐너의 정기 탐색</li></ul>' +
            '<p>모두 404 응답으로 접근하거나 실행에 성공한 요청은 없었고, <em>침해 없음으로 확인되어 종결</em>되었습니다.</p></div></li>' +
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
    var lockScroll = function (on) {  // About이 열려 있는 동안 뒤 페이지 스크롤 막기 (스크롤바 폭만큼 보정해 화면 흔들림 방지)
      var root = document.documentElement;
      if (on) {
        var sb = window.innerWidth - root.clientWidth;
        root.classList.add('scroll-lock');
        if (sb > 0) document.body.style.paddingRight = sb + 'px';
      } else {
        root.classList.remove('scroll-lock');
        document.body.style.paddingRight = '';
      }
    };
    var closeAbout = function () { if (about.close) about.close(); else { about.removeAttribute('open'); lockScroll(false); } };
    about.addEventListener('close', function () {
      lockScroll(false);
      if (typeof moveInk === 'function') moveInk(navHome);  // About은 팝업이라 막대는 지금 페이지 메뉴로 복귀
    });
    $('.about-close', about).addEventListener('click', closeAbout);
    about.addEventListener('click', function (e) { if (e.target === about) closeAbout(); });  // 바깥 클릭
    var aboutPanel = $('.about-panel', about), aboutBar = $('.about-bar', about), aboutName = $('.about-name', about);
    var syncBar = function () {  // 큰 Re.log 제목이 상단 바 뒤로 지나가면 바에 작은 로고 표시
      aboutBar.classList.toggle('is-stuck', aboutPanel.scrollTop > aboutName.offsetTop + aboutName.offsetHeight - aboutBar.offsetHeight);
    };
    aboutPanel.addEventListener('scroll', syncBar, { passive: true });
    aboutBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        if (nav) { nav.classList.remove('open'); if (menuBtn) menuBtn.setAttribute('aria-expanded', 'false'); }
        lockScroll(true);
        if (about.showModal) about.showModal(); else about.setAttribute('open', '');
        aboutPanel.scrollTop = 0; syncBar();
      });
    });
    if (location.hash === '#about') aboutBtns[0].click();  // ...html#about 링크로 바로 열기
  }

  // ---- 도움말 툴팁: 마우스오버·포커스는 CSS, 터치 기기는 ? 버튼 클릭으로 열고 닫기
  $$('[data-tip]').forEach(function (box) {
    var btn = $('.info-btn', box);
    if (!btn) return;
    var setOpen = function (open) {
      box.classList.toggle('open', open);
      btn.setAttribute('aria-expanded', String(open));
    };
    btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(!box.classList.contains('open')); });
    // 배경 아무 곳이나 누르면 닫기 — iOS는 빈 배경 탭에 click을 안 쏘므로 pointerdown 사용
    document.addEventListener('pointerdown', function (e) {
      if (box.contains(e.target)) return;
      setOpen(false);
      if (box.contains(document.activeElement)) document.activeElement.blur();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
  });

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
    var PLATFORM = { windows: 'Windows · WEB · WAS1 · WAS2', linux: 'Linux · WEB1 · WEB2 · WAS1 · WAS2' };
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    var NOTE = {
      demo: '시나리오는 10/29(목) 14시, Windows 서버에서 DB 커넥션 풀 고갈로 주문 API의 500 오류가 집중적으로 발생한 상황. 각종 스캐너 노이즈가 뒤섞인 로그 속에서, 과연 이 이상 징후를 찾아낼 수 있을까요?',
      'live-monthly': '실제 운영 리포트를 공개용으로 마스킹한 사본입니다. 실제 메일에는 원본 그대로 담겨 내부 담당자에게만 발송되며, 여기서는 IP · 도메인 · 계정 등 보안상 민감한 정보만 마스킹했습니다. 상세 로그 표는 일부만 보여 드립니다.'
    };
    NOTE.live = NOTE['live-monthly'];
    var state = { source: 'demo', kind: 'windows', m: {} };
    var segBtns = $$('#source-seg button'), aiSw = $('#ai-sw');
    // AI 요약 켬 = 데모(주간만) · 끔 = 실제 운영 리포트(주간 · 월간) — Try it 폼과 같은 구조
    var PICK = { 'on weekly': 'demo', 'off weekly': 'live', 'off monthly': 'live-monthly' };
    var aiOf = function (src) { return src === 'demo'; };
    var periodOf = function (src) { return src === 'live-monthly' ? 'monthly' : 'weekly'; };
    var has = function (src) { return !!state.m[src]; };
    var lastSource = null, lastFrameUrl = '';
    var moveSegThumb = slideThumb($('#source-seg'), 'button[aria-pressed=true]');
    var moveKindThumb = slideThumb($('#kind-tabs'), 'button[aria-selected=true]');

    // 주간 'Week 44' · 월간 'October' 모두 한 줄로 (연도는 Period에)
    function title(m) {
      var k = m.period_key || '';
      var w = /^\d{4}W(\d{1,2})$/.exec(k);
      if (w) return 'Week ' + Number(w[1]);
      var mo = /^\d{4}(\d{2})$/.exec(k);
      if (mo) return MONTHS[Number(mo[1]) - 1];
      return k;
    }
    function period(m) {
      var p = /\((\d{4}-\d{2}-\d{2}) ~ (\d{4}-\d{2}-\d{2})\)/.exec(m.period_label || '');
      var sl = function (d) { return d.replace(/-/g, '/'); };  // 2026/10/26 - 11/01
      return p ? sl(p[1]) + ' - ' + sl(p[2].slice(5)) : (m.period_label || '');
    }
    function kinds(src) {
      var m = state.m[src]; if (!m) return [];
      return ['windows', 'linux'].filter(function (k) { return m[k] && (m[k].email || (m[k].reports || []).length); });
    }
    var escTxt = function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
    function swapIn(el, delay) {
      el.classList.remove('swap-in'); void el.offsetWidth;
      el.style.animationDelay = (delay || 0) + 'ms';
      el.classList.add('swap-in');
    }
    function verdict(url, animate) {
      var dd = $('#v-verdict');
      // 이미 판정이 떠 있으면 '확인 중'으로 깜빡이지 않고 결과가 오면 바뀐 경우에만 교체
      if (!dd.querySelector('.pill:not(.pill-dim)')) dd.innerHTML = '<span class="pill pill-dim">확인 중</span>';
      fetch(url, { cache: 'no-cache' }).then(function (r) { return r.text(); }).then(function (t) {
        if (url !== lastFrameUrl) return;  // 그사이 다른 리포트로 바뀌었으면 무시
        var v = /종합:\s*(정상|주의|위험)/.exec(t);
        var cls = { '정상': 'pill-ok', '주의': 'pill-warn', '위험': 'pill-bad' };
        // 운영 리포트(AI 요약 없음)는 장애 없이 지나간 기간이라 정상으로 표시
        var lv = v ? v[1] : (state.source !== 'demo' ? '정상' : null);
        var html = lv ? '<span class="pill ' + cls[lv] + '"><i>●</i> ' + lv + '</span>'
          : '<span class="pill pill-dim">AI 요약 없음</span>';
        if (dd.innerHTML !== html) { dd.innerHTML = html; if (animate) swapIn(dd, 0); }
        fillStats(t);
      }).catch(function () { if (url === lastFrameUrl) dd.textContent = '—'; });
    }

    function render() {
      var m = state.m[state.source]; if (!m) return;
      var ks = kinds(state.source);
      if (ks.indexOf(state.kind) < 0) state.kind = ks[0];
      var aiOn = aiOf(state.source);
      aiSw.checked = aiOn;
      aiSw.disabled = !has('live') && !has('live-monthly');
      segBtns.forEach(function (b) {
        var src = PICK[(aiOn ? 'on ' : 'off ') + b.dataset.period];
        b.disabled = !src || !has(src);
        b.setAttribute('aria-pressed', String(b.dataset.period === periodOf(state.source)));
      });
      moveSegThumb();
      // 소스를 바꿀 때 내용이 실제로 달라진 칸만 새로 들어오게 (같은 값은 그대로 둠)
      var animate = !!lastSource && lastSource !== state.source, order = 0;
      lastSource = state.source;
      var put = function (sel, html) {
        var el = $(sel); if (!el || el.innerHTML === html) return;
        el.innerHTML = html;
        if (animate) swapIn(el, (order++) * 60);
      };

      // 탭(Windows/Linux)마다 원본 주차가 다를 수 있음 → 탭에 기간이 있으면 그 값을 우선
      var cur = m[state.kind] || {};
      var pm = { period_key: cur.period_key || m.period_key, period_label: cur.period_label || m.period_label };
      put('#r-title', title(pm));
      put('#r-note', escTxt(NOTE[state.source]));
      put('#v-period', escTxt(period(pm)));
      put('#v-platform', escTxt(PLATFORM[state.kind]));
      put('#v-source', state.source === 'demo' ? '데모 · 합성 로그' : '운영 서버 · 마스킹');

      var tabs = $('#kind-tabs'); $$('button', tabs).forEach(function (b) { tabs.removeChild(b); });
      ks.forEach(function (k) {
        var b = document.createElement('button');
        b.type = 'button'; b.setAttribute('role', 'tab'); b.textContent = KIND[k];
        b.setAttribute('aria-selected', String(k === state.kind));
        b.addEventListener('click', function () { state.kind = k; render(); });
        tabs.appendChild(b);
      });
      moveKindThumb();

      var sec = m[state.kind] || {};
      var path = sec.email || (sec.reports && sec.reports[0] && sec.reports[0].href);
      var url = state.source + '/' + path;
      $('#mail-frame').src = url;
      $('#mail-subject').textContent = (sec.email ? '' : '[리포트] ') + (sec.title || '') + ' — ' + (pm.period_label || '');
      $('#frame-note').textContent = (sec.email
        ? '실제로 발송되는 HTML 메일 본문입니다. 상세 리포트는 ZIP으로 첨부됩니다.'
        : '이 기간은 메일 원본 대신 대표 리포트를 보여 드립니다.') + ' ' +
        (state.source === 'demo' ? 'IP는 문서용 예시 대역(RFC 5737)입니다.' : 'IP는 10.20.x.x · 198.18.x.x로 치환했습니다.');
      lastFrameUrl = url;
      verdict(url, animate);
      $('#get-this').href = 'contact.html?src=' + state.source + '&kind=' + state.kind;  // 보던 조합 그대로 미리 선택

      // 상세 리포트: 위 탭(Windows/Linux)에 맞춰 목록을 보여 주고, 줄마다 설명 + 메일 본문의 핵심 수치
      var files = $('#files'); files.textContent = '';
      var reps = (sec.reports || []);
      reps.forEach(function (r, i) {
        var key = fileKey(r.href);
        var a = document.createElement('a');
        a.href = state.source + '/' + r.href; a.target = '_blank'; a.rel = 'noopener';
        a.innerHTML = '<span class="no">' + (i < 9 ? '0' : '') + (i + 1) + '</span>' +
          '<span class="f-main"><span class="t"></span><span class="d"></span></span>' +
          '<span class="f-stats" data-key="' + key + '"></span><span class="go" aria-hidden="true">↗</span>';
        $('.t', a).textContent = FILE_TITLE[key] || r.title;
        $('.d', a).textContent = FILE_DESC[key] || '';
        files.appendChild(a);
      });
      $('#files-note').textContent = KIND[state.kind] + ' ' + reps.length + '개';
    }

    // 상세 리포트 줄 설명 / 키 / 메일 본문에서 수치 뽑기
    var FILE_TITLE = { TOMCAT_EOUT: 'TOMCAT (E-OUT)', TOMCAT_INOUT: 'TOMCAT (IN-OUT)' };
    var FILE_DESC = {
      index: '플랫폼 전체 요약과 리포트 목차',
      NGINX: '상태코드·경로 키워드를 일별·IP별·URL별로 집계',
      TOMCAT_EOUT: 'Exception·커넥션 고갈을 시간대별로 묶음',
      TOMCAT_INOUT: '인증·외부 연동 실패를 분류하고 정상 401은 노이즈로',
      EBIZ: 'L4 편차와 WEB·WAS 노드별 트래픽·노이즈'
    };
    function fileKey(href) {
      var b = href.split('/').pop();
      if (/^index_/.test(b)) return 'index';
      var mm = /^Report_(.+?)_\d{4}W?\d+\.html$/.exec(b);
      return mm ? mm[1] : b;
    }
    function num(s) { return Number(String(s).replace(/,/g, '')) || 0; }
    function fmt(n) { return n.toLocaleString('en-US'); }
    function chip(v, label, cls) { return '<span class="f-stat' + (cls ? ' ' + cls : '') + '"><b>' + v + '</b>' + label + '</span>'; }
    function fillStats(html) {
      var t = html.replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ');
      var st = {}, sumMain = 0, sumNoise = 0, hasWin = false;
      ['NGINX', 'TOMCAT_EOUT', 'TOMCAT_INOUT'].forEach(function (k) {
        var mm = new RegExp('-\\s*' + k + ':\\s*주요\\s*([\\d,]+)건\\s*/\\s*노이즈\\s*([\\d,]+)건').exec(t);
        if (!mm) return;
        hasWin = true; sumMain += num(mm[1]); sumNoise += num(mm[2]);
        if (num(mm[1]) + num(mm[2]) === 0) {  // 둘 다 0이면 숫자 대신 '며칠 분석 · 이상 없음'
          var dd = new RegExp(k + '\\s*주요 탐지[^]*?분석 일수\\s*(\\d+)').exec(t);
          st[k] = (dd ? chip(dd[1] + '일', '분석') : '') + '<span class="f-stat is-ok"><i></i>이상 없음</span>';
        } else {
          st[k] = chip(mm[1], '주요') + chip(mm[2], '노이즈', 'is-noise');
        }
      });
      if (hasWin) st.index = chip(fmt(sumMain), '주요') + chip(fmt(sumNoise), '노이즈', 'is-noise');
      var l4 = /L4:[^\n]*?편차\s*([\d.]+%)/.exec(t), re = /-\s*(?:WEB|WAS)\d:\s*트래픽\s*[\d,]+\s*\/\s*노이즈\s*([\d,]+)건/g, mm2, ln = 0, any = false;
      while ((mm2 = re.exec(t))) { any = true; ln += num(mm2[1]); }
      if (l4 || any) st.EBIZ = (l4 ? chip(l4[1], 'L4 편차') : '') + (any ? chip(fmt(ln), '노이즈', 'is-noise') : '');
      $$('#files .f-stats').forEach(function (el) { el.innerHTML = st[el.dataset.key] || ''; });
    }

    var choose = function (ai, per) {  // 없는 조합이면 같은 AI 설정 안에서 있는 쪽으로
      var src = PICK[ai + ' ' + per];
      if (!src || !has(src)) src = ai === 'on' ? 'demo' : (has('live') ? 'live' : 'live-monthly');
      if (has(src)) { state.source = src; render(); }
    };
    segBtns.forEach(function (b) {
      b.addEventListener('click', function () { if (!b.disabled) choose(aiOf(state.source) ? 'on' : 'off', b.dataset.period); });
    });
    aiSw.addEventListener('change', function () { choose(aiSw.checked ? 'on' : 'off', periodOf(state.source)); });

    var q = /[?&]src=([\w-]+)/.exec(location.search);
    if (q && SOURCES.indexOf(q[1]) >= 0) state.source = q[1];

    Promise.all(SOURCES.map(function (src) {
      return fetch(src + '/manifest.json', { cache: 'no-cache' })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (m) { state.m[src] = m; })
        .catch(function () { if (state.source === src) state.source = 'demo'; });
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

    // AI 사용 = 데모(합성 로그 + AI 요약, 주간만) · AI 미사용 = 실제 운영 리포트(주간 · 월간)
    var radio = function (name, v) { return form.querySelector('input[name=' + name + '][value="' + v + '"]'); };
    var SOURCE = { 'on weekly': 'demo', 'off weekly': 'live', 'off monthly': 'live-monthly' };
    var missing = {};  // 아직 공개되지 않은 출처
    var aiSw = $('#mail-ai', form);
    var sourceOf = function () {
      return SOURCE[(aiSw.checked ? 'on' : 'off') + ' ' + new FormData(form).get('period')];
    };
    var q = /[?&]src=([\w-]+)/.exec(location.search);
    if (q) Object.keys(SOURCE).forEach(function (k) {
      if (SOURCE[k] === q[1]) { aiSw.checked = k.split(' ')[0] === 'on'; radio('period', k.split(' ')[1]).checked = true; }
    });
    var qk = /[?&]kind=(windows|linux)\b/.exec(location.search);
    if (qk) radio('kind', qk[1]).checked = true;
    // 라디오 그룹(리포트 · 플랫폼)에도 미끄러지는 알약
    var optThumbs = $$('.opts', form).map(function (box) {
      return slideThumb(box, 'label:has(input:checked)');
    });
    var periodNote = $('#period-note');
    var syncOpts = function () {
      aiSw.disabled = !!(missing.live && missing['live-monthly']);  // 실제 리포트가 없으면 AI 사용으로 고정
      if (aiSw.disabled) aiSw.checked = true;
      var aiOn = aiSw.checked;
      var w = radio('period', 'weekly'), mo = radio('period', 'monthly');
      w.disabled = !aiOn && !!missing.live;
      mo.disabled = aiOn || !!missing['live-monthly'];
      if (mo.disabled && mo.checked) w.checked = true;
      if (w.disabled && w.checked) mo.checked = true;
      periodNote.textContent = aiOn
        ? '데모 로그로 만든 주간 리포트에 AI 요약이 함께 담겨요.'
        : '실제 운영 리포트를 공개용으로 마스킹한 사본이에요.';
      optThumbs.forEach(function (up) { up(); });
    };
    form.addEventListener('change', syncOpts);
    syncOpts();

    // 공개되지 않은 출처는 고를 수 없게
    ['live', 'live-monthly'].forEach(function (src) {
      fetch(src + '/manifest.json', { method: 'HEAD', cache: 'no-cache' }).then(function (r) {
        if (!r.ok) { missing[src] = true; syncOpts(); }
      }).catch(function () {});
    });

    // 배포 액세스 확인: 익명 호출이 되면 페이지 안에서(inline), 막혀 있으면 새 탭(tab)
    fetch(MAIL_ENDPOINT, { method: 'POST', body: JSON.stringify({ probe: true }) })
      .then(function (r) { return r.json(); })
      .then(function (res) { mode = res && res.ok ? 'inline' : 'tab'; })
      .catch(function () { mode = 'tab'; });

    // 이메일 칸에는 아이디만: '@'부터 뒤는 지움 (전체 주소를 붙여 넣어도 아이디만 남음)
    // 입력 칸 폭을 글자에 맞춰 늘려서 @vntgcorp.com이 바로 뒤에 붙어 따라오게
    var mailTo = $('#mail-to', form), mailField = mailTo.parentNode, sizer = $('.mail-sizer', mailField);
    var fitMail = function () {
      sizer.textContent = mailTo.value || mailTo.placeholder;
      mailTo.style.width = Math.ceil(sizer.getBoundingClientRect().width) + 2 + 'px';
    };
    mailTo.addEventListener('input', function () {
      var at = mailTo.value.indexOf('@');
      if (at >= 0) mailTo.value = mailTo.value.slice(0, at);
      fitMail();
    });
    mailField.addEventListener('click', function (e) { if (e.target !== mailTo) mailTo.focus(); });
    window.addEventListener('resize', fitMail);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitMail);
    fitMail();

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var fd = new FormData(form);
      var id = String(fd.get('relog_to') || '').trim().toLowerCase();
      if (!/^[a-z0-9._%+-]+$/.test(id)) return say('이메일 아이디를 확인해 주세요.', 'err');
      var to = id + '@' + ALLOWED_DOMAIN;
      var payload = { email: to, source: sourceOf() || 'demo', kind: fd.get('kind'), website: fd.get('website') || '' };

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
