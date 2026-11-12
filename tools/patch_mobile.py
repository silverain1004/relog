"""이미 만들어진 리포트 HTML에 폰 화면 보정 CSS를 끼워 넣는다.

새로 생성하는 리포트는 report_builder가 알아서 넣으므로, 이 스크립트는
docs/live* 처럼 예전에 만들어 둔 리포트를 다시 생성하지 않고 고칠 때만 쓴다.
같은 파일에 여러 번 돌려도 한 번만 들어간다.

    python tools/patch_mobile.py docs/live docs/live-monthly docs/demo
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from report_builder import MOBILE_MARK, MOBILE_STYLES  # noqa: E402


def patch_file(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if MOBILE_MARK in text or "</style>" not in text:
        return False
    # 예전 버전 블록이 있으면 (마커 ~ </style>) 걷어내고 새 버전으로 교체
    old = text.find("\n/* relog-mobile v")
    if old != -1:
        text = text[:old] + text[text.index("</style>", old):]
    text = text.replace("</style>", MOBILE_STYLES + "</style>", 1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return True


def main(roots: list) -> None:
    changed = 0
    for root in roots:
        for dirpath, _, files in os.walk(root):
            for name in files:
                # 리포트만 (docs/live/email 의 메일 본문은 웹메일용이라 건드리지 않음)
                if name.endswith(".html") and "reports" in dirpath.replace("\\", "/").split("/"):
                    path = os.path.join(dirpath, name)
                    if patch_file(path):
                        changed += 1
                        print("patched", path)
    print(f"{changed}개 파일 수정")


if __name__ == "__main__":
    main(sys.argv[1:] or ["docs/live", "docs/live-monthly", "docs/demo"])
