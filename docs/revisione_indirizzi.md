# Revisione degli indirizzi condivisi

## Struttura trovata

Arboris usa Django 5.2.13 e PostgreSQL. `Indirizzo` aveva già strada, civico,
FK a Regione, Provincia, Citta e CAP, più il CAP testuale. Il salvataggio derivava
Provincia/Regione dalla città. Non esistevano vincoli di identità dell'indirizzo:
il controllo dei duplicati era un suggerimento aggirabile con «Crea comunque nuovo».
La modifica aggiornava direttamente il record condiviso.

La vecchia tabella Famiglia è già stata rimossa dalle migration precedenti.
Le famiglie sono componenti connesse del grafo delle relazioni attive
`StudenteFamiliare`, rappresentate da `LogicalFamilySnapshot`. Il precedente
indirizzo principale era quello più frequente tra i componenti, calcolato ogni volta.

Relazioni effettive individuate:

* `Persona.indirizzo`, condivisa con il profilo `Familiare` e gli eventuali profili lavorativi;
* `Studente.indirizzo`;
* `AnagraficaIndirizzo.indirizzo`: contatti multipli con etichetta, note e priorità,
  associabili genericamente a persone, familiari, studenti e dipendenti;
* `sistema.Scuola.indirizzo_sede_legale` e `indirizzo_operativo`.

I dipendenti usano Persona e i contatti generici; gli indirizzi testuali dei
fornitori non sono FK a Indirizzo. Non sono emersi serializer/API di creazione
alternativi. Gli import territoriali continuano a usare Regione/Provincia/Citta/CAP;
il loro controllo della presenza di indirizzi resta compatibile. Documenti, dashboard,
stampe e ricerca continuano a utilizzare i modelli e le property esistenti.

## Implementazione

### Identità e cambio indirizzo

`address_normalization.py` contiene la normalizzazione v1, condivisa con il servizio,
la migration e il suggeritore preesistente. Gestisce Unicode, maiuscole, spazi,
punteggiatura della strada, prefisso `n.`, civico in fondo alla strada e suffissi
come `25A`, `25 A`, `25/A`. `25`, `25/A`, `25/B`, intervalli e interni restano distinti.
Non applica correzioni fonetiche o abbreviazioni ambigue dei nomi delle strade.

L'identità SHA-256 comprende strada/civico normalizzati, città, CAP e riferimenti
territoriali. `unique_indirizzo_normalizzato` è un vincolo UNIQUE PostgreSQL;
`indirizzo_lookup_idx` indicizza città/strada/civico. Il servizio
`get_or_create_normalized_address` usa `transaction.atomic()` e `get_or_create`,
che recupera il record vincente dopo un inserimento concorrente.

Form, popup e admin riusano il record esistente. Il model normalizza anche gli
inserimenti diretti e `bulk_create`. Aggiornamenti diretti o in blocco dei record
condivisi sono rifiutati; l'admin permette consultazione e creazione/riuso, non
modifica o cancellazione diretta. Cambiare indirizzo dal popup restituisce il nuovo
ID al solo campo chiamante, da confermare salvando la scheda del soggetto.
Dal catalogo indirizzi si ottiene un altro record senza spostare associazioni.

**Limite deliberato:** dati senza Comune o senza civico non provano l'identità di
un'abitazione: sono conservati con chiave NULL e non vengono accorpati. Anche dati
territoriali storici incoerenti richiedono verifica. CAP diversi rimangono distinti.
Le normali creazioni dal form richiedono una città del catalogo. Un CAP manuale
di cinque cifre è ammesso anche se manca dal catalogo, senza creare nuove entità CAP.

### Indirizzo della famiglia

`ResidenzaFamiglia` contiene una FK `indirizzo_principale`. Studenti e familiari
possono condividere queste impostazioni, mentre l'appartenenza alla famiglia
continua a dipendere dalle relazioni esistenti. Non è stata reintrodotta la vecchia
tabella Famiglia né cambiata l'identità dei nuclei o dei documenti.

Il pulsante **Indirizzo principale** nella scheda famiglia permette ricerca e
inserimento manuale. Nei form completi, popup e formset è disponibile
**Usa l'indirizzo principale della famiglia**. Il checkbox è esplicito perché
i contatti multipli possono contenere anche altri indirizzi, che devono rimanere
conservati e non essere scambiati per un'eccezione alla residenza familiare.

`indirizzo_effettivo` usa il principale familiare quando il checkbox è attivo;
altrimenti mantiene la precedenza dei contatti personali e della FK individuale,
con fallback al principale se manca un indirizzo personale. I campi personali
storici non vengono azzerati dalla migration. I componenti già dotati di un proprio
indirizzo devono scegliere esplicitamente l'eredità per seguire futuri cambiamenti.

Una nuova relazione collega le impostazioni compatibili. Se unisce nuclei con
principali diversi, li mantiene separati e mostra il conflitto nella famiglia.
La modifica del principale riguarda solo i componenti attualmente nel gruppo:
una precedente separazione del nucleo non sposta persone rimaste fuori dal gruppo.
Nessun vecchio indirizzo o impostazione orfana è eliminato automaticamente.

### Geoapify

`/api/address-autocomplete/` è protetto dai permessi anagrafici. Cerca anche nel
database locale, senza dipendere da Geoapify. Il provider viene chiamato solo per
query di almeno quattro caratteri, con debounce browser di 350 ms, massimo cinque
risultati esterni, filtro Italia e lingua italiana; il Comune selezionato contestualizza
la ricerca. Timeout connessione/lettura: 2/4 secondi; cache: 120 secondi; limite
indicativo: 30 richieste esterne al minuto per utente. Su più processi, una cache
condivisa rende il limite globale; con la cache locale predefinita vale per processo.

Il matching usa sigla/nome della provincia, nomi comunali normalizzati e CAP per
disambiguare. Omonimie, risultati sconosciuti o contraddittori richiedono scelta
manuale: non vengono creati Comuni, Province, Regioni o CAP da testo esterno.
Le coordinate e il provider ID sono opzionali, validati e trasmessi al form in un
token firmato con scadenza; una modifica manuale non conserva coordinate riferite
alla vecchia selezione. La chiave API non compare nelle risposte o nel frontend.
Errori, assenza della chiave e timeout lasciano disponibili ricerca locale e campi manuali.

Parametri e formato del provider seguono la
[documentazione ufficiale Geoapify Address Autocomplete](https://apidocs.geoapify.com/docs/geocoding/address-autocomplete/).

## Migration e dati

* `0008_shared_addresses`: aggiunge campi, indice, impostazioni familiari e archivio
  delle unioni. Non elimina colonne o tabelle esistenti.
* `0009_normalize_and_share_addresses`: normalizza, unisce duplicati certi,
  reindirizza tutte le FK del registro storico Django e poi applica UNIQUE;
  inizializza le impostazioni dei nuclei conservando le associazioni individuali.

La deduplicazione è transazionale. Su PostgreSQL blocca le scritture nelle tabelle
coinvolte durante l'operazione. Sceglie l'ID minore; prima di rimuovere un duplicato
ormai privo di riferimenti conserva tutti i suoi campi e gli ID delle associazioni
originali in `IndirizzoArchivioMigrazione`. Non cancella record per cascata.
Ripetere le funzioni sui dati già migrati non crea altre unioni o impostazioni.

La data migration è intenzionalmente **non reversibile automaticamente**: un
rollback non deve riassegnare collegamenti che gli utenti potrebbero avere cambiato
dopo il deploy. Per ripristinare integralmente lo stato precedente usare il backup;
l'archivio delle unioni consente verifiche puntuali.

Verifica in sola lettura sul database locale esistente: **32 indirizzi, nessun
incompleto e nessun duplicato potenziale**. Non sono state applicate migration
né deduplicazioni al database esistente o alla produzione. Le migration sono state
applicate solo a database PostgreSQL di test separati, con dati fittizi.

Il comando `python manage.py verifica_indirizzi` è utilizzabile prima e dopo il
deploy, non scrive dati e restituisce conteggi e ID, senza stampare indirizzi personali.

## Render

1. Configurare `GEOAPIFY_API_KEY` nelle variabili d'ambiente del servizio web.
   L'assenza della variabile disabilita solo la ricerca esterna.
2. Verificare lo stato delle migration e fare un backup PostgreSQL prima del deploy.
   Il database deve essere allineato alle migration precedenti: la vecchia `0002`
   conteneva già rimozioni di tabelle legacy e non è stata modificata da questa revisione.
3. Eseguire le nuove migration in una finestra senza scritture applicative e con
   i vecchi worker arrestati. La deduplicazione acquisisce lock; evitare che una
   versione precedente reinserisca record privi della nuova chiave durante il rollout.
4. Il `build.sh` esistente esegue già `collectstatic` e `migrate`: coordinare questo
   passaggio con la finestra di deploy. Non sono necessarie nuove dipendenze Python.
5. Verificare una ricerca reale con la propria chiave Geoapify e le eventuali
   restrizioni di accesso configurate nel progetto Geoapify.

## File interessati

* Backend: `anagrafica/models.py`, `forms.py`, `views.py`, `urls.py`, `admin.py`,
  `signals.py`, `contact_services.py`, `family_logic.py`.
* Nuovi servizi: `address_normalization.py`, `address_services.py`,
  `address_autocomplete.py`, `family_address_services.py` in `anagrafica/`.
* Nuove migration `0008`, `0009`; comando `management/commands/verifica_indirizzi.py`;
  test `anagrafica/test_addresses.py`.
* Configurazione: `arboris/settings.py`, `sistema/permission_catalog.py`.
* Template: form indirizzo completo/popup, form famiglia/familiare/studente,
  popup studente, i due formset studenti condivisi in `templates/common/inlines`,
  `templates/base.html` e `popup_base.html`.
* Nuovi template: `famiglie/famiglia_indirizzo.html`, `indirizzi/address_search.html`,
  `partials/family_address_choice.html` in `templates/anagrafica/`.
* JavaScript: `static/js/core/address-autocomplete.js`, `address-city-caps.js`,
  `family-address-choice.js`; stile in `static/css/style.css`.

## Verifiche

Risultati finali del 27 settembre 2026:

| Controllo | Esito |
| --- | --- |
| Suite completa, versione finale | 996 test, OK, 119 skip previsti dalla suite; 126,720 secondi |
| Nuovi test indirizzi e test performance | 31 test, tutti OK (26 nuovi + 5 performance) |
| `python manage.py check` | Nessun problema |
| `python manage.py makemigrations --check --dry-run` | Nessuna modifica mancante |
| `node --check` sui tre nuovi JavaScript | OK |
| `git diff --check` | OK |
| Migration su PostgreSQL separato | OK, inclusi riuso idempotente e archivio delle unioni |
| Race tra due connessioni PostgreSQL | Un solo record creato |

La suite completa è stata eseguita con impostazioni temporanee che puntavano a
PostgreSQL locale e a un database di test dedicato, creato e rimosso dal runner.
Per velocizzare i test funzionali completi è stato usato l'hasher MD5 **solo nelle
impostazioni di test**; i 31 test mirati sono passati anche con l'hasher ordinario.
La configurazione password dell'applicazione non è cambiata.

La prima esecuzione con `--keepdb` ha evidenziato un record di audit del provider
bancario rimasto dopo il flush di un test transazionale, che falsava i test della
cronologia, oltre a una fixture di etichetta non autosufficiente nei nuovi test.
La fixture è stata corretta; l'intera suite è poi passata su database nuovo.
Le righe `RuntimeError: test interruption` nel log appartengono a un errore
intenzionalmente simulato dai test del worker finanziario.

Il browser di prova ha usato esclusivamente un database separato con nomi fittizi.
È stato verificato il riuso
locale senza provider, il riempimento dei campi, il salvataggio senza duplicati,
il form dell'indirizzo principale e il checkbox nei formset, con persistenza di
`indirizzo=NULL`, `usa_indirizzo_famiglia=True` e corretto indirizzo effettivo.

La chiamata reale a Geoapify richiede verifica con la chiave di produzione:
i test automatici usano risposte simulate valide, errori, timeout e dati non riconciliabili.
