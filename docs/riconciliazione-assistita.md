# Riconciliazione assistita di rette e fornitori

Implementazione del 14 settembre 2026.

## Comportamento

Gli import di movimenti bancari, fatture e scadenze accodano una ricerca di possibili abbinamenti. La ricerca parte dopo il salvataggio definitivo e funziona in entrambi gli ordini: movimento prima della scadenza o scadenza prima del movimento. Sono comprese le nuove rate generate dal piano delle iscrizioni e le modifiche a importi, identità e pagamenti collegati.

Il pulsante **Riconciliazioni da verificare**, nell'intestazione, mostra il numero dei casi aperti e viene evidenziato quando il numero è positivo. Il popup si apre soltanto al clic. Il contatore si aggiorna ogni 30 secondi quando la pagina è visibile e dopo le decisioni nel popup.

Il popup separa rette e fornitori. Ogni proposta espone movimento, destinatario, scadenza, importo assegnato, residui successivi e motivi della compatibilità. Sono gestiti abbinamenti singoli, parziali e cumulativi, anche con più movimenti. Il punteggio è un indice di compatibilità delle regole esistenti, non una probabilità statistica.

- **Conferma abbinamento** registra il pagamento usando i servizi contabili esistenti.
- **Rifiuta** conserva la decisione senza registrare pagamenti. La stessa proposta non riappare a ogni import.
- **Riapri proposta**, nella vista delle rifiutate, consente una nuova valutazione.
- La selezione multipla mostra numero e totale delle proposte. Alternative che usano gli stessi movimenti o le stesse scadenze non possono essere confermate insieme.
- **Più tardi**, o la chiusura della finestra, conserva le proposte aperte.

Il contatore raggruppa le alternative collegate nello stesso caso. Le viste sono paginate a 20 proposte. Le proposte rifiutate, confermate e superate restano consultabili con lo storico delle decisioni.

## Correttezza e autorizzazioni

La ricerca non scrive riconciliazioni. Anche le precedenti funzioni di riconciliazione automatica richiamabili dagli import ora accodano soltanto l'analisi. La sincronizzazione dello stato dei pagamenti già dichiarati da Fatture in Cloud mantiene il comportamento esistente: è distinta dall'abbinamento ai movimenti bancari.

Prima di ogni conferma vengono riletti e bloccati i record interessati; importi, residui e dati rilevanti devono corrispondere alla proposta mostrata. Una proposta non più valida viene segnata come da aggiornare e accodata nuovamente. Tutte le allocazioni di una singola proposta sono atomiche: un errore annulla anche quelle già eseguite. Due conferme simultanee della stessa proposta producono un solo pagamento. Nelle conferme multiple ogni proposta indipendente ha la propria transazione; eventuali errori vengono riportati insieme agli esiti positivi.

Le decisioni conservano utente, data e azione. Il rifiuto è collegato alla versione materiale dei dati, senza dipendere dai soli timestamp: cambiamenti sostanziali possono generare una nuova proposta. Un pagamento annullato può rendere nuovamente disponibile l'abbinamento originario.

Chi gestisce la parte economica può valutare le rette; chi gestisce la finanza può valutare rette e fornitori. I permessi vengono controllati sul contatore, sulle viste e sulle azioni, compresi gli identificativi inviati direttamente al server.

La ricerca assistita riguarda movimenti bancari in EUR, non ignorati e non sostenuti da terzi. Esclude destinazioni già saldate, scadenze annullate, note di credito, documenti compensati e proforme da verificare o sostituite. Riutilizza le regole di confronto di nominativi, familiari, causali, IBAN, riferimenti, importi e date già presenti in Arboris, con i relativi limiti di ricerca dei cumulativi.

## Elaborazione e prestazioni

Le richieste sono persistenti e deduplicate per oggetto. Vengono scritte nella stessa transazione dei dati importati; il worker viene risvegliato dopo il commit. Un rollback dell'import non lascia richieste di analisi.

Il worker elabora fino a 40 richieste per passaggio e controlla il limite di 20 secondi tra le richieste. Una singola analisi può superare tale limite. La ricerca e le decisioni sono serializzate tramite un lock nel database per evitare corse fra processi. Gli oggetti necessari alle proposte vengono caricati a gruppi, mentre contatore e popup leggono proposte già preparate: non eseguono il matching durante il caricamento della pagina.

Senza broker Celery il lavoro viene eseguito in un thread del processo web. Con `CELERY_BROKER_URL` configurato viene inviato al task `gestione_finanziaria.tasks.analyse_reconciliation_task`: serve quindi un worker Celery attivo. Un controllo ogni 30 secondi riprende le richieste rimaste in coda, anche dopo un riavvio. Gli errori di analisi prevedono un nuovo tentativo dopo due minuti e un avviso nel popup; i dettagli tecnici restano nei log.

`ARBORIS_RECONCILIATION_ENABLED=0` disattiva il worker avviato dal web, mantenendo le richieste persistenti e il comando manuale. È indipendente dai flag delle sincronizzazioni finanziarie e dei backup. I comandi di gestione e i test non avviano thread di analisi.

## Attivazione

Applicare le migrazioni prima di avviare i processi web con questa versione:

```powershell
.venv\Scripts\python.exe -B manage.py migrate
```

La migrazione `gestione_finanziaria.0016_proposte_riconciliazione` crea le tabelle e accoda i movimenti esistenti non ignorati. Non registra pagamenti e non modifica le riconciliazioni esistenti. In produzione rigenerare gli statici con la configurazione prevista dal progetto e riavviare processi web ed eventuali worker Celery.

Per elaborare una porzione di coda da riga di comando:

```powershell
.venv\Scripts\python.exe -B manage.py analyse_reconciliations --limit 100 --max-seconds 60
```

L'opzione `--scan-existing` accoda nuovamente i movimenti esistenti. Il comando rispetta i limiti indicati; ripeterlo per esaurire una coda più ampia. Non registra riconciliazioni.

Le migrazioni sono state applicate e verificate nei database di test dedicati. Al termine delle verifiche sono state applicate anche al database locale configurato nel progetto, inclusa la dipendenza `0015` già presente nel repository. Il deployment esterno non è stato aggiornato. In altri ambienti resta necessario eseguire i passaggi di attivazione sopra indicati.

È stato eseguito anche un primo lotto di analisi locale: dieci richieste elaborate, un caso disponibile, nessun errore e nessuna riconciliazione registrata. La coda restante viene ripresa dal worker all'avvio dell'applicazione.

## Verifiche eseguite

- Suite completa su PostgreSQL nuovo: **837 test, 718 superati, 119 già saltati, zero fallimenti ed errori**, circa 80 secondi esclusa la preparazione del database.
- 25 nuovi test per ordine degli import, file duplicati, conferma esplicita, rifiuto persistente, riapertura, dati cambiati, familiari, parziali, cumulativi, rollback, retry, permessi e concorrenza reale fra due connessioni.
- Aggiornato il test dell'import Fatture in Cloud per richiedere conferma esplicita prima della registrazione del pagamento.
- Verifica browser con dati fittizi e database isolato: apertura al clic, chiusura senza decisione, selezioni alternative, rifiuto, riapertura, conferma individuale e multipla, residui, totale selezionato e aggiornamento del contatore.
- `manage.py check`, `makemigrations --check --dry-run`, controllo sintattico JavaScript e `git diff --check` completati.

Per ripetere i test della funzionalità:

```powershell
.venv\Scripts\python.exe -B manage.py test gestione_finanziaria.test_reconciliation_review
```
