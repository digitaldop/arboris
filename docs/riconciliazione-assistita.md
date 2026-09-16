# Riconciliazione assistita di rette e fornitori

Implementazione del 14 settembre 2026.

## Comportamento

Gli import di movimenti bancari, fatture e scadenze accodano una ricerca di possibili abbinamenti. La ricerca parte dopo il salvataggio definitivo e funziona in entrambi gli ordini: movimento prima della scadenza o scadenza prima del movimento. Sono comprese le nuove rate generate dal piano delle iscrizioni e le modifiche a importi, identità e pagamenti collegati.

Il pulsante **Riconciliazioni da verificare**, nell'intestazione, mostra il numero dei casi aperti e viene evidenziato quando il numero è positivo. Il popup si apre soltanto al clic. Il contatore si aggiorna ogni 30 secondi quando la pagina è visibile e dopo le decisioni nel popup.

Il popup separa rette e fornitori. Per le rette ogni movimento bancario occupa una riga: il movimento è a sinistra e il menu delle rate a destra. Il menu mostra alunno, numero rata, mese di riferimento, scadenza e residuo; la rata più compatibile è selezionata inizialmente. L'analisi include tutte le rate ancora da saldare degli alunni riconosciuti, anche oltre il precedente limite di dodici alternative e con residui inferiori al movimento. Per i fornitori rimangono la scadenza/fattura a sinistra e i movimenti alternativi a destra. Cambiare candidato aggiorna dettagli, importi, residui, selezione e colore della riga. Sono gestiti abbinamenti singoli, parziali e cumulativi, anche con più movimenti: una proposta cumulativa mantiene insieme tutte le proprie allocazioni. Le combinazioni di più movimenti costituiscono un gruppo distinto e non vengono spezzate nelle singole righe.

Il mese nella causale (per esempio «Settembre 26» o «settembre 2026») viene confrontato con mese e anno di riferimento della rata, anche se la scadenza è stata spostata. Senza un anno esplicito si considera l'occorrenza del mese più vicina alla data del bonifico; senza un mese nella causale si usano il mese del movimento e la distanza dalla scadenza. Il limite al punteggio distingue i mesi coerenti da quelli non confermati o in contrasto con la causale: nome e importo da soli non rendono tutte le rate equivalenti a 100. A parità di compatibilità, periodo e distanza dalla scadenza precedono l'identificativo. La ricerca inversa non somma il bonus per un gruppo di rate quando sta esaminando una sola rata.

La scala continua va dal rosso (0) al verde (100). Al colore si affiancano il punteggio e un'indicazione testuale: bassa sotto 50, media da 50, alta da 75, molto alta da 90. I motivi sono consultabili in un dettaglio espandibile. Il punteggio è un indice di compatibilità delle regole esistenti, non una probabilità statistica.

- **Conferma abbinamento** registra il pagamento usando i servizi contabili esistenti.
- **Rifiuta** scarta tutte le alternative della riga, conservando le decisioni senza registrare pagamenti. La riga sparisce subito e il salvataggio avviene in background, senza ricaricare la pagina o mostrare il caricamento generale. In caso di errore le opzioni non salvate vengono ripristinate con un avviso; quelle salvate rimangono escluse. Ripetere un rifiuto già registrato non duplica lo storico. La stessa proposta non riappare a ogni import.
- **Riapri proposta**, nella vista delle rifiutate, consente una nuova valutazione.
- La selezione multipla mostra numero e totale delle proposte. Alternative che usano gli stessi movimenti o le stesse scadenze non possono essere confermate insieme.
- **Più tardi**, o la chiusura della finestra, conserva le proposte aperte.

Il contatore raggruppa le alternative collegate nello stesso caso. Le viste sono paginate a 20 gruppi (movimenti per le rette, destinazioni per i fornitori), mantenendo tutti i candidati della stessa riga nella medesima pagina. Dopo i rifiuti, «Carica altre proposte» recupera gli elementi spostati nella pagina corrente, senza saltarli per effetto della nuova paginazione. Le proposte rifiutate, confermate e superate restano consultabili con lo storico delle decisioni.

## Correttezza e autorizzazioni

La ricerca non scrive riconciliazioni. Anche le precedenti funzioni di riconciliazione automatica richiamabili dagli import ora accodano soltanto l'analisi. La sincronizzazione dello stato dei pagamenti già dichiarati da Fatture in Cloud mantiene il comportamento esistente: è distinta dall'abbinamento ai movimenti bancari.

Prima di ogni conferma vengono riletti e bloccati i record interessati; importi, residui e dati rilevanti devono corrispondere alla proposta mostrata. Una proposta non più valida viene segnata come da aggiornare e accodata nuovamente. Tutte le allocazioni di una singola proposta sono atomiche: un errore annulla anche quelle già eseguite. Due conferme simultanee della stessa proposta producono un solo pagamento. Nelle conferme multiple ogni proposta indipendente ha la propria transazione; eventuali errori vengono riportati insieme agli esiti positivi.

Le decisioni conservano utente, data e azione. Il rifiuto è collegato alla versione materiale dei dati, senza dipendere dai soli timestamp: cambiamenti sostanziali possono generare una nuova proposta. Un pagamento annullato può rendere nuovamente disponibile l'abbinamento originario.

Chi gestisce la parte economica può valutare le rette; chi gestisce la finanza può valutare rette e fornitori. I permessi vengono controllati sul contatore, sulle viste e sulle azioni, compresi gli identificativi inviati direttamente al server.

La ricerca assistita riguarda movimenti bancari in EUR, non ignorati e non sostenuti da terzi. Esclude destinazioni già saldate, scadenze annullate, note di credito, documenti compensati e proforme da verificare o sostituite. Riutilizza le regole di confronto di nominativi, familiari, causali, IBAN, riferimenti, importi e date già presenti in Arboris, con i relativi limiti di ricerca dei cumulativi.

## Elaborazione e prestazioni

Le richieste sono persistenti e deduplicate per oggetto. Vengono scritte nella stessa transazione dei dati importati; il worker viene risvegliato dopo il commit. Un rollback dell'import non lascia richieste di analisi.

Il worker elabora fino a 40 richieste per passaggio e controlla il limite di 20 secondi tra le richieste. Una singola analisi può superare tale limite. La ricerca, le conferme e le riaperture sono serializzate tramite un lock nel database per evitare corse fra processi. Il rifiuto blocca solo la propria proposta, senza attendere il lock generale o ricalcolare tutti i casi; i raggruppamenti vengono riallineati dalle analisi o dalle decisioni successive. L'invalidazione dell'analisi non sovrascrive i rifiuti arrivati nel frattempo.

Gli oggetti necessari alle proposte vengono caricati a gruppi, mentre contatore e popup leggono proposte già preparate: non eseguono il matching durante il caricamento della pagina. La paginazione legge le identità delle allocazioni, caricando dettagli e storico solo per le righe visualizzate. Le richieste di rifiuto e del contatore non attivano l'indicatore globale di attesa; le operazioni che richiedono una navigazione conservano il comportamento precedente.

Senza broker Celery il lavoro viene eseguito in un thread del processo web. Con `CELERY_BROKER_URL` configurato viene inviato al task `gestione_finanziaria.tasks.analyse_reconciliation_task`: serve quindi un worker Celery attivo. Un controllo ogni 30 secondi riprende le richieste rimaste in coda, anche dopo un riavvio. Gli errori di analisi prevedono un nuovo tentativo dopo due minuti e un avviso nel popup; i dettagli tecnici restano nei log.

`ARBORIS_RECONCILIATION_ENABLED=0` disattiva il worker avviato dal web, mantenendo le richieste persistenti e il comando manuale. È indipendente dai flag delle sincronizzazioni finanziarie e dei backup. I comandi di gestione e i test non avviano thread di analisi.

## Attivazione

Applicare le migrazioni prima di avviare i processi web con questa versione:

```powershell
.venv\Scripts\python.exe -B manage.py migrate
```

La migrazione `0017_refresh_tuition_proposals` accoda nuovamente gli incassi bancari in EUR per completare le alternative delle rette con le nuove regole. Non registra pagamenti. L'analisi aggiorna punteggi e motivazioni delle proposte aperte senza modificare le decisioni rifiutate. Il popup riordina anche le proposte preparate prima dell'aggiornamento, mentre il worker completa il ricalcolo. Per questa revisione occorre pubblicare codice e statici e applicare la migrazione.

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

## Revisione interfaccia e rifiuto del 14 settembre 2026

- 36 test mirati superati, inclusi 11 nuovi test in `gestione_finanziaria/test_reconciliation_interface.py`: alternative, paginazione, cumulativi, rifiuti JSON, invio senza JavaScript, candidato confermato, permessi, idempotenza e concorrenza con il worker.
- Suite completa: **886 test, 767 superati, 119 già esclusi, nessun errore o fallimento**.
- Browser su dati fittizi isolati: cambio candidato e colore, conservazione della selezione, rifiuto individuale e multiplo, storico, conferma del candidato selezionato e assenza di errori JavaScript. Con risposta ritardata di quattro secondi, la riga risulta già nascosta al primo controllo (circa 300 ms, comprensivi dell'automazione). Le altre righe rimangono utilizzabili e non compare il caricamento globale. Verificati ripristino dopo errore HTTP 503 simulato e salvataggio durante il cambio di scheda Rette/Fornitori.
- Controlli Django, migrazioni, sintassi JavaScript e Git superati. Nessuna nuova migrazione. Aggiornate le versioni degli asset statici; pubblicazione su Render da eseguire.

## Revisione delle rate per movimento del 14 settembre 2026

- 65 test mirati superati: mese nella causale, anno esplicito e arretrati a cavallo d'anno, parità dei vecchi punteggi, oltre dodici alternative, rate parzialmente saldate, esclusione delle saldate, aggiornamento delle proposte aperte e conservazione dei rifiuti.
- Suite completa su PostgreSQL dedicato nuovo: **907 test, 788 superati, 119 esclusi, nessun fallimento o errore** (131 secondi). La prima esecuzione sul database di test riutilizzato è stata interrotta dopo un rallentamento; la verifica completa sul database nuovo è terminata regolarmente.
- Verifica browser su dati fittizi isolati: settembre preselezionato con vecchie proposte tutte a 100; movimento a sinistra e menu rate a destra; cambio a novembre; selezione conservata e totale aggiornato a 60 EUR con 40 EUR residui sul movimento; esclusione delle selezioni incompatibili; rifiuto di tutte le alternative, storico, riapertura e conferma della sola rata scelta. Nessun errore JavaScript.
- `manage.py check`, `makemigrations --check --dry-run` e `git diff --check` superati. Migrazione `0017` applicata anche al database locale. Gli asset sono alla versione 3. Nessun pagamento reale registrato e nessun deployment esterno eseguito.
- Il database locale non contiene l'alunna e il movimento dello screenshot: il difetto di ordinamento è stato riprodotto con dati fittizi; non è stato possibile accertare lo stato originario della rata di settembre nell'ambiente esterno.

## Quote di preiscrizione dalla lista movimenti, 16 settembre 2026

- Verificato in sola lettura il movimento segnalato: quota di preiscrizione da 300 EUR ancora da pagare, dodici rate mensili da 350 EUR e causale con «quota iscrizione». La quota senza scadenza veniva penalizzata dall'ordinamento per data ed esclusa dal limite di dodici proposte.
- Il confronto condiviso riconosce iscrizione, preiscrizione e le varianti separate da spazio o trattino. La quota coerente con la causale non viene penalizzata per l'assenza di scadenza; le mensilità hanno compatibilità ridotta quando la causale indica soltanto l'iscrizione. Per causali miste, come «preiscrizione e retta settembre», restano applicabili anche i criteri delle rette. Importo e identità dello studente/familiare continuano a determinare il punteggio effettivo.
- La pagina di riconciliazione del movimento mostra tutte le rate e quote candidate senza il precedente limite di dodici. Le regole condivise si applicano anche alla ricerca dalla rata e all'ordinamento delle alternative nel popup.
- 13 nuovi test, inclusi il caso con dodici mensilità, causali generiche e miste, acconti, identità approssimata, quote saldate, vecchie proposte e conferma della sola preiscrizione. Verifica mirata su PostgreSQL isolato: **92 test, 88 superati e 4 esclusi, nessun fallimento o errore**. `manage.py check` e `git diff --check` superati.
- Nessuna nuova migrazione. La correzione è locale e richiede la pubblicazione del codice su Render. Nessun pagamento reale registrato.
