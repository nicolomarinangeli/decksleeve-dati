#!/usr/bin/env python3
"""La copia giornaliera di tcgcsv da cui legge DeckSleeve.

tcgcsv.com ripubblica ogni giorno categorie, gruppi, prodotti e prezzi di
TCGplayer, e nelle sue regole (https://tcgcsv.com/docs, «Usage Guidelines»)
chiede di non essere chiamato dalle app degli utenti: i dati vanno tenuti in
una copia propria, aggiornata una volta al giorno, con un User-Agent
riconoscibile e almeno 100 ms fra una richiesta e l'altra.

Questo script fa quella copia. Gira una volta al giorno su GitHub Actions
(vedi workflow.yml) e scrive una cartella pronta per GitHub Pages:

    last-updated.txt                      la data di tcgcsv da cui viene la copia
    tcgplayer/<categoria>/groups.json
    tcgplayer/<categoria>/<gruppo>/products.json
    tcgplayer/<categoria>/<gruppo>/prices.json
    stato.json                            quando, quanti file, quanti presi dalla copia di prima
    index.html                            da dove vengono i dati

Gli stessi percorsi di tcgcsv con «.json» in fondo: GitHub Pages comprime solo
i file di cui riconosce il tipo, e senza estensione ogni telefono scaricherebbe
dieci volte tanto.

Se tcgcsv non è cambiato dall'ultima copia pubblicata, non scarica nulla.
Se una richiesta fallisce del tutto, prende quel file dalla copia di ieri;
se ne fallisce più dell'1 %, si ferma e la copia di ieri resta online.

Uso:
    python3 copia.py --uscita sito --precedente https://<utente>.github.io/<repo>
    python3 copia.py --uscita prova --categorie 23        (una categoria, per provare)
"""

import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

TCGCSV = "https://tcgcsv.com"
USER_AGENT = "DeckSleeveCopia/1.0 (+https://github.com/nicolomarinangeli/decksleeve-dati)"

# Le categorie di TCGplayer che l'app legge, e perché.
CATEGORIE = {
    1: "Magic (solo i prodotti sigillati)",
    2: "Yu-Gi-Oh! (solo i prodotti sigillati)",
    3: "Pokémon (le stampe che le altre fonti non hanno, e i sigillati)",
    85: "Pokémon giapponese",
    68: "One Piece",
    80: "Dragon Ball Super Fusion World",
    27: "Dragon Ball Super Masters",
    23: "Dragon Ball Z (Panini)",
}

# tcgcsv chiede almeno 100 ms; un po' di margine non costa nulla.
PAUSA = 0.15
TENTATIVI = 4
SOGLIA_FALLITI = 0.01

_ultima = 0.0


def scarica(url, riservato=True):
    """Il contenuto di un indirizzo, con la pausa e i tentativi. Solleva l'ultimo errore."""
    global _ultima
    errore = None
    for tentativo in range(TENTATIVI):
        if riservato:
            attesa = PAUSA - (time.monotonic() - _ultima)
            if attesa > 0:
                time.sleep(attesa)
            _ultima = time.monotonic()
        richiesta = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(richiesta, timeout=60) as risposta:
                dati = risposta.read()
                if risposta.headers.get("Content-Encoding") == "gzip":
                    dati = gzip.decompress(dati)
                return dati
        except urllib.error.HTTPError as e:
            errore = e
            if e.code == 404:
                break
            # 403/429: tcgcsv blocca per 10 minuti chi va troppo veloce.
            if e.code in (403, 429):
                print(f"  {e.code} da {url}: aspetto 11 minuti", flush=True)
                time.sleep(660)
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            errore = e
        time.sleep([5, 30, 120, 0][tentativo])
    raise errore


def json_valido(dati):
    """Il JSON di tcgcsv, se è una risposta riuscita; altrimenti None."""
    try:
        documento = json.loads(dati)
    except ValueError:
        return None
    if not isinstance(documento, dict) or documento.get("success") is not True:
        return None
    if not isinstance(documento.get("results"), list):
        return None
    return documento


def scrivi(cartella, percorso, dati):
    destinazione = os.path.join(cartella, percorso)
    os.makedirs(os.path.dirname(destinazione), exist_ok=True)
    with open(destinazione, "wb") as f:
        f.write(dati)


def main():
    parametri = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parametri.add_argument("--uscita", required=True, help="cartella da scrivere (viene creata)")
    parametri.add_argument("--precedente", help="indirizzo della copia pubblicata, per saltare un giorno uguale e per i file che non arrivano")
    parametri.add_argument("--categorie", help="solo queste, separate da virgole (per provare)")
    parametri.add_argument("--forza", action="store_true", help="copia anche se tcgcsv non è cambiato")
    argomenti = parametri.parse_args()

    categorie = [int(c) for c in argomenti.categorie.split(",")] if argomenti.categorie else list(CATEGORIE)
    precedente = argomenti.precedente.rstrip("/") if argomenti.precedente else None
    uscita = argomenti.uscita

    aggiornato = scarica(f"{TCGCSV}/last-updated.txt").decode().strip()
    print(f"tcgcsv aggiornato: {aggiornato}", flush=True)

    if precedente and not argomenti.forza:
        try:
            pubblicato = scarica(f"{precedente}/last-updated.txt", riservato=False).decode().strip()
        except Exception:
            pubblicato = None
        if pubblicato == aggiornato:
            print("La copia pubblicata è già di questa data: niente da fare.")
            esito("cambiato", "no")
            return

    os.makedirs(uscita, exist_ok=True)
    file_scritti = 0
    falliti = []
    ripresi = []

    def prendi(percorso_tcgcsv, percorso_copia):
        nonlocal file_scritti
        try:
            dati = scarica(f"{TCGCSV}/tcgplayer/{percorso_tcgcsv}")
            if json_valido(dati) is None:
                raise ValueError("risposta non valida")
        except Exception as e:
            if not precedente:
                falliti.append(f"{percorso_tcgcsv}: {e}")
                return None
            try:
                dati = scarica(f"{precedente}/{percorso_copia}", riservato=False)
                if json_valido(dati) is None:
                    raise ValueError("copia di ieri non valida")
                ripresi.append(percorso_copia)
            except Exception as e2:
                falliti.append(f"{percorso_tcgcsv}: {e} (e dalla copia di ieri: {e2})")
                return None
        scrivi(uscita, percorso_copia, dati)
        file_scritti += 1
        return dati

    totale_gruppi = 0
    for categoria in categorie:
        dati = prendi(f"{categoria}/groups", f"tcgplayer/{categoria}/groups.json")
        if dati is None:
            # Senza l'elenco dei gruppi la categoria intera mancherebbe: meglio fermarsi.
            print(f"Elenco dei gruppi della categoria {categoria} non arrivato.", file=sys.stderr)
            esito("cambiato", "no")
            sys.exit(1)
        gruppi = [g["groupId"] for g in json.loads(dati)["results"]]
        totale_gruppi += len(gruppi)
        print(f"Categoria {categoria} ({CATEGORIE.get(categoria, '?')}): {len(gruppi)} gruppi", flush=True)
        for indice, gruppo in enumerate(gruppi, 1):
            for tipo in ("products", "prices"):
                prendi(f"{categoria}/{gruppo}/{tipo}", f"tcgplayer/{categoria}/{gruppo}/{tipo}.json")
            if indice % 50 == 0:
                print(f"  {indice}/{len(gruppi)}", flush=True)

    attesi = len(categorie) + totale_gruppi * 2
    if falliti:
        print(f"{len(falliti)} file non arrivati:", file=sys.stderr)
        for riga in falliti[:30]:
            print(f"  {riga}", file=sys.stderr)
    if len(falliti) > attesi * SOGLIA_FALLITI:
        print("Troppi file mancanti: la copia non si pubblica.", file=sys.stderr)
        esito("cambiato", "no")
        sys.exit(1)

    # Per ultima, come fa tcgcsv: chi la legge sa che tutto il resto è già al suo posto.
    scrivi(uscita, "last-updated.txt", (aggiornato + "\n").encode())
    scrivi(uscita, ".nojekyll", b"")
    stato = {
        "tcgcsvAggiornato": aggiornato,
        "copiatoIl": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "categorie": categorie,
        "gruppi": totale_gruppi,
        "file": file_scritti,
        "presiDallaCopiaDiIeri": len(ripresi),
        "mancanti": len(falliti),
    }
    scrivi(uscita, "stato.json", (json.dumps(stato, indent=2, ensure_ascii=False) + "\n").encode())
    scrivi(uscita, "index.html", PAGINA.format(aggiornato=aggiornato).encode())
    print(f"Fatto: {file_scritti} file, {len(ripresi)} presi dalla copia di ieri, {len(falliti)} mancanti.")
    esito("cambiato", "sì")


def esito(chiave, valore):
    """Un valore per i passi successivi del workflow, se gira su GitHub Actions."""
    percorso = os.environ.get("GITHUB_OUTPUT")
    if percorso:
        with open(percorso, "a") as f:
            f.write(f"{chiave}={'true' if valore == 'sì' else 'false'}\n")


PAGINA = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dati di DeckSleeve</title></head>
<body style="font-family:system-ui,sans-serif;max-width:40em;margin:2em auto;padding:0 1em;line-height:1.5">
<h1>Dati di DeckSleeve</h1>
<p>Copia giornaliera di <a href="https://tcgcsv.com">tcgcsv.com</a>, che ripubblica i dati di TCGplayer,
fatta perché l'app DeckSleeve non chiami tcgcsv dai telefoni, come chiedono le sue regole.
Grazie a tcgcsv per il suo lavoro.</p>
<p>Dati di tcgcsv del {aggiornato}. Prodotti e prezzi sono di TCGplayer.</p>
</body></html>
"""


if __name__ == "__main__":
    main()
