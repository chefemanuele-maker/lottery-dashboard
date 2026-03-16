from __future__ import annotations

import shutil
from pathlib import Path

from flask import Flask, Response

import euromillions_live_dashboard_v2 as euro
import superenalotto_live_dashboard as supereno

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent


def ensure_packaged_data_available() -> None:
    """Make packaged history files visible to the original dashboard code."""
    # EuroMillions code expects the original CSV in ~/Data/Euro.
    euro.ensure_base_dir()
    packaged_csv = ROOT / "euromillions_export_2026-03-16.csv"
    target_csv = euro.USER_ORIGINAL
    if packaged_csv.exists() and not target_csv.exists():
        shutil.copy2(packaged_csv, target_csv)

    # SuperEnalotto code already searches cwd/Desktop/Downloads/BASE_DIR.
    # Copy packaged .xls archives to BASE_DIR as an extra fallback.
    supereno.ensure_base_dir()
    for path in ROOT.glob("it-superenalotto-past-draws-archive*.xls"):
        target = supereno.BASE_DIR / path.name
        if not target.exists():
            shutil.copy2(path, target)


@app.before_request
def _bootstrap() -> None:
    ensure_packaged_data_available()


@app.get("/")
def home() -> Response:
    html = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lottery Intelligence Hub</title>
<style>
:root{--bg:#07111f;--panel:#0b1730;--line:#183461;--cyan:#5ce8ff;--pink:#ff4db8;--text:#e6f8ff;--muted:#98b5ce;--lime:#95ff9c;}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial;background:radial-gradient(circle at top left,rgba(92,232,255,.16),transparent 25%),radial-gradient(circle at top right,rgba(255,77,184,.14),transparent 28%),linear-gradient(180deg,#020814,#07111f 55%,#020814);color:var(--text)}
.wrap{max-width:1100px;margin:0 auto;padding:28px}.hero,.card{background:linear-gradient(180deg,rgba(11,23,48,.97),rgba(8,18,40,.98));border:1px solid rgba(92,232,255,.16);border-radius:20px;box-shadow:0 18px 60px rgba(0,0,0,.32),0 0 36px rgba(92,232,255,.06)}
.hero{padding:24px}.pill{display:inline-block;padding:6px 10px;border-radius:999px;background:linear-gradient(90deg,var(--cyan),#b0fbff);color:#04101d;font-weight:900;font-size:12px;letter-spacing:.08em;text-transform:uppercase}h1{margin:12px 0 8px;font-size:46px;line-height:1;letter-spacing:-.04em}.lead{color:var(--muted);max-width:820px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.card{padding:20px}.title{font-size:24px;font-weight:800;margin-bottom:8px}.muted{color:var(--muted)}.btn{display:inline-block;margin-top:16px;padding:12px 16px;border-radius:12px;text-decoration:none;color:#04101d;font-weight:900;background:linear-gradient(90deg,var(--cyan),#b6ffff);box-shadow:0 0 24px rgba(92,232,255,.15)}.btn.alt{background:linear-gradient(90deg,#ffd86a,#fff1b3)}.mini{font-size:13px;color:var(--muted);margin-top:10px}.list{margin:12px 0 0;padding-left:18px;color:var(--muted)}@media(max-width:860px){.grid{grid-template-columns:1fr}h1{font-size:38px}}
</style>
</head>
<body>
<div class="wrap">
  <section class="hero">
    <span class="pill">Lottery Intelligence Hub</span>
    <h1>Dashboard web pronta per deploy</h1>
    <p class="lead">Due pagine separate, stesso stile professionale: una per EuroMillions UK e una per SuperEnalotto. Ogni pagina prova ad aggiornarsi dalla fonte ufficiale quando la apri e usa la cache locale se il sito ufficiale non risponde.</p>
  </section>
  <div class="grid">
    <section class="card">
      <div class="title">EuroMillions UK</div>
      <div class="muted">Best line for next draw, backup lines, top numbers, top stars, pattern analysis, refresh automatico alla visita.</div>
      <a class="btn" href="/euromillions">Apri /euromillions</a>
      <div class="mini">Storico iniziale incluso nel pacchetto: CSV locale.</div>
    </section>
    <section class="card">
      <div class="title">SuperEnalotto Italia</div>
      <div class="muted">Best line for next draw, backup lines, top numbers, SuperStar ranking, pattern analysis, refresh automatico alla visita.</div>
      <a class="btn alt" href="/superenalotto">Apri /superenalotto</a>
      <div class="mini">Archivi .xls inclusi nel pacchetto per bootstrap locale.</div>
    </section>
  </div>
  <section class="card" style="margin-top:18px;">
    <div class="title">Rotte disponibili</div>
    <ul class="list">
      <li><strong>/</strong> home</li>
      <li><strong>/euromillions</strong> dashboard EuroMillions UK</li>
      <li><strong>/superenalotto</strong> dashboard SuperEnalotto</li>
      <li><strong>/health</strong> health check semplice</li>
    </ul>
  </section>
</div>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.get("/euromillions")
def euromillions_page() -> Response:
    df, refresh = euro.refresh_history()
    data = euro.build_dashboard_data(df)
    return Response(euro.render_dashboard(data, refresh), mimetype="text/html")


@app.get("/superenalotto")
def superenalotto_page() -> Response:
    payload = supereno.build_dashboard_payload()
    return Response(supereno.render_html(payload), mimetype="text/html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
