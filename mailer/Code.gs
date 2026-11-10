/**
 * "메일로 받아보기" 발송 서버 (Google Apps Script 웹 앱)
 *
 * GitHub Pages(정적)에서 { email, source, kind } 를 POST 하면,
 * Pages에 올라가 있는 <source>/manifest.json 을 읽어 그 리포트 메일 HTML을 그대로 보내고
 * 상세 리포트는 ZIP으로 첨부한다 — 실제 운영 메일과 같은 형태.
 *
 * 공개 페이지에 붙는 발송기라 남용 방지가 필수:
 *  - ALLOWED_DOMAINS 의 사내 주소로만 발송 (외부 주소 스팸 발송기로 악용 불가)
 *  - 주소별 / 전체 발송 횟수 제한 (6시간 창, CacheService)
 *  - 허니팟 필드(website)가 채워진 요청은 조용히 무시
 *  - 요청자가 고를 수 있는 건 source(demo|live)·kind(windows|linux) 뿐.
 *    본문·첨부는 이 스크립트에 고정된 PAGES_BASE 아래에서만 가져온다 (임의 URL 불가)
 *  - 발송 기록에 이메일 원문을 남기지 않음 (캐시 키는 해시)
 */
var PAGES_BASE = 'https://silverain1004.github.io/relog/';
var ALLOWED_DOMAINS = ['vntgcorp.com'];
var LIMIT_PER_ADDRESS = 3;   // 6시간당 주소별
var LIMIT_TOTAL = 100;       // 6시간당 전체
var WINDOW_SEC = 21600;      // CacheService 최대 보관 시간(6시간)
var LIVE_NOTE = '실제 운영 리포트이며, IP·도메인·계정 등 식별 정보는 마스킹되어 있습니다.';
var SOURCES = {
  demo: '합성 로그로 만든 데모 리포트입니다.',
  live: LIVE_NOTE,
  'live-monthly': LIVE_NOTE
};
var KINDS = ['windows', 'linux'];

function doPost(e) {
  // 두 가지 호출 방식을 모두 받는다.
  //  1) fetch(text/plain JSON)  — 배포 액세스가 '모든 사용자'일 때 페이지 안에서 바로 발송
  //  2) 폼 POST(새 탭)          — 액세스가 '도메인 내 사용자'로 제한된 경우. 새 탭에는 회사 구글 로그인이 실림
  var isForm = !!(e && e.parameter && e.parameter.email);
  var req;
  if (isForm) {
    req = e.parameter;
  } else {
    try {
      req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    } catch (err) {
      return reply_(false, '요청 형식이 올바르지 않아요.');
    }
  }
  var res = handle_(req);
  return isForm ? page_(res.ok, res.message) : reply_(res.ok, res.message);
}

function handle_(req) {
  if (req.probe) return result_(true, 'ok'); // 페이지가 배포 액세스 방식을 확인하는 요청 (발송 없음)
  if (req.website) return result_(true, '발송했어요.'); // 허니팟: 봇에게는 성공처럼 보이게

  var email = String(req.email || '').trim().toLowerCase();
  var source = SOURCES.hasOwnProperty(req.source) ? req.source : 'demo';
  var kind = KINDS.indexOf(req.kind) >= 0 ? req.kind : 'windows';
  if (email.length > 100 || !/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/.test(email)) {
    return result_(false, '이메일 주소를 확인해 주세요.');
  }
  var domain = email.split('@')[1];
  if (ALLOWED_DOMAINS.length && ALLOWED_DOMAINS.indexOf(domain) < 0) {
    return result_(false, '사내 메일(@' + ALLOWED_DOMAINS.join(', @') + ')로만 받을 수 있어요.');
  }

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return result_(false, '잠시 후 다시 시도해 주세요.');
  try {
    var cache = CacheService.getScriptCache();
    var addrKey = 'a:' + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, email));
    var mine = Number(cache.get(addrKey) || 0);
    var total = Number(cache.get('total') || 0);
    if (mine >= LIMIT_PER_ADDRESS) return result_(false, '이 주소로는 이미 여러 번 보냈어요. 몇 시간 뒤에 다시 시도해 주세요.');
    if (total >= LIMIT_TOTAL) return result_(false, '발송 한도를 넘었어요. 나중에 다시 시도해 주세요.');

    sendReport_(email, source, kind);

    cache.put(addrKey, String(mine + 1), WINDOW_SEC);
    cache.put('total', String(total + 1), WINDOW_SEC);
  } catch (err) {
    console.error(err);
    return result_(false, err.userMessage || '발송 중 오류가 났어요. 잠시 후 다시 시도해 주세요.');
  } finally {
    lock.releaseLock();
  }
  return result_(true, email + ' 로 보냈어요. 1~2분 안에 도착해요.');
}

function sendReport_(to, source, kind) {
  var base = PAGES_BASE + source + '/';
  var manifest = JSON.parse(fetch_(base + 'manifest.json').getContentText('UTF-8'));
  var report = manifest[kind];
  var bodyPath = report && (report.email || (report.reports && report.reports.length && report.reports[0].href));
  if (!bodyPath) {
    var err = new Error('no report');
    err.userMessage = '이 리포트는 아직 준비 중이에요.';
    throw err;
  }

  var periodLabel = report.period_label || manifest.period_label;  // Windows·Linux 주차가 다를 수 있어 탭 값 우선
  var banner = '<div style="background:#fff7e6;border-bottom:1px solid #f0d9a8;padding:10px 16px;' +
    'font-size:13px;color:#7a5200;font-family:Segoe UI,Arial,sans-serif">' +
    'AIVE 출품작 「Re.log」에서 보낸 메일입니다. ' + SOURCES[source] + ' ' +
    '<a href="' + PAGES_BASE + '" style="color:#7a5200">데모 페이지</a></div>';
  // 메일 원본이 있으면 그대로, 없으면(상세 리포트만 공개된 기간) 메일에서 깨지지 않는 표지를 본문으로.
  // 상세 리포트 HTML은 브라우저용 CSS라 Gmail에 그대로 넣으면 레이아웃이 깨진다.
  var html = report.email
    ? fetch_(base + report.email).getContentText('UTF-8').replace(/(<body[^>]*>)/i, '$1' + banner)
    : cover_(report, base, source, periodLabel, banner);

  var files = (report.reports || []).map(function (r) {
    return fetch_(base + r.href).getBlob().setName(r.href.split('/').pop());
  });
  var attachments = files.length ? [Utilities.zip(files, report.zip || 'reports.zip')] : [];

  MailApp.sendEmail({
    to: to,
    subject: '[로그리포트 ' + (source === 'demo' ? 'Demo' : 'Real') + '] ' + report.title +
      (periodLabel ? ' — ' + periodLabel : ''),
    htmlBody: html,
    body: '로그 리포트입니다. HTML 메일을 지원하는 메일 앱에서 확인해 주세요. ' + PAGES_BASE,
    attachments: attachments,
    name: 'Re.log'
  });
}

// 메일 원본이 없는 리포트용 표지: 인라인 스타일·표 레이아웃만 써서 Gmail·Outlook에서도 그대로 보이게
function cover_(report, base, source, periodLabel, banner) {
  var esc = function (s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
  var font = "font-family:'Malgun Gothic','Apple SD Gothic Neo',Segoe UI,Arial,sans-serif;";
  var rows = (report.reports || []).map(function (r) {
    return '<tr><td style="padding:12px 0;border-bottom:1px solid #e5e7eb;' + font + 'font-size:14px;color:#111827">' + esc(r.title) + '</td>' +
      '<td align="right" style="padding:12px 0;border-bottom:1px solid #e5e7eb;' + font + 'font-size:13px">' +
      '<a href="' + base + r.href + '" style="color:#D81B50;text-decoration:none">브라우저에서 보기 →</a></td></tr>';
  }).join('');
  return '<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;background:#f4f3ef">' + banner +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f3ef"><tr><td align="center" style="padding:28px 16px">' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px">' +
    '<tr><td style="padding:28px 28px 8px;' + font + '">' +
      '<div style="font-size:12px;letter-spacing:.08em;color:#6b7280">RE.LOG · ' + (source === 'demo' ? 'DEMO' : 'REAL') + '</div>' +
      '<div style="margin-top:8px;font-size:20px;font-weight:700;color:#111827">' + esc(report.title) + '</div>' +
      '<div style="margin-top:6px;font-size:14px;color:#4b5563">' + esc(periodLabel) + '</div>' +
    '</td></tr>' +
    '<tr><td style="padding:16px 28px 4px;' + font + 'font-size:14px;line-height:1.7;color:#374151">' +
      '이 기간은 실제로 받은 메일 본문 대신 상세 리포트를 보내 드립니다. 아래 목록을 브라우저에서 열거나, 첨부한 ZIP(' + esc(report.zip || 'reports.zip') + ')을 내려받아 확인해 주세요.' +
    '</td></tr>' +
    '<tr><td style="padding:8px 28px 12px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + rows + '</table></td></tr>' +
    '<tr><td style="padding:12px 28px 28px;' + font + 'font-size:13px">' +
      '<a href="' + PAGES_BASE + 'report.html?src=' + source + '" style="color:#D81B50;text-decoration:none">Re.log 리포트 뷰어에서 보기 →</a>' +
    '</td></tr></table></td></tr></table></body></html>';
}

function fetch_(url) {
  var res = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    var err = new Error(url + ' -> ' + res.getResponseCode());
    err.userMessage = '리포트를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.';
    throw err;
  }
  return res;
}

function result_(ok, message) {
  return { ok: ok, message: message };
}

function page_(ok, message) {
  var color = ok ? '#1e8e5a' : '#d64545';
  var html = '<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>메일로 받아보기</title></head>' +
    '<body style="margin:0;font-family:Segoe UI,Malgun Gothic,Arial,sans-serif;background:#f6f7f9;color:#1d2330">' +
    '<div style="max-width:440px;margin:80px auto;padding:24px;background:#fff;border:1px solid #e2e6ec;border-radius:14px">' +
    '<div style="font-size:18px;font-weight:700;margin-bottom:8px">Re.log</div>' +
    '<div style="font-size:15px;color:' + color + '">' + escape_(message) + '</div>' +
    '<div style="margin-top:18px;font-size:13px"><a href="' + PAGES_BASE + '">← 데모 페이지로 돌아가기</a> · 이 탭은 닫아도 돼요.</div>' +
    '</div></body></html>';
  return HtmlService.createHtmlOutput(html).setTitle('메일로 받아보기');
}

function escape_(t) {
  return String(t).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function reply_(ok, message) {
  return ContentService.createTextOutput(JSON.stringify({ ok: ok, message: message }))
    .setMimeType(ContentService.MimeType.JSON);
}

/** 배포 전 편집기에서 한 번 실행: 권한 승인 + 본인에게 테스트 발송 */
function testSendToMe() {
  sendReport_(Session.getActiveUser().getEmail(), 'demo', 'windows');
}

// 편집기에서 실행: 내 주소의 발송 횟수(6시간 3통)와 전체 카운트를 초기화 — 테스트용
function resetMyLimit() {
  var email = Session.getActiveUser().getEmail().toLowerCase();
  var key = 'a:' + Utilities.base64EncodeWebSafe(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, email));
  CacheService.getScriptCache().removeAll([key, 'total']);
  console.log('초기화 완료: ' + email);
}
