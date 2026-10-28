# Avvisi tornei FITP

Due volte al giorno controlla i tornei di tennis su [fitp.it](https://www.fitp.it/Tornei/Ricerca-tornei)
nella zona configurata e manda su Telegram quelli nuovi con le iscrizioni ancora aperte.

## Come funziona

1. Chiede all'API usata dal sito tutte le competizioni FITP della provincia che iniziano da oggi in poi.
2. Per ognuna legge il dettaglio e tiene i tabelloni che corrispondono ai filtri di `config.json`
   (sesso, singolare/doppio, categoria d'età) con la scadenza delle iscrizioni non ancora passata.
3. Manda un unico messaggio Telegram con i tabelloni mai segnalati prima e li annota in `state.json`,
   così non te li ripropone.

I tornei TPRA sono esclusi perché il sito non ne espone il dettaglio.

## Configurazione

`config.json`:

| campo | significato |
|---|---|
| `id_regione`, `id_provincia` | Piemonte = 1, Torino = 201 (gli altri codici sono nei filtri del sito) |
| `gender` | `M` o `F` |
| `doubles` | `false` solo singolari, `true` solo doppi |
| `age_category` | `NOR` = categoria assoluta (esclude i tornei Under); `null` per tutti |

## Installazione

1. **Bot Telegram**: scrivi a [@BotFather](https://t.me/BotFather), comando `/newbot`, e copia il token.
2. **Chat id**: manda un messaggio qualsiasi al tuo bot, poi apri
   `https://api.telegram.org/bot<TOKEN>/getUpdates` e copia il valore di `"chat":{"id":...}`.
3. **Secrets su GitHub**: nel repository, *Settings → Secrets and variables → Actions → New repository secret*,
   crea `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
4. **Prova**: *Actions → Controlla tornei FITP → Run workflow*. Il primo giro manda tutti i tornei
   già aperti, i successivi solo quelli nuovi.

Per provarlo in locale senza inviare nulla: `python3 fitp_alert.py --dry-run`.

## Sicurezza

- Token e chat id stanno solo nei *GitHub Secrets*: sono cifrati, non finiscono mai nel codice
  né in `state.json`, e GitHub li maschera con `***` nei log.
- Lo script non stampa mai l'URL di Telegram (che contiene il token), nemmeno in caso di errore.
- Il workflow ha solo il permesso di scrivere sul repository, per aggiornare `state.json`.
- Consigliato un repository **privato**. Se qualcuno ottenesse il token potrebbe al massimo scrivere
  messaggi come il tuo bot: in quel caso lo rigeneri da @BotFather con `/revoke`.
