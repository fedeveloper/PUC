#!/usr/bin/env python3
"""Avvisa su Telegram dei nuovi tornei FITP con iscrizioni aperte.

Interroga le stesse API usate da https://www.fitp.it/Tornei/Ricerca-tornei,
filtra i tabelloni che corrispondono alla configurazione (provincia, sesso,
singolare/doppio) con scadenza iscrizioni futura, e invia un messaggio
Telegram per ogni tabellone mai segnalato prima. Solo libreria standard.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

API_BASE = "https://dp-myfit-test-function-v2.azurewebsites.net"  # quello usato dal sito
LIST_URL = API_BASE + "/api/v3/tornei/puc/list"
DETAIL_URL = API_BASE + "/api/v3/puc/competizione/dettaglio"
PAGE_URL = "https://www.fitp.it/Tornei/Dettaglio-Competizione?competitionId="
TENNIS = 4332
PAGE_SIZE = 25
ROME_TZ = ZoneInfo("Europe/Rome")
USER_AGENT = "fitp-alert/1.0 (avvisi personali tornei)"


def post_json(url, payload, retries=3):
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data, headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            # L'API risponde 200 con corpo vuoto quando non ci sono risultati.
            return json.loads(body) if body.strip() else None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries - 1:
                raise
            print(f"Errore su {url} ({exc}), riprovo...", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def list_competitions(cfg, today):
    """Tutte le competizioni FITP della zona che iniziano da oggi in poi."""
    competitions, skip = [], 0
    while True:
        payload = {
            "guid": "", "profilazione": "", "freetext": None,
            "id_regione": cfg["id_regione"], "id_provincia": cfg["id_provincia"],
            "id_stato": None, "id_disciplina": TENNIS, "sesso": None,
            "data_inizio": today.strftime("%d/%m/%Y"), "data_fine": None,
            "tipo_competizione": None, "categoria_eta": None,
            "id_classifica": None, "classifica": None,
            "massimale_montepremi": None,
            "iscrizioneStranieriNonTesseratiFitAbilitata": None,
            "id_area_regionale": None, "ambito": None,
            "rowstoskip": skip, "fetchrows": PAGE_SIZE,
            "sortcolumn": "data_inizio", "sortorder": "asc",
        }
        data = post_json(LIST_URL, payload)
        if not data or not data.get("competizioni"):
            break
        competitions += data["competizioni"]
        skip += PAGE_SIZE
        if skip >= data.get("record", 0):
            break
    # I tornei TPRA hanno un guid fittizio e nessun dettaglio consultabile.
    return [c for c in competitions if c.get("id_fonte") == "TORNEI FITP"]


def parse_utc(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def matching_tournaments(detail, cfg, now):
    """Tabelloni del dettaglio che corrispondono ai filtri e sono ancora aperti."""
    for t in detail.get("Tournaments") or []:
        if t.get("Gender") != cfg["gender"]:
            continue
        if bool(t.get("IsDoubleTournament")) != cfg["doubles"]:
            continue
        age = cfg.get("age_category")
        if age and age not in (t.get("CategoryAge") or "").split(","):
            continue
        end = t.get("DateEndSubscription")
        if not end or parse_utc(end) <= now:
            continue
        yield t


def format_message(comp, detail, t):
    deadline = parse_utc(t["DateEndSubscription"]).astimezone(ROME_TZ)
    lines = [
        f"🎾 <b>{esc(detail.get('Description') or comp['nome_torneo']).strip()}</b>",
        f"{esc(t.get('TournamentDescription', ''))}",
        f"📍 {esc(detail.get('TennisClub', ''))} – {esc(detail.get('Municipality') or comp.get('citta', ''))}",
        f"📅 {comp['data_inizio']} → {comp['data_fine']}",
        f"⏰ Iscrizioni entro {deadline:%d/%m/%Y %H:%M}",
    ]
    if t.get("AvailableRankings"):
        lines.append(f"🏅 Classifiche: {esc(t['AvailableRankings'])}")
    if t.get("TennisCourtType"):
        lines.append(f"🏟 {esc(t['TennisCourtType'])}")
    if not detail.get("OnLineSubscriptions"):
        lines.append("⚠️ Iscrizione online non consentita")
    lines.append(f'<a href="{PAGE_URL}{comp["guid"]}">Apri su fitp.it</a>')
    return "\n".join(lines)


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json.dumps(payload).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        # Non stampare l'URL: contiene il token.
        raise RuntimeError(f"Telegram ha risposto {exc.code}: {exc.read()[:200]!r}") from None


def send_digest(blocks, dry_run):
    """Invia i tornei raggruppati, restando sotto il limite di 4096 caratteri."""
    header = f"Nuovi tornei con iscrizioni aperte: {len(blocks)}"
    messages, current = [], header
    for block in blocks:
        if len(current) + len(block) + 2 > 4000:
            messages.append(current)
            current = block
        else:
            current += "\n\n" + block
    messages.append(current)
    for text in messages:
        if dry_run:
            print("=" * 40 + "\n" + text)
        else:
            send_telegram(text)
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--state", default="state.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="stampa i messaggi invece di inviarli e non salva lo stato")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = json.load(f)
    try:
        with open(args.state) as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {"seen": {}}
    seen = state["seen"]

    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(ROME_TZ).date()
    competitions = list_competitions(cfg, today)
    print(f"Competizioni FITP in zona da {today:%d/%m/%Y}: {len(competitions)}")

    blocks = []
    for comp in competitions:
        detail = post_json(DETAIL_URL, {"competitionUid": comp["guid"]})
        time.sleep(0.5)  # gentile con il server
        if not detail:
            continue
        for t in matching_tournaments(detail, cfg, now):
            key = str(t.get("TournamentUid") or t.get("TournamentId"))
            if key in seen:
                continue
            blocks.append(format_message(comp, detail, t))
            seen[key] = {"nome": t.get("TournamentDescription"),
                         "competizione": comp["guid"],
                         "scadenza": t["DateEndSubscription"]}

    # Dimentica i tornei la cui scadenza è passata da più di 60 giorni.
    cutoff = now - dt.timedelta(days=60)
    state["seen"] = {k: v for k, v in seen.items() if parse_utc(v["scadenza"]) > cutoff}
    if blocks:
        send_digest(blocks, args.dry_run)
    print(f"Nuovi tornei segnalati: {len(blocks)}")
    if not args.dry_run:
        with open(args.state, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")


if __name__ == "__main__":
    main()
