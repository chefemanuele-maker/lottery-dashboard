
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import random
import re
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import pandas as pd
except Exception:
    print("This app needs pandas installed. Try: pip3 install pandas requests xlrd")
    raise

try:
    import requests
except Exception:
    print("This app needs requests installed. Try: pip3 install requests")
    raise

LATEST_URL = "https://www.superenalotto.it/ultima-estrazione"
ARCHIVE_URL = "https://www.superenalotto.it/archivio-estrazioni"
OFFICIAL_HOME = "https://www.superenalotto.it"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
DEFAULT_PORT = 8776

BASE_DIR = Path.home() / "Data" / "SuperEnalotto"
LOCAL_HISTORY = BASE_DIR / "superenalotto_history_live.csv"
PACKAGED_HISTORY = Path(__file__).resolve().parent / "superenalotto_history.csv"

N_MAIN = list(range(1, 91))
N_SUPERSTAR = list(range(1, 91))

MONTHS_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

@dataclass
class RefreshResult:
    source: str
    ok: bool
    message: str
    draws_added: int = 0
    latest_date: Optional[str] = None

def ensure_base_dir() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def parse_it_date(text: str) -> dt.date:
    t = collapse_ws(text).lower()
    m = re.search(r"(\d{1,2})\s+([a-zàèéìòù]+)\s+(\d{4})", t, re.I)
    if not m:
        raise ValueError(f"Could not parse Italian date: {text}")
    day = int(m.group(1))
    month = MONTHS_IT[m.group(2).lower()]
    year = int(m.group(3))
    return dt.date(year, month, day)

def standardize_history(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename = {c: str(c).strip().lower() for c in df.columns}
    df = df.rename(columns=rename)
    required = ["draw_date", "n1", "n2", "n3", "n4", "n5", "n6", "superstar"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing column {c}")
    if "jolly" not in df.columns:
        df["jolly"] = pd.NA
    if "draw_number" not in df.columns:
        df["draw_number"] = pd.NA
    if "weekday" not in df.columns:
        df["weekday"] = pd.NA
    if "jackpot" not in df.columns:
        df["jackpot"] = pd.NA
    if "source" not in df.columns:
        df["source"] = "local_archive"

    df["draw_date"] = pd.to_datetime(df["draw_date"], errors="coerce").dt.date
    for c in ["n1","n2","n3","n4","n5","n6","jolly","superstar","draw_number"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    df = df.dropna(subset=["draw_date","n1","n2","n3","n4","n5","n6","superstar"]).copy()
    return df

def parse_superenalotto_xls(path: Path) -> pd.DataFrame:
    try:
        import xlrd  # noqa: F401
    except Exception as exc:
        raise RuntimeError("xlrd is required only when falling back to old .xls archives.") from exc

    raw = pd.read_excel(path, engine="xlrd", header=3)
    raw.columns = raw.iloc[0]
    df = raw.iloc[1:].copy()
    df.columns = [str(c).strip() for c in df.columns]

    keep = ["Data", "Giorno della Settimana", "1", "2", "3", "4", "5", "6", "JOLLY", "Superstar"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing expected columns {missing}")

    df = df[keep].rename(columns={
        "Data": "draw_date",
        "Giorno della Settimana": "weekday",
        "1": "n1", "2": "n2", "3": "n3", "4": "n4", "5": "n5", "6": "n6",
        "JOLLY": "jolly", "Superstar": "superstar"
    })
    df["source"] = f"xls:{path.name}"
    return standardize_history(df)

def dedupe_history(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["draw_date","n1","n2","n3","n4","n5","n6","superstar"]
    if "jolly" in df.columns:
        keys.append("jolly")
    return (
        df.sort_values("draw_date")
        .drop_duplicates(subset=keys, keep="last")
        .sort_values("draw_date")
        .reset_index(drop=True)
    )

def persist_history(df: pd.DataFrame) -> None:
    ensure_base_dir()
    out = df.copy()
    out["draw_date"] = out["draw_date"].astype(str)
    out.to_csv(LOCAL_HISTORY, index=False)

def discover_local_archives() -> List[Path]:
    places = [
        Path.cwd(),
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        BASE_DIR,
    ]
    seen = set()
    found: List[Path] = []
    for place in places:
        if not place.exists():
            continue
        for p in sorted(place.glob("it-superenalotto-past-draws-archive*.xls")):
            if p not in seen:
                found.append(p)
                seen.add(p)
    return found

def load_local_history() -> pd.DataFrame:
    ensure_base_dir()
    frames: List[pd.DataFrame] = []

    # Fast path for hosting: prefer the prebuilt CSV snapshot to avoid loading many .xls files in memory.
    for candidate in [PACKAGED_HISTORY, LOCAL_HISTORY]:
        if candidate.exists():
            try:
                frames.append(standardize_history(pd.read_csv(candidate)))
            except Exception:
                pass

    # Fallback only when no CSV history is available.
    if not frames:
        for p in discover_local_archives():
            try:
                frames.append(parse_superenalotto_xls(p))
            except Exception:
                continue

    if not frames:
        raise FileNotFoundError(
            "No SuperEnalotto history found. Keep superenalotto_history.csv near the dashboard, or provide the .xls archives as fallback."
        )

    df = dedupe_history(pd.concat(frames, ignore_index=True))
    persist_history(df)
    return df

def fetch_text(url: str, timeout: int = 20) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT, "Referer": OFFICIAL_HOME})
    r.raise_for_status()
    return r.text

def parse_latest_from_archive_text(text: str) -> Dict[str, object]:
    t = collapse_ws(text.replace("\xa0", " "))
    patt = re.compile(
        r"Concorso\s*N[º°]?\s*(\d+)\s+del\s+(\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4})\s+"
        r"(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+"
        r"(\d{1,2})\s+(\d{1,2})\s+Dettagli",
        re.I
    )
    m = patt.search(t)
    if not m:
        raise ValueError("Could not parse latest draw from archive page text.")
    nums = list(map(int, m.groups()[2:10]))
    return {
        "draw_number": int(m.group(1)),
        "draw_date": parse_it_date(m.group(2)),
        "n1": nums[0], "n2": nums[1], "n3": nums[2],
        "n4": nums[3], "n5": nums[4], "n6": nums[5],
        "jolly": nums[6], "superstar": nums[7],
        "source": "official_archive_page",
    }

def parse_latest_from_latest_text(text: str) -> Dict[str, object]:
    t = collapse_ws(text.replace("\xa0", " "))
    p1 = re.compile(
        r"Concorso\s*N[º°]?\s*(\d+)\s+del\s+(\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4}).{0,300}?"
        r"Combinazione vincente\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+"
        r"Jolly\s+(\d{1,2})\s+SuperStar\s+(\d{1,2})",
        re.I
    )
    m = p1.search(t)
    if not m:
        raise ValueError("Could not parse latest draw from ultima-estrazione page.")
    nums = list(map(int, m.groups()[2:10]))
    return {
        "draw_number": int(m.group(1)),
        "draw_date": parse_it_date(m.group(2)),
        "n1": nums[0], "n2": nums[1], "n3": nums[2],
        "n4": nums[3], "n5": nums[4], "n6": nums[5],
        "jolly": nums[6], "superstar": nums[7],
        "source": "official_latest_page",
    }

def fetch_latest_official() -> Dict[str, object]:
    errors = []
    for url, parser in [(LATEST_URL, parse_latest_from_latest_text), (ARCHIVE_URL, parse_latest_from_archive_text)]:
        try:
            return parser(fetch_text(url))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(" ; ".join(errors))

def refresh_history() -> Tuple[pd.DataFrame, RefreshResult]:
    df = load_local_history()
    try:
        latest = fetch_latest_official()
        one = pd.DataFrame([latest])
        one = standardize_history(one)
        before = len(df)
        merged = dedupe_history(pd.concat([df, one], ignore_index=True))
        persist_history(merged)
        added = len(merged) - before
        return merged, RefreshResult(
            source=str(latest.get("source", "official_site")),
            ok=True,
            message="Aggiornamento ufficiale completato.",
            draws_added=max(0, added),
            latest_date=str(merged["draw_date"].max()),
        )
    except Exception as exc:
        return df, RefreshResult(
            source="local_cache",
            ok=False,
            message=f"Fonte ufficiale non disponibile adesso. Uso cache locale. ({exc})",
            draws_added=0,
            latest_date=str(df["draw_date"].max()) if not df.empty else None,
        )

def enrich_history(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    num_cols = [f"n{i}" for i in range(1, 7)]
    out["draw_date"] = pd.to_datetime(out["draw_date"])
    out["sum_main"] = out[num_cols].astype(int).sum(axis=1)
    out["odd_count"] = out[num_cols].astype(int).apply(lambda r: sum(v % 2 for v in r), axis=1)
    out["even_count"] = 6 - out["odd_count"]
    out["low_count"] = out[num_cols].astype(int).apply(lambda r: sum(v <= 45 for v in r), axis=1)
    out["high_count"] = 6 - out["low_count"]
    out["odd_even"] = out["odd_count"].astype(str) + "-" + out["even_count"].astype(str)
    out["low_high"] = out["low_count"].astype(str) + "-" + out["high_count"].astype(str)
    return out.sort_values("draw_date").reset_index(drop=True)

def build_rank_table(df: pd.DataFrame, number_pool: Sequence[int], cols: Sequence[str], kind: str) -> pd.DataFrame:
    appearances = {n: 0 for n in number_pool}
    last_seen = {n: None for n in number_pool}
    work = df.reset_index(drop=True)

    for idx, row in work.iterrows():
        vals = [int(row[c]) for c in cols]
        for v in vals:
            if v in appearances:
                appearances[v] += 1
                last_seen[v] = idx

    n_draws = len(work)
    rows = []
    for n in number_pool:
        since_seen = n_draws if last_seen[n] is None else (n_draws - 1 - last_seen[n])
        freq = appearances[n]
        freq_rate = freq / max(1, n_draws)
        recency = since_seen / max(1, n_draws)
        hot_score = 100 * (0.72 * freq_rate + 0.28 * recency)
        rows.append({
            "number": n,
            "kind": kind,
            "frequency": freq,
            "freq_rate": freq_rate,
            "draws_since_seen": since_seen,
            "score": hot_score,
        })
    out = pd.DataFrame(rows).sort_values(["score","frequency","number"], ascending=[False,False,True]).reset_index(drop=True)
    out["rank"] = range(1, len(out)+1)
    return out

def build_pattern_table(series: pd.Series, label: str) -> pd.DataFrame:
    counts = series.value_counts(dropna=False).rename_axis(label).reset_index(name="count")
    counts["pct"] = counts["count"] / counts["count"].sum()
    return counts

def line_score(numbers: Sequence[int], superstar: int, main_rank: pd.DataFrame, ss_rank: pd.DataFrame,
               odd_even_pref: Dict[str,float], low_high_pref: Dict[str,float], median_sum: float) -> Tuple[float, Dict[str, object]]:
    mr = main_rank.set_index("number")["score"].to_dict()
    sr = ss_rank.set_index("number")["score"].to_dict()
    nums = sorted(numbers)
    odd = sum(n % 2 for n in nums)
    even = 6 - odd
    low = sum(n <= 45 for n in nums)
    high = 6 - low
    odd_even = f"{odd}-{even}"
    low_high = f"{low}-{high}"
    total = sum(nums)
    raw = sum(mr.get(n, 0) for n in nums) + 0.65 * sr.get(superstar, 0)
    raw += 26 * odd_even_pref.get(odd_even, 0)
    raw += 18 * low_high_pref.get(low_high, 0)
    raw += max(0, 18 - abs(total - median_sum) / 3.5)
    if len(set(nums)) < 6:
        raw -= 100
    if max(nums) - min(nums) < 20:
        raw -= 8
    return raw, {"sum_main": total, "odd_even": odd_even, "low_high": low_high}

def pick_weighted_unique(candidates: Sequence[int], weights: Sequence[float], k: int, rng: random.Random) -> List[int]:
    chosen: List[int] = []
    cand = list(candidates)
    w = list(weights)
    while len(chosen) < k and cand:
        total = sum(w)
        if total <= 0:
            idx = rng.randrange(len(cand))
        else:
            r = rng.random() * total
            acc = 0.0
            idx = 0
            for i, ww in enumerate(w):
                acc += ww
                if acc >= r:
                    idx = i
                    break
        chosen.append(cand.pop(idx))
        w.pop(idx)
    return chosen

def generate_lines(df: pd.DataFrame, main_rank: pd.DataFrame, ss_rank: pd.DataFrame, lines_per_mode: int = 4, seed: int = 41) -> pd.DataFrame:
    rng = random.Random(seed)
    odd_even_pref = build_pattern_table(df["odd_even"], "odd_even").set_index("odd_even")["pct"].to_dict()
    low_high_pref = build_pattern_table(df["low_high"], "low_high").set_index("low_high")["pct"].to_dict()
    median_sum = float(df["sum_main"].median())

    top_main = main_rank["number"].tolist()
    top_ss = ss_rank["number"].tolist()
    candidate_rows = []

    mode_specs = {
        "safe":      {"main_slices": [(0,18,3.5,4), (18,35,2.3,2)], "ss_slice": (0,12,2.8)},
        "balanced":  {"main_slices": [(0,24,3.0,3), (12,42,2.1,2), (30,60,1.4,1)], "ss_slice": (0,18,2.2)},
        "aggressive":{"main_slices": [(0,20,2.2,2), (15,55,1.9,2), (40,90,1.4,2)], "ss_slice": (0,30,1.6)},
    }

    for mode, spec in mode_specs.items():
        for _ in range(500):
            nums: List[int] = []
            for start, end, power, count in spec["main_slices"]:
                pool = top_main[start:end]
                weights = [max(0.01, main_rank.set_index("number").loc[n, "score"]) ** power for n in pool]
                nums.extend(pick_weighted_unique([n for n in pool if n not in nums], weights[:len([n for n in pool if n not in nums])], count, rng))
            nums = sorted(set(nums))
            while len(nums) < 6:
                pool = [n for n in top_main[:70] if n not in nums]
                weights = [max(0.01, main_rank.set_index("number").loc[n, "score"]) for n in pool]
                nums.extend(pick_weighted_unique(pool, weights, 1, rng))
                nums = sorted(set(nums))
            if len(nums) != 6:
                continue

            s0, s1, spow = spec["ss_slice"]
            ss_pool = top_ss[s0:s1]
            ss_weights = [max(0.01, ss_rank.set_index("number").loc[n, "score"]) ** spow for n in ss_pool]
            superstar = pick_weighted_unique(ss_pool, ss_weights, 1, rng)[0]

            score, meta = line_score(nums, superstar, main_rank, ss_rank, odd_even_pref, low_high_pref, median_sum)
            candidate_rows.append({
                "mode": mode,
                "main_numbers": " ".join(f"{n:02d}" for n in nums),
                "superstar": f"{superstar:02d}",
                "score": round(score, 3),
                "sum_main": meta["sum_main"],
                "odd_even": meta["odd_even"],
                "low_high": meta["low_high"],
            })

    out = pd.DataFrame(candidate_rows)
    out = out.sort_values(["mode","score"], ascending=[True,False]).drop_duplicates(subset=["main_numbers","superstar"]).reset_index(drop=True)
    parts = []
    for mode in ["balanced","safe","aggressive"]:
        chunk = out[out["mode"] == mode].head(lines_per_mode)
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True)

def choose_best_line(lines: pd.DataFrame) -> Dict[str, object]:
    top = lines.sort_values("score", ascending=False).reset_index(drop=True)
    balanced = top[top["mode"] == "balanced"]
    if not balanced.empty and float(balanced.iloc[0]["score"]) >= float(top.iloc[0]["score"]) - 2.0:
        row = balanced.iloc[0]
        reason = "Balanced: il compromesso più solido tra numeri forti, mix medio e pattern storici."
    else:
        row = top.iloc[0]
        reason = "Scelto per score assoluto più alto nel modello statistico."
    return row.to_dict() | {"reason": reason}

def build_dashboard_payload() -> Dict[str, object]:
    history, refresh = refresh_history()
    hist = enrich_history(history)

    main_rank = build_rank_table(hist, N_MAIN, [f"n{i}" for i in range(1, 7)], "main")
    ss_rank = build_rank_table(hist, N_SUPERSTAR, ["superstar"], "superstar")
    odd_even = build_pattern_table(hist["odd_even"], "odd_even")
    low_high = build_pattern_table(hist["low_high"], "low_high")
    lines = generate_lines(hist, main_rank, ss_rank)
    best = choose_best_line(lines)

    latest = hist.sort_values("draw_date").iloc[-1].to_dict()
    latest["draw_date"] = pd.to_datetime(latest["draw_date"]).date().isoformat()

    return {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "refresh": refresh,
        "stored_draws": len(hist),
        "history_start": str(hist["draw_date"].min().date()),
        "history_end": str(hist["draw_date"].max().date()),
        "latest": latest,
        "best": best,
        "lines": lines.to_dict(orient="records"),
        "main_rank": main_rank.head(12).to_dict(orient="records"),
        "ss_rank": ss_rank.head(10).to_dict(orient="records"),
        "odd_even": odd_even.head(6).to_dict(orient="records"),
        "low_high": low_high.head(6).to_dict(orient="records"),
    }

def badge_class(ok: bool) -> str:
    return "badge-ok" if ok else "badge-warn"

def render_html(payload: Dict[str, object]) -> str:
    latest = payload["latest"]
    refresh: RefreshResult = payload["refresh"]
    best = payload["best"]
    lines = payload["lines"]

    def chips(nums: Sequence[int | str], cls: str = "chip"):
        return "".join(f'<span class="{cls}">{html.escape(str(n))}</span>' for n in nums)

    latest_nums = [f'{int(latest[f"n{i}"]):02d}' for i in range(1,7)]
    top_main_rows = "".join(
        f"<tr><td>{r['rank']}</td><td>{r['number']:02d}</td><td>{r['frequency']}</td><td>{r['draws_since_seen']}</td><td>{r['score']:.2f}</td></tr>"
        for r in payload["main_rank"]
    )
    top_ss_rows = "".join(
        f"<tr><td>{r['rank']}</td><td>{r['number']:02d}</td><td>{r['frequency']}</td><td>{r['draws_since_seen']}</td><td>{r['score']:.2f}</td></tr>"
        for r in payload["ss_rank"]
    )
    line_rows = "".join(
        f"<tr><td>{html.escape(str(r['mode']))}</td><td>{html.escape(str(r['main_numbers']))}</td><td>{html.escape(str(r['superstar']))}</td><td>{r['sum_main']}</td><td>{html.escape(str(r['odd_even']))}</td><td>{html.escape(str(r['low_high']))}</td><td>{float(r['score']):.3f}</td></tr>"
        for r in lines
    )
    odd_even_rows = "".join(
        f"<tr><td>{html.escape(str(r['odd_even']))}</td><td>{r['count']}</td><td>{100*float(r['pct']):.1f}%</td></tr>"
        for r in payload["odd_even"]
    )
    low_high_rows = "".join(
        f"<tr><td>{html.escape(str(r['low_high']))}</td><td>{r['count']}</td><td>{100*float(r['pct']):.1f}%</td></tr>"
        for r in payload["low_high"]
    )

    best_copy = f"{best['main_numbers']} | SuperStar {best['superstar']}"
    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SuperEnalotto cyber dashboard</title>
<style>
:root {{
  --bg:#06111f; --panel:#0a1630; --panel2:#0d1c3d; --line:#18305f;
  --text:#dff5ff; --muted:#9ab7d0; --cyan:#59e7ff; --pink:#ff49b6; --lime:#8dff8a; --gold:#ffd86a;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  background:
    radial-gradient(circle at top left, rgba(89,231,255,.16), transparent 26%),
    radial-gradient(circle at top right, rgba(255,73,182,.14), transparent 26%),
    linear-gradient(180deg, #030814, #071127 55%, #030814);
  color:var(--text);
}}
.wrap {{ max-width: 1220px; margin: 0 auto; padding: 22px; }}
.hero, .panel {{
  background: linear-gradient(180deg, rgba(10,22,48,.96), rgba(8,18,40,.97));
  border: 1px solid rgba(89,231,255,.18);
  border-radius: 18px;
  box-shadow: 0 0 0 1px rgba(255,255,255,.02) inset, 0 18px 60px rgba(0,0,0,.34), 0 0 36px rgba(89,231,255,.07);
}}
.hero {{ padding: 22px; margin-bottom: 18px; }}
.kicker {{ display:inline-block; font-size:12px; color:#09111f; background:linear-gradient(90deg,var(--cyan),#a7f7ff); padding:6px 10px; border-radius:999px; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
h1 {{ margin:12px 0 8px; font-size:42px; line-height:1; letter-spacing:-.03em; }}
p.lead {{ margin:0; color:var(--muted); max-width:900px; }}
.meta {{ display:flex; gap:14px; flex-wrap:wrap; margin-top:14px; color:var(--muted); font-size:13px; }}
.badge {{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge-ok {{ background:rgba(141,255,138,.12); color:#adffb0; border:1px solid rgba(141,255,138,.35); }}
.badge-warn {{ background:rgba(255,216,106,.12); color:#ffe699; border:1px solid rgba(255,216,106,.35); }}
.grid {{ display:grid; gap:18px; }}
.grid2 {{ grid-template-columns: 1.2fr .8fr; }}
.grid3 {{ grid-template-columns: repeat(3,1fr); }}
.panel {{ padding:18px; overflow:hidden; }}
.panel h2, .panel h3 {{ margin:0 0 12px; }}
.small {{ font-size:13px; color:var(--muted); }}
.big-line {{
  display:grid; grid-template-columns: 1fr auto; gap:20px; align-items:center;
  padding:18px; border-radius:16px;
  background:
    linear-gradient(135deg, rgba(89,231,255,.12), rgba(255,73,182,.08)),
    linear-gradient(180deg, rgba(12,28,61,.95), rgba(8,18,40,.96));
  border:1px solid rgba(89,231,255,.22);
}}
.line-main {{ font-size:34px; font-weight:900; letter-spacing:.06em; color:#fff; text-shadow:0 0 16px rgba(89,231,255,.18); }}
.line-ss {{ color:var(--gold); font-weight:800; font-size:20px; margin-top:8px; }}
.reason {{ margin-top:10px; color:var(--muted); }}
button {{
  appearance:none; border:0; cursor:pointer; border-radius:12px; padding:12px 14px; font-weight:800;
  color:#05101f; background:linear-gradient(90deg,var(--cyan),#b5ffff); box-shadow:0 0 24px rgba(89,231,255,.18);
}}
.btnbar {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }}
button.secondary {{ background:linear-gradient(90deg,#ffd86a,#fff0aa); }}
.chips {{ display:flex; gap:8px; flex-wrap:wrap; }}
.chip, .chip-gold {{
  width:42px; height:42px; border-radius:999px; display:inline-flex; align-items:center; justify-content:center;
  font-weight:900; box-shadow: 0 0 18px rgba(255,255,255,.05) inset;
}}
.chip {{ background:linear-gradient(180deg,#f4fbff,#d5e4f2); color:#071122; }}
.chip-gold {{ background:linear-gradient(180deg,#ffe07e,#f3b934); color:#09111e; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ text-align:left; padding:11px 10px; border-bottom:1px solid rgba(154,183,208,.12); }}
th {{ color:#8feeff; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
tbody tr:hover {{ background:rgba(89,231,255,.045); }}
.mode-pill {{
  display:inline-block; padding:6px 10px; border-radius:999px; font-size:12px; font-weight:800; text-transform:uppercase;
}}
.m-safe {{ background:rgba(141,255,138,.12); color:#a9ffb5; }}
.m-balanced {{ background:rgba(89,231,255,.12); color:#9bf2ff; }}
.m-aggressive {{ background:rgba(255,73,182,.12); color:#ff9ed6; }}
.stat-card {{
  padding:14px; border-radius:14px; background:linear-gradient(180deg, rgba(13,28,61,.9), rgba(9,18,39,.94)); border:1px solid rgba(255,255,255,.05);
}}
.stat-card b {{ display:block; font-size:14px; margin-bottom:8px; }}
.footer-note {{ margin-top:18px; font-size:12px; color:var(--muted); }}
@media (max-width: 980px) {{ .grid2, .grid3 {{ grid-template-columns: 1fr; }} .line-main {{ font-size:28px; }} }}
</style>
<script>
function copyBestLine() {{
  const text = {best_copy!r};
  navigator.clipboard.writeText(text).then(() => {{
    const el = document.getElementById('copyStatus');
    el.textContent = 'Copiata.';
    setTimeout(() => el.textContent = '', 1800);
  }});
}}
setTimeout(() => window.location.reload(), 1000 * 60 * 15);
</script>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <span class="kicker">SuperEnalotto live model</span>
    <h1>SuperEnalotto cyber picks dashboard</h1>
    <p class="lead">Si aggiorna quando la apri: usa i tuoi archivi .xls come base, poi prova a controllare l'ultima estrazione sul sito ufficiale SuperEnalotto e ricalcola la linea migliore per il prossimo concorso. È un supporto statistico, non una macchina che predice il futuro.</p>
    <div class="meta">
      <span class="badge {badge_class(refresh.ok)}">{html.escape(refresh.source)} · {html.escape(refresh.message)}</span>
      <span>Generata: {html.escape(payload['generated_at'])}</span>
      <span>Storico: {html.escape(payload['history_start'])} → {html.escape(payload['history_end'])}</span>
      <span>Concorsi salvati: {payload['stored_draws']}</span>
    </div>
  </section>

  <div class="grid grid2">
    <section class="panel">
      <h2>Best line for next draw</h2>
      <div class="big-line">
        <div>
          <div class="line-main">{html.escape(str(best['main_numbers']))}</div>
          <div class="line-ss">SuperStar {html.escape(str(best['superstar']))}</div>
          <div class="reason">{html.escape(str(best['reason']))}</div>
          <div class="small" style="margin-top:10px;">Score {float(best['score']):.3f} · Somma {best['sum_main']} · Odd/Even {html.escape(str(best['odd_even']))} · Low/High {html.escape(str(best['low_high']))}</div>
        </div>
        <div>
          <div class="btnbar">
            <button onclick="copyBestLine()">Copy best line</button>
            <button class="secondary" onclick="window.location.reload()">Refresh now</button>
          </div>
          <div id="copyStatus" class="small" style="margin-top:10px;"></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Latest official draw in your history</h2>
      <div class="small">Data concorso: {html.escape(str(latest['draw_date']))}</div>
      <div class="chips" style="margin-top:12px;">{chips(latest_nums, "chip")}</div>
      <div class="chips" style="margin-top:12px;"><span class="small" style="width:100%;">Jolly</span>{chips([f"{int(latest['jolly']):02d}"], "chip-gold")}</div>
      <div class="chips" style="margin-top:12px;"><span class="small" style="width:100%;">SuperStar</span>{chips([f"{int(latest['superstar']):02d}"], "chip-gold")}</div>
      <div class="small" style="margin-top:14px;">Concorso n. {html.escape(str(latest.get('draw_number', '—')))} · Sorgente {html.escape(str(latest.get('source', 'local')))}</div>
      <div class="footer-note">Nota utile: nel gioco reale scegli 6 numeri. Il Jolly viene estratto dal sistema e non si seleziona sulla schedina. SuperStar invece può essere suggerito separatamente.</div>
    </section>
  </div>

  <div class="grid grid3" style="margin-top:18px;">
    <section class="panel stat-card">
      <b>Safe</b>
      <div class="small">Si appoggia più forte ai numeri attualmente più robusti.</div>
    </section>
    <section class="panel stat-card">
      <b>Balanced</b>
      <div class="small">Il miglior compromesso tra numeri forti, medi e pattern ricorrenti.</div>
    </section>
    <section class="panel stat-card">
      <b>Aggressive</b>
      <div class="small">Lascia entrare più numeri ritardatari o meno comuni.</div>
    </section>
  </div>

  <section class="panel" style="margin-top:18px;">
    <h2>Suggested backup lines</h2>
    <table>
      <thead><tr><th>Mode</th><th>Main numbers</th><th>SuperStar</th><th>Sum</th><th>Odd-Even</th><th>Low-High</th><th>Score</th></tr></thead>
      <tbody>{line_rows}</tbody>
    </table>
  </section>

  <div class="grid grid2" style="margin-top:18px;">
    <section class="panel">
      <h2>Top 12 main numbers</h2>
      <table>
        <thead><tr><th>Rank</th><th>Numero</th><th>Frequency</th><th>Ritardo</th><th>Score</th></tr></thead>
        <tbody>{top_main_rows}</tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Top 10 SuperStar numbers</h2>
      <table>
        <thead><tr><th>Rank</th><th>Numero</th><th>Frequency</th><th>Ritardo</th><th>Score</th></tr></thead>
        <tbody>{top_ss_rows}</tbody>
      </table>
    </section>
  </div>

  <div class="grid grid2" style="margin-top:18px;">
    <section class="panel">
      <h2>Most common odd-even patterns</h2>
      <table>
        <thead><tr><th>Pattern</th><th>Count</th><th>Share</th></tr></thead>
        <tbody>{odd_even_rows}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Most common low-high patterns</h2>
      <table>
        <thead><tr><th>Pattern</th><th>Count</th><th>Share</th></tr></thead>
        <tbody>{low_high_rows}</tbody>
      </table>
    </section>
  </div>
</div>
</body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            payload = build_dashboard_payload()
            body = render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = f"<h1>Errore dashboard</h1><pre>{html.escape(str(exc))}</pre>".encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    def log_message(self, format, *args):
        return

def run_server(port: int, open_browser: bool = True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"SuperEnalotto dashboard running on {url}")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run_server(args.port, open_browser=not args.no_browser)

if __name__ == "__main__":
    main()
