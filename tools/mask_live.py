"""실제 운영 리포트를 마스킹해서 docs/live/ 로 내보낸다.

    python tools/mask_live.py <원본 폴더> [--deny 단어 ...]

원본 폴더 구조 (repo 밖에 둘 것 — 원본은 절대 커밋하지 않는다):
    <원본>/*.zip   리포트 메일 첨부 ZIP (Report_Windows_*.zip, Report_Linux_*.zip)
    <원본>/*.eml   Gmail에서 '원본 다운로드'한 리포트 메일 — 본문과 첨부 ZIP을 알아서 풀어 아래 구조로 만든다
또는 직접:
    <원본>/windows/index_*.html, Report_*.html     Windows 서버 reports/weekly
    <원본>/linux/Report_EBIZ_*.html                 Linux WEB1 reports/weekly
    <원본>/email/windows.(html|eml), linux.(html|eml)   (선택) 실제로 받은 메일

마스킹 규칙 — 수치·차트·패턴은 그대로, 식별 정보만 일관되게 치환:
    IPv4      사설 → 10.20.x.y / 공인 → 198.18.x.y (RFC 2544 벤치마크 대역). 같은 IP는 항상 같은 값
    도메인     허용 목록 외 → <첫 라벨>.customer-N.example
    이메일     userN@example.com
    금칙어     고객사·회사·계정명 등 (tools/mask_words.txt + --deny, 파일은 git 제외)
    URL 값     쿼리 파라미터 값, JWT, 긴 토큰, 5자리 이상 숫자 ID
    경로       C:\\Users\\<이름>, /home/<이름>

치환 후 결과 전체를 다시 검사해서 하나라도 남아 있으면 아무것도 쓰지 않고 실패한다.
원본→치환 대응표는 <원본>/mask_map.txt 에만 남는다 (repo 밖).
"""
import argparse
import email
import email.policy
import glob
import io
import ipaddress
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "live")

WORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mask_words.txt")


def load_words(path=WORDS_FILE):
    """고객사·회사·계정명 같은 현장별 금칙어. 공개 레포에 올리지 않도록 별도 파일(git 제외)에 둔다.

    한 줄에 하나, `정규식<TAB>치환어` (치환어를 생략하면 masked). # 으로 시작하면 주석.
    """
    words = []
    if not os.path.exists(path):
        return words
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            pat, _, rep = line.partition("	")
            words.append((pat.strip(), rep.strip() or "masked"))
    return words


DENY_WORDS = load_words()
DOMAIN_ALLOW = (
    "example.com", "example.org", "example.net", "w3.org", "google.com", "googleapis.com",
    "anthropic.com", "github.io", "github.com", "apache.org", "zaxxer.com",
)
SAFE_IP_NETS = [ipaddress.ip_network(n) for n in (
    "10.20.0.0/16", "198.18.0.0/15", "127.0.0.0/8", "0.0.0.0/32",
)]

IPV4_RE = re.compile(r"(?<![\d.])((?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3})(?![\d.])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DOMAIN_RE = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:co\.kr|or\.kr|go\.kr|ac\.kr|ne\.kr|kr|com|net|org|io|cloud|biz|info|dev|app|internal|local|corp))\b",
    re.I)
QUERY_RE = re.compile(r"([?&;](?:amp;)?[A-Za-z0-9_.\-\[\]]+=)([^&\s\"'<>;]+)")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9/._-])(?=[A-Za-z0-9+_-]*\d)(?=[A-Za-z0-9+_-]*[A-Za-z])[A-Za-z0-9+_-]{32,}={0,2}(?![A-Za-z0-9/.])")
PATH_ID_RE = re.compile(r"(/)(\d{5,})(?=[/?\s\"'<&]|$)")
WIN_USER_RE = re.compile(r"([A-Za-z]:\\\\?Users\\\\?)([^\\\s\"'<]+)", re.I)
HOME_RE = re.compile(r"(/home/)([^/\s\"'<]+)")


class Masker:
    def __init__(self, deny_extra, words=None):
        self.words = DENY_WORDS if words is None else words
        self.deny = [(re.compile(p, re.I), r) for p, r in self.words]
        self.deny += [(re.compile(re.escape(w), re.I), "masked") for w in deny_extra]
        self.ip_map, self.dom_map, self.org_map, self.mail_map = {}, {}, {}, {}
        self.n_private = self.n_public = 0
        self.stats = Counter()

    # --- 개별 규칙
    def _ip(self, m):
        raw = m.group(1)
        ip = ipaddress.ip_address(raw)
        if raw in ("127.0.0.1", "0.0.0.0") or any(ip in n for n in SAFE_IP_NETS[:2]):
            return raw
        if raw not in self.ip_map:
            if ip.is_private:
                n = self.n_private = self.n_private + 1
                self.ip_map[raw] = "10.20.%d.%d" % (n // 254, n % 254 + 1)
            else:
                n = self.n_public = self.n_public + 1
                self.ip_map[raw] = "198.%d.%d.%d" % (18 + n // 65024, (n // 254) % 256, n % 254 + 1)
        self.stats["ip"] += 1
        return self.ip_map[raw]

    def _email(self, m):
        raw = m.group(0).lower()
        if raw.endswith("@example.com"):
            return raw
        self.mail_map.setdefault(raw, "user%d@example.com" % (len(self.mail_map) + 1))
        self.stats["email"] += 1
        return self.mail_map[raw]

    def _domain(self, m):
        raw = m.group(1)
        low = raw.lower()
        if low.endswith(".example") or any(low == a or low.endswith("." + a) for a in DOMAIN_ALLOW):
            return raw
        labels = low.split(".")
        org = ".".join(labels[-3:] if len(labels) >= 3 and labels[-2] in ("co", "or", "go", "ac", "ne") else labels[-2:])
        self.org_map.setdefault(org, "customer-%d.example" % (len(self.org_map) + 1))
        sub = low[: -len(org)].rstrip(".")
        first = sub.split(".")[0] if sub else ""
        masked = (first + "." if first else "") + self.org_map[org]
        self.dom_map[raw] = masked
        self.stats["domain"] += 1
        return masked

    def _query(self, m):
        val = m.group(2)
        if val.isdigit() and len(val) <= 3:
            return m.group(0)
        self.stats["query"] += 1
        return m.group(1) + "***"

    def mask(self, text):
        text = EMAIL_RE.sub(self._email, text)
        text = JWT_RE.sub(lambda m: self._count("token", "&lt;jwt&gt;"), text)
        text = QUERY_RE.sub(self._query, text)
        text = TOKEN_RE.sub(lambda m: self._count("token", "&lt;token&gt;"), text)
        text = DOMAIN_RE.sub(self._domain, text)
        text = IPV4_RE.sub(self._ip, text)
        text = PATH_ID_RE.sub(lambda m: self._count("path_id", m.group(1) + "{id}"), text)
        text = WIN_USER_RE.sub(lambda m: self._count("path_user", m.group(1) + "user"), text)
        text = HOME_RE.sub(lambda m: self._count("path_user", m.group(1) + "appuser"), text)
        for rx, rep in self.deny:
            text, n = rx.subn(rep, text)
            self.stats["deny"] += n
        return text

    def _count(self, key, rep):
        self.stats[key] += 1
        return rep


def leaks(text, deny_extra, words=None):
    """마스킹 결과에 남은 식별 정보 목록. 비어 있어야 통과."""
    found = []
    for m in IPV4_RE.finditer(text):
        ip = ipaddress.ip_address(m.group(1))
        if not any(ip in n for n in SAFE_IP_NETS):
            found.append(("ip", m.group(1)))
    for m in EMAIL_RE.finditer(text):
        if not m.group(0).lower().endswith("@example.com"):
            found.append(("email", m.group(0)))
    for m in DOMAIN_RE.finditer(text):
        low = m.group(1).lower()
        if not (low.endswith(".example") or any(low == a or low.endswith("." + a) for a in DOMAIN_ALLOW)):
            found.append(("domain", m.group(1)))
    for p, _ in (DENY_WORDS if words is None else words):
        for m in re.finditer(p, text, re.I):
            found.append(("deny", m.group(0)))
    for w in deny_extra:
        if w.lower() in text.lower():
            found.append(("deny", w))
    for m in JWT_RE.finditer(text):
        found.append(("jwt", m.group(0)[:20]))
    return found


def read_email_html(path):
    if path.endswith(".eml"):
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)
        part = msg.get_body(preferencelist=("html",))
        if part is None:
            raise RuntimeError("%s 에 HTML 본문이 없습니다." % path)
        return part.get_content()
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_eml(src):
    """<원본>/*.eml (Gmail '원본 다운로드') → 본문은 email/<kind>.html, 첨부 ZIP 속 HTML은 <kind>/ 로 풀어 둔다."""
    for path in sorted(glob.glob(os.path.join(src, "*.eml"))):
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)
        subject = str(msg.get("subject", ""))
        kind = "linux" if "linux" in subject.lower() else "windows" if "windows" in subject.lower() else None
        if kind is None:
            print("   [건너뜀] 제목으로 Windows/Linux를 알 수 없음: %s" % os.path.basename(path))
            continue
        body = msg.get_body(preferencelist=("html",))
        if body is not None:
            os.makedirs(os.path.join(src, "email"), exist_ok=True)
            with open(os.path.join(src, "email", kind + ".html"), "w", encoding="utf-8") as f:
                f.write(body.get_content())
        for part in msg.iter_attachments():
            name = part.get_filename() or ""
            if not name.lower().endswith(".zip"):
                continue
            with zipfile.ZipFile(io.BytesIO(part.get_payload(decode=True))) as zf:
                for info in zf.infolist():
                    base = os.path.basename(info.filename)
                    if base.lower().endswith(".html"):
                        os.makedirs(os.path.join(src, kind), exist_ok=True)
                        with open(os.path.join(src, kind, base), "wb") as f:
                            f.write(zf.read(info))
        print("   [eml] %s → %s" % (os.path.basename(path), kind))


def extract_zip(src):
    """<원본>/*.zip (리포트 메일 첨부: Report_Windows_*.zip, Report_Linux_*.zip) → <kind>/ 로 풀어 둔다."""
    for path in sorted(glob.glob(os.path.join(src, "*.zip"))):
        low = os.path.basename(path).lower()
        kind = "linux" if "linux" in low or "ebiz" in low else "windows" if "win" in low else None
        if kind is None:
            print("   [건너뜀] 파일명으로 Windows/Linux를 알 수 없음: %s" % os.path.basename(path))
            continue
        os.makedirs(os.path.join(src, kind), exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                base = os.path.basename(info.filename)
                if base.lower().endswith(".html"):
                    with open(os.path.join(src, kind, base), "wb") as f:
                        f.write(zf.read(info))
        print("   [zip] %s → %s" % (os.path.basename(path), kind))


LOG_TBODY_RE = re.compile(r'(<table class="log-table"[^>]*>.*?<tbody>)(.*?)(</tbody>)', re.S)
ROW_RE = re.compile(r"<tr[\s>].*?</tr>", re.S)


def trim_log_rows(text, max_rows):
    """상세 로그 표를 기간 전체에서 고르게 max_rows 줄만 남긴다. 집계·차트·Top N 은 그대로."""
    def _trim(m):
        rows = ROW_RE.findall(m.group(2))
        if len(rows) <= max_rows:
            return m.group(0)
        step = len(rows) / float(max_rows)
        kept = [rows[int(i * step)] for i in range(max_rows)]
        note = ("<tr><td colspan='7' style='text-align:center;color:#888'>공개본: 전체 %s건 중 기간 전체에서 고르게 %d건만 표시 "
                "(집계·차트·Top N은 전체 기준)</td></tr>" % (format(len(rows), ","), max_rows))
        return m.group(1) + note + "".join(kept) + m.group(3)
    return LOG_TBODY_RE.sub(_trim, text)


def collect(src):
    """(원본 경로, docs/live 상대 경로) 목록"""
    extract_zip(src)
    extract_eml(src)
    items = []
    for kind in ("windows", "linux"):
        for p in sorted(glob.glob(os.path.join(src, kind, "*.html"))):
            items.append((p, "reports/%s/%s" % (kind, os.path.basename(p))))
    for kind in ("windows", "linux"):
        for ext in ("html", "eml"):
            p = os.path.join(src, "email", "%s.%s" % (kind, ext))
            if os.path.exists(p):
                items.append((p, "email/%s.html" % kind))
                break
    return items


def build_manifest(outputs, texts):
    def reports_of(kind):
        return sorted((o for o in outputs if o.startswith("reports/%s/" % kind)),
                      key=lambda o: (0 if "/index_" in o else 1, o))
    win_reports, lin_reports = reports_of("windows"), reports_of("linux")

    def period_key(paths):
        keys = re.findall(r"_(\d{4}(?:W\d{2}|\d{2}))\.html", " ".join(paths))
        return max(keys) if keys else ""
    label = ""
    for t in texts.values():
        m = re.search(r"\d{4}년 \d+(?:주|월) \([^)]*\)", t)
        if m:
            label = m.group(0)
            break

    def title(href):
        name = os.path.basename(href)
        if name.startswith("index_"):
            return ("Linux" if "/linux/" in href else "Windows") + " 목차"
        if "EBIZ" in name:
            return "Linux 통합 (L4·노드별)"
        return re.sub(r"^Report_|_\d{4}W?\d+\.html$", "", name)

    def ai(kind):
        t = texts.get("email/%s.html" % kind, "")
        return "claude" if "AI 요약 (Claude)" in t else ("none" if t else "missing")

    def label_of(rels):
        for rel in rels:
            m = re.search(r"\d{4}년 \d+(?:주|월) \([^)]*\)", texts.get(rel, ""))
            if m:
                return m.group(0)
        return label

    def section(kind, reports, title_text, zipprefix):
        email_rel = "email/%s.html" % kind
        if not reports and email_rel not in outputs:
            return None
        # Windows·Linux 원본 주차가 다를 수 있어 탭마다 기간을 따로 둔다 (뷰어는 이 값을 우선 사용)
        return {
            "title": title_text,
            "period_label": label_of(reports + [email_rel]),
            "period_key": period_key(reports),
            "email": email_rel if email_rel in outputs else None,
            "zip": "%s_%s.zip" % (zipprefix, period_key(reports)),
            "reports": [{"title": title(h), "href": h} for h in reports],
        }

    return {
        "source": "live",
        "label": "실제 운영 (마스킹)",
        "period_label": label,
        "period_key": period_key(outputs),
        "ai_source": {"windows": ai("windows"), "linux": ai("linux")},
        "windows": section("windows", win_reports, "E-OUT, IN-OUT 시스템 통합 로그 리포트 (Windows)", "Report_WIN"),
        "linux": section("linux", lin_reports, "E-BIZ 시스템 통합 로그 리포트 (Linux)", "Report_EBIZ"),
    }


def main():
    ap = argparse.ArgumentParser(description="실제 운영 리포트 마스킹 → docs/live/")
    ap.add_argument("src", help="원본 리포트 폴더 (repo 밖)")
    ap.add_argument("--deny", nargs="*", default=[], help="추가로 가릴 단어 (사람 이름, 서버 호스트명 등)")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--max-log-rows", type=int, default=300, help="상세 로그 표에 남길 최대 줄 수 (기본 300)")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if src.startswith(ROOT + os.sep):
        sys.exit("[중단] 원본 폴더가 repo 안에 있습니다. repo 밖으로 옮겨 주세요: " + src)
    items = collect(src)
    if not items:
        sys.exit("[중단] 원본 폴더에서 리포트를 찾지 못했습니다. 구조는 --help 참고.")

    if not DENY_WORDS:
        print("[주의] tools/mask_words.txt 가 없어 고객사·계정명 금칙어 없이 진행합니다. "
              "tools/mask_words.example.txt 를 복사해 채워 두세요.")
    masker = Masker(args.deny)
    texts, problems = {}, []
    for path, rel in items:
        raw = read_email_html(path) if rel.startswith("email/") else open(path, encoding="utf-8", errors="replace").read()
        masked = masker.mask(trim_log_rows(raw, args.max_log_rows))
        texts[rel] = masked
        for kind, val in leaks(masked, args.deny):
            problems.append((rel, kind, val))

    with open(os.path.join(src, "mask_map.txt"), "w", encoding="utf-8") as f:
        for title, mp in (("IP", masker.ip_map), ("도메인", masker.dom_map), ("이메일", masker.mail_map)):
            f.write("## %s (%d)\n" % (title, len(mp)))
            f.writelines("%s -> %s\n" % kv for kv in sorted(mp.items()))

    if problems:
        print("[실패] 마스킹 후에도 남은 항목이 있어 아무것도 쓰지 않았습니다:")
        for rel, kind, val in sorted(set(problems))[:50]:
            print("   %-40s %-7s %s" % (rel, kind, val))
        return 1

    if os.path.exists(args.out):
        shutil.rmtree(args.out)
    for rel, text in texts.items():
        dst = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
    manifest = build_manifest(list(texts), texts)
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("[완료] %d개 파일 → %s" % (len(texts), args.out))
    print("   치환 건수:", dict(masker.stats))
    print("   고유 IP %d개 / 도메인 %d개 / 이메일 %d개 — 대응표: %s" % (
        len(masker.ip_map), len(masker.dom_map), len(masker.mail_map), os.path.join(src, "mask_map.txt")))
    print("   ※ 사람 이름·서버 호스트명처럼 패턴으로 못 잡는 건 --deny 로 추가하고, 결과를 한 번 눈으로 확인하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
