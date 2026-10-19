# Copia giornaliera di tcgcsv

L'app legge da qui i dati di One Piece e Dragon Ball, le carte Pokémon
giapponesi e quelle che mancano alle altre fonti, e i prodotti sigillati con i
loro prezzi. Prima li chiedeva a tcgcsv.com direttamente dal telefono.

## Perché una copia

Le regole di tcgcsv (https://tcgcsv.com/docs, «Usage Guidelines») chiedono:

- niente richieste dalle app degli utenti: i dati vanno tenuti in un database
  o in una cache propri;
- un User-Agent riconoscibile e almeno 100 ms fra le richieste (oltre: IP
  bloccato per 10 minuti);
- non più di 10.000 richieste in 24 ore;
- leggere prima `last-updated.txt` e aggiornare una volta al giorno.

La copia rispetta tutto: una sola macchina chiede, una volta al giorno, circa
4.100 richieste (8 categorie, circa 2.050 gruppi, prodotti e prezzi di ognuno),
con 150 ms fra l'una e l'altra.

## Dove sta

Repository pubblico `nicolomarinangeli/decksleeve-dati` su GitHub:

- `copia.py` alla radice;
- il workflow in `.github/workflows/copia.yml`;
- GitHub Pages con sorgente «GitHub Actions».

Indirizzo letto dall'app (`TCGCSVMirror.ROOT`):
`https://nicolomarinangeli.github.io/decksleeve-dati`

Perché GitHub e non un server: gratis per un repository pubblico, nessuna
macchina da tenere accesa, nessuna carta di credito; Pages comprime i JSON
(circa 400 MB sul disco, circa 40 MB compressi) e regge il traffico dell'app.
Limiti da tenere d'occhio: sito ≤ 1 GB, traffico indicativo 100 GB al mese.
Se un giorno non bastassero, si mette Cloudflare davanti senza toccare l'app.

## Come si prova sul Mac

```bash
python3 -I copia.py --uscita /tmp/copia --categorie 23
```

Una categoria piccola (Dragon Ball Z, 9 gruppi): pochi secondi.

## Cosa fa se qualcosa va storto

- tcgcsv non è cambiato dall'ultima copia: non scarica nulla, non pubblica.
- Un file non arriva dopo 4 tentativi: lo prende dalla copia di ieri.
- Più dell'1 % dei file mancanti, o manca l'elenco dei gruppi di una
  categoria: si ferma, e online resta la copia di ieri.
- 403 o 429 da tcgcsv: aspetta 11 minuti prima di riprovare.
- GitHub sospende i lavori pianificati di un repository senza attività per
  60 giorni: il workflow fa un commit con `stato.json` se l'ultimo ha più di
  40 giorni. Se succedesse lo stesso, arriva una mail: basta riattivarli da
  «Actions».
