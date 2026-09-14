# Comunicazioni mirate per classe

Nella pagina **Anagrafiche → Comunicazioni alle famiglie**, dopo gli anni scolastici, la sezione **Seleziona per classe** permette di scegliere:

- **Tutte le classi**, comprese le iscrizioni senza classe assegnata.
- Una o più classi: vengono inclusi i destinatari dei figli iscritti ad almeno una delle classi scelte.
- Una o più pluriclassi già configurate: vengono considerate le iscrizioni effettivamente assegnate a quei gruppi.
- **Classe non assegnata**, per individuare separatamente queste iscrizioni.

Selezionare una classe attiva automaticamente la modalità **Classi selezionate** e seleziona i destinatari corrispondenti. Il cambio del filtro aggiorna immediatamente l'elenco e la selezione; successivamente si possono escludere singole persone. **Seleziona tutti nel filtro** include soltanto i destinatari visibili; **Deseleziona tutti** mantiene la selezione vuota anche aggiornando l'anteprima. Deselezionare l'ultima classe mostra un elenco vuoto, senza passare automaticamente a tutte le classi.

I contatori riepilogano le iscrizioni e gli indirizzi disponibili nel filtro. Il riepilogo sopra l'elenco indica separatamente i destinatari selezionati e gli indirizzi email unici. Un genitore collegato a più figli riceve una sola copia per indirizzo, anche quando i figli appartengono a classi diverse o i filtri si sovrappongono.

Cambiare anno scolastico richiede **Aggiorna destinatari** prima dell'invio. La bozza di oggetto e messaggio resta nel modulo. Le opzioni di classe derivano dalle iscrizioni attive e non annullate degli anni scelti; le classi senza iscrizioni ammesse non vengono proposte.

Il server ricostruisce i destinatari e applica nuovamente il filtro all'invio. Classi non valide, destinatari fuori dal filtro e assegnazioni cambiate dopo l'anteprima bloccano l'intero invio e richiedono una verifica della selezione. Il client email in CCN usa anch'esso soltanto gli indirizzi selezionati nel filtro. Lo storico conserva le informazioni di classe e pluriclasse nei dettagli dei destinatari.

## Verifiche e pubblicazione

Sono stati aggiunti 14 test per singole classi, unione di classi, pluriclassi, fratelli, indirizzi duplicati, assenza di classe, anni scolastici, selezioni vuote, aggiornamenti delle iscrizioni e validazione dell'invio. Gli invii nei test sono simulati. Il caricamento di iscrizioni, classi, familiari e contatti usa quattro query nella prova di regressione, senza query aggiuntive per ciascun familiare.

Suite completa su PostgreSQL, inclusa la successiva correzione dei permessi del calendario: **875 test totali, 756 superati, 119 già esclusi, nessun fallimento o errore**. Nel browser sono stati verificati i filtri, le selezioni individuali, la conservazione della bozza, la selezione vuota e il cambio degli anni. Superati anche i controlli Django, JavaScript e Git.

Non sono necessarie nuove migrazioni. Le modifiche sono nel progetto locale; per renderle disponibili su Render occorre pubblicare questa versione con i nuovi asset statici. Lo script `build.sh` del progetto include già `collectstatic`.
