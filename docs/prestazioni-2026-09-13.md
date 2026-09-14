# Ottimizzazione dei caricamenti — 13 settembre 2026

Le modifiche riducono il lavoro ripetuto sul database, gli aggiornamenti del DOM e i dati trasferiti al browser. Sono state verificate localmente su PostgreSQL, con dati sintetici e database di test separati. Nessuna migrazione dello schema è necessaria.

## Misure prima e dopo

Riferimento iniziale: commit `d56fa318ca16b3f31352304361274cba3b146c92`.

Ogni misura riporta la mediana di cinque esecuzioni dopo un riscaldamento iniziale, sullo stesso computer e sugli stessi dati. Ogni nucleo contiene un genitore, uno studente e un'iscrizione con tariffa. Le misure riguardano le funzioni di preparazione dei dati, **non l'intero caricamento HTTP né la produzione**.

| Elaborazione | Nuclei | Query prima → dopo | Tempo prima → dopo |
| --- | ---: | ---: | ---: |
| Famiglie logiche | 1 | 8 → 6 | 24,03 → 34,72 ms |
| Famiglie logiche | 12 | 63 → 6 | 203,66 → 40,76 ms |
| Famiglie logiche | 50 | 253 → 6 | 779,48 → 74,54 ms |
| Dashboard economica | 1 | 31 → 8 | 53,98 → 13,95 ms |
| Dashboard economica | 12 | 339 → 8 | 569,27 → 19,40 ms |
| Dashboard economica | 50 | 1.403 → 8 | 2.266,18 → 45,19 ms |

Il caricamento in blocco ha un piccolo costo iniziale: con un unico nucleo il percorso famiglie risulta più lento in questa misura. Il beneficio aumenta al crescere dei dati; con 50 nuclei il tempo misurato diminuisce di circa il 90% per le famiglie e il 98% per la dashboard economica.

| Risorsa | Prima | Dopo |
| --- | ---: | ---: |
| CSS principale, non compresso | 1.031.949 byte | 821.730 byte |
| CSS principale, gzip | 120.090 byte | 109.386 byte |
| HTML login, prova con `Accept-Encoding: gzip` | 4.821 byte | 1.444 byte |

Il CSS diminuisce del 20,4% prima della compressione e dell'8,9% dopo gzip. La dimensione gzip dell'HTML può variare leggermente per il padding di sicurezza di Django.

## Interventi

- **Famiglie:** studenti, genitori e indirizzi effettivi vengono letti in blocco. Restano l'ordinamento del database, i legami transitivi, le persone isolate e l'esclusione dei collegamenti inattivi. Il conteggio dei nuclei nella home usa soltanto gli identificativi e una query, senza costruire tutte le schede anagrafiche.
- **Dashboard economica:** ordine dei figli, tariffe e regole per le iscrizioni in corso d'anno vengono preparati insieme. Le informazioni restano sulle sole istanze usate per il riepilogo; non viene introdotta una cache condivisa di importi o pagamenti. La selezione delle tariffe mantiene la parentela diretta e l'ordinamento del calcolo originario.
- **Iscrizioni:** il conteggio delle rate viene calcolato nella query della lista, eliminando un accesso al database per ciascuna riga.
- **Note:** il gestore delle modifiche osserva soltanto nuovi campi e cambiamenti di sola lettura. Non rielabora la pagina in risposta al proprio rendering. La prova browser iniziale riproduceva 84 mutazioni in una finestra di 200 ms dopo la modifica del popup; dopo la correzione le mutazioni a riposo sono zero.
- **Notifiche:** le normali navigazioni riutilizzano il riepilogo appena generato dal server, evitando le due richieste immediatamente successive al caricamento. Gli aggiornamenti restano attivi all'apertura dei menu, al ritorno alla scheda e al ripristino dalla cache della cronologia.
- **Backup:** il middleware avvia un controllo in background, senza attendere `pg_dump` prima di restituire la pagina. Restano i controlli esistenti di frequenza e il blocco nel database contro le esecuzioni sovrapposte. Il controllo web parte al massimo una volta al minuto per processo.
- **Sincronizzazioni finanziarie:** il controllo su richiesta viene limitato prima di creare il thread; le connessioni del worker vengono chiuse al termine del lavoro.
- **Risorse comuni:** gzip per le risposte dinamiche, caricamento dei font senza bloccare il rendering e identico identificativo del CSS per pagina principale, popup e login.
- **Build statica:** minificazione sintattica dei CSS con [rcssmin 1.2.2](https://pypi.org/project/rcssmin/1.2.2/), prima del calcolo degli hash e della compressione WhiteNoise. I sorgenti restano leggibili; l'ordine delle regole è preservato. La build ha elaborato 243 risorse nel manifest.

## Verifiche

- 11 nuovi test backend superati: crescita delle query, correttezza dei riepiloghi, ordine delle tariffe, conteggio rate, esecuzione asincrona, limitazione dei thread, indipendenza dei backup dalle sincronizzazioni, chiusura connessioni e minificazione con URL, hash e gzip coerenti.
- 8 verifiche nel browser superate: inattività del DOM, formattazione, passaggio lettura/modifica, anteprima, eventi input, aggiunta dinamica dei campi, serializzazione del testo e inattività dopo modifica del popup.
- `collectstatic` con `DEBUG=False` e il nuovo storage: completato.
- Login attraverso il middleware con `DEBUG=False`: HTTP 200 e risposta gzip correttamente decodificabile.
- `manage.py check`, `makemigrations --check --dry-run` e controllo sintattico dei due JavaScript modificati: superati.
- Suite completa prima della correzione dei problemi preesistenti: **804 test, 680 superati, 119 saltati, 4 fallimenti e 1 errore già presenti nella versione iniziale**. Nessuna nuova regressione rilevata.
- Ultimo controllo mirato, incluse le rifiniture finali e i test esistenti dello scheduler PSD2: **24 test superati**.

I cinque problemi preesistenti sono stati corretti nel successivo intervento richiesto:

1. **Archivio storico:** test aggiornati ai modelli `Studente`, `Familiare` e `StudenteFamiliare`. La loro riattivazione ha confermato due difetti del servizio: mancavano gli snapshot delle famiglie logiche e la lettura di `luogo_nascita_id` sul profilo familiare generava un errore. Ora le famiglie vengono salvate con componenti, nome e indirizzo; le etichette sono calcolate una sola volta e riutilizzate per familiari, studenti, iscrizioni e rate. I test verificano corrispondenza con l'anteprima, fratelli, collegamenti inattivi, luogo di nascita e conservazione dei dati dopo modifiche anagrafiche.
2. **Ricerca nazioni:** la fixture Francia ora valorizza esplicitamente `nome_nazionalita="Francese"`, come richiesto dal modello attuale. Un test aggiuntivo verifica che una nazionalità assente rimanga vuota.
3. **Condizione predefinita delle iscrizioni:** il test usa date esplicite, incluso il passaggio dal 31 agosto al 1º settembre. Verifica così anno e condizione corretti senza dipendere dal giorno di esecuzione.
4. **Previsioni ricorrenti:** le date dei test del budget sono coerenti con l'anno scolastico delle fixture. Corretto anche il servizio: la data di riferimento passata al budget viene rispettata nella scelta dell'anno scolastico, con una regressione dedicata su due anni.
5. **Voci di budget inattive:** lo stesso allineamento delle date ripristina la verifica di visibilità, conteggio, esclusione dai totali e riattivazione della voce nel periodo selezionato.

Le correzioni dell'archivio si applicano alle nuove archiviazioni; gli archivi già congelati non vengono riscritti. Non sono necessarie migrazioni dello schema.

**Verifica finale delle correzioni:** suite completa su un nuovo database PostgreSQL di test, **812 test totali: 693 superati, 119 già saltati, zero fallimenti e zero errori**, in 83,1 secondi (esclusa la preparazione del database). I quattro test originali dell'archivio sono nuovamente eseguibili e sono stati aggiunti quattro test di regressione. Anche `manage.py check` è superato.

Il primo confronto aveva anche un fallimento del test dello scheduler causato dalla variabile d'ambiente del runner temporaneo. Eliminata quella forzatura e usato il riconoscimento standard dei comandi di test, il test passa. La suite completa è stata rieseguita su un database nuovo: il riuso con `--keepdb` lasciava una voce di audit del provider generata dai segnali `post_migrate`, interferendo con i test che richiedono un registro vuoto.

## Ripetere i controlli

```powershell
.venv\Scripts\python.exe -B manage.py test anagrafica.test_performance sistema.test_performance
.venv\Scripts\python.exe -B manage.py test archivio_storico.tests anagrafica.tests.AjaxCercaCittaTests anagrafica.tests.IscrizioneInlineDefaultsTests gestione_finanziaria.tests.BudgetingGestioneFinanziariaTests
.venv\Scripts\python.exe -B tests\browser\serve_loading.py
```

Aprire [la verifica locale delle note](http://127.0.0.1:8796/). Il server espone soltanto la pagina di test e i suoi due asset. Per confrontare il comportamento iniziale:

```powershell
.venv\Scripts\python.exe -B tests\browser\serve_loading.py --baseline d56fa318ca16b3f31352304361274cba3b146c92
```

Aprire quindi `/?before=1`. Terminare il server con `Ctrl+C`.

## Messa in esercizio e limiti

Installare le dipendenze aggiornate e rigenerare gli statici con `DEBUG=False`; lo script `build.sh` esistente esegue già installazione e `collectstatic`. La minificazione è attiva nello storage di produzione. Per riutilizzare gli hash e la cache è necessario distribuire il manifest insieme agli asset generati.

Il backup web resta una modalità best effort: un riavvio del processo può interrompere il thread. Il comando `run_scheduled_database_backups` resta utilizzabile con uno scheduler esterno, come `run_scheduled_psd2_sync` per la sincronizzazione. `ARBORIS_BACKGROUND_BACKUP_ENABLED=0` disattiva il controllo web dei backup; il flag esistente `ARBORIS_BACKGROUND_SCHEDULER_ENABLED` continua a governare le sole sincronizzazioni finanziarie. I comandi espliciti restano disponibili.

Per quantificare il beneficio reale servono misure nell'ambiente di produzione con volumi rappresentativi. Le liste complete continuano a generare HTML proporzionale ai risultati; il CSS principale rimane ampio. Paginazione, suddivisione degli stili per pagina e indici guidati dai piani di esecuzione possono essere valutati sulla base dei tempi residui, dei filtri effettivamente usati e del comportamento richiesto alle liste.
