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

  var html = fetch_(base + bodyPath).getContentText('UTF-8');  // 메일 원본이 없으면 대표 리포트를 본문으로
  var banner = '<div style="background:#fff7e6;border-bottom:1px solid #f0d9a8;padding:10px 16px;' +
    'font-size:13px;color:#7a5200;font-family:Segoe UI,Arial,sans-serif">' +
    'AIVE 출품작 「Re.log」에서 보낸 메일입니다. ' + SOURCES[source] + ' ' +
    '<a href="' + PAGES_BASE + '" style="color:#7a5200">데모 페이지</a></div>';
  html = html.replace(/(<body[^>]*>)/i, '$1' + banner);

  var files = (report.reports || []).map(function (r) {
    return fetch_(base + r.href).getBlob().setName(r.href.split('/').pop());
  });
  var attachments = files.length ? [Utilities.zip(files, report.zip || 'reports.zip')] : [];

  MailApp.sendEmail({
    to: to,
    subject: '[로그리포트 ' + (source === 'demo' ? '데모' : '실제') + '] ' + report.title +
      (manifest.period_label ? ' — ' + manifest.period_label : ''),
    htmlBody: html,
    body: '로그 리포트입니다. HTML 메일을 지원하는 메일 앱에서 확인해 주세요. ' + PAGES_BASE,
    attachments: attachments,
    name: 'Re.log'
  });
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
