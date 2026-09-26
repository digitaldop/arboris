# Permessi dei ruoli per modulo e pagina

In **Impostazioni generali → Gestione Account → Ruoli**, ogni modulo ha un livello
predefinito: divieto di accesso, solo visualizzazione, visualizzazione e azione.
Ogni pagina può ereditare il livello o sostituirlo con uno dei tre livelli.
Le eccezioni possono sia limitare sia ampliare il livello del modulo.

Esempio Segreteria:

| Modulo / pagina | Livello |
| --- | --- |
| Anagrafica | Solo visualizzazione |
| Economia | Divieto di accesso |
| Economia → Matrice rette / Panoramica rette | Solo visualizzazione |
| Gestione finanziaria | Divieto di accesso |
| Gestione finanziaria → Movimenti bancari | Solo visualizzazione |

I comandi collettivi si applicano alle pagine del singolo modulo oppure a tutte
le pagine. «Deseleziona tutto» imposta divieto; «Ripristina ereditarietà» elimina
le eccezioni. Il controllo completo prevale sulle impostazioni granulari e viene
segnalato nella schermata. Un ruolo inattivo o un modulo disattivato non concede
accesso, anche in presenza di eccezioni.

Le abilitazioni speciali preesistenti rimangono il valore ereditato per
Comunicazioni alle famiglie, Backup, Cronologia e Feedback. Un livello esplicito
sulla pagina prevale su queste abilitazioni. Gli account senza ruolo continuano
a usare i permessi del profilo utente.

## Applicazione

`sistema/permission_catalog.py` associa le pagine ai nomi delle URL di elenco,
dettaglio e azione. Le chiavi coincidono con quelle della navigazione, salvo le
alias dichiarate. Nuove URL protette devono essere registrate nel catalogo:
un test controlla la copertura e l'assenza di duplicati.

Il middleware e i decoratori applicano i livelli anche ad accessi diretti,
richieste non sicure e modalità `?edit=1`. I callback OAuth richiedono gestione.
I toggle generici verificano la pagina associata al modello, mai il solo modulo.
Menu, ricerca globale, home e contenuti provenienti da altri moduli nel calendario
rispettano le autorizzazioni. Le ricevute personali di lettura delle notifiche
sono consentite in visualizzazione; non modificano i dati gestionali.
Login, informazioni legali, crediti pubblici e webhook con autenticazione propria
mantengono il loro flusso dedicato.

La migrazione `sistema.0013` aggiunge `permessi_pagine` e converte le precedenti
voci di menu disabilitate in divieti di accesso. Le altre pagine mantengono i
livelli ereditati. Non assegna nuovi ruoli agli account.

Verifiche: `python manage.py test sistema.test_page_permissions` e suite di
regressione dei moduli che usano i permessi.
