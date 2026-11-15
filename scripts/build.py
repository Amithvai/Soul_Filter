#!/usr/bin/env python3
"""Soul Filter builder — per-sumber, independen, format ABP."""

import datetime
import pathlib
import time
import urllib.request
from urllib.parse import urlsplit

OUTPUT = pathlib.Path("output")

# (nama file output, judul, URL sumber)
SOURCES = [
    ("soul-oisd-small.txt", "oisd small",
     "https://abp.oisd.nl/basic/"),
    ("soul-oisd-big.txt", "oisd big",
     "https://abp.oisd.nl/"),
    ("soul-abpindo.txt", "ABPindo",
     "https://raw.githubusercontent.com/ABPindo/indonesianadblockrules/master/subscriptions/abpindo.txt"),
]

# oisd menolak User-Agent bot (404/503) → pakai UA browser
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# abp.oisd.nl rate-limit ketat: butuh jeda >= ~60 dtk antar-request host yang sama
HOST_COOLDOWN = 65.0
_last_request: dict[str, float] = {}


def _respect_cooldown(url: str) -> None:
    host = urlsplit(url).netloc
    last = _last_request.get(host)
    if last is not None:
        wait = HOST_COOLDOWN - (time.monotonic() - last)
        if wait > 0:
            print(f"    cooldown {host}: tunggu {wait:.0f}s")
            time.sleep(wait)
    _last_request[host] = time.monotonic()


def fetch(url: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            _respect_cooldown(url)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8", "replace")
            # oisd balas 503 berupa teks "Service Unavailable" (bukan status error)
            if body.lstrip().startswith("Error: Service Unavailable"):
                raise RuntimeError("upstream kirim 'Service Unavailable'")
            return body
        except Exception as exc:  # noqa: BLE001
            print(f"    attempt {attempt}/{retries} gagal: {exc}")
            if attempt < retries:
                time.sleep(HOST_COOLDOWN)
    return None


def valid_rule(line: str) -> bool:
    """Baris rule ABP yang valid; buang komentar/metadata/header.

    Soul tidak mendukung scriptlet (##+js) & CSS injection (#$#) — dibuang
    supaya file lebih kecil.
    """
    if not line:
        return False
    if line.startswith("!") or line.startswith("[Adblock"):
        return False
    if line.startswith("# "):  # komentar gaya "# text"
        return False
    if line.startswith("##") and "+js(" in line:
        return False  # scriptlet injection — tidak didukung Soul
    if line.startswith(("#$#", "##^")):
        return False  # CSS injection / uBO-specific — tidak didukung Soul
    return True


def count_rules(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if valid_rule(line.strip())
    )


def build_one(fname: str, title: str, url: str) -> None:
    print(f"[{title}] downloading {url}")
    text = fetch(url)
    if text is None:
        print(f"[{title}] GAGAL download — output lama dipertahankan")
        return

    rules: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not valid_rule(line) or line in seen:
            continue
        seen.add(line)
        rules.append(line)

    out = OUTPUT / fname
    old = count_rules(out)

    # Sanity check: rule turun > 15% = kemungkinan upstream rusak → jangan update
    if old and len(rules) < old * 0.85:
        print(f"[{title}] WARN: rule {old} -> {len(rules)} (turun >15%) — skip")
        return

    if old == len(rules):
        print(f"[{title}] jumlah rule sama ({len(rules)}) — cek isi tetap jalan")
    else:
        print(f"[{title}] {old} -> {len(rules)} rule")

    header = "\n".join(
        [
            "[Adblock Plus 2.0]",
            f"! Title: Soul Filter — {title}",
            f"! Last modified: {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M UTC}",
            f"! Source: {url}",
            f"! Rules: {len(rules)}",
            "",
        ]
    )
    out.write_text(header + "\n" + "\n".join(rules) + "\n", encoding="utf-8")
    print(f"[{title}] ditulis: {out}")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    for fname, title, url in SOURCES:
        try:
            build_one(fname, title, url)
        except Exception as exc:  # noqa: BLE001
            print(f"[{title}] ERROR: {exc}")


if __name__ == "__main__":
    main()
