# Calendario: visibilità in base ai permessi

Gli eventi inseriti direttamente nel calendario restano condivisi, anche quando
sono stati creati da un altro utente. Rimangono applicate le impostazioni di
attività, visibilità e visualizzazione nella dashboard già previste dal calendario.

Le informazioni provenienti dagli altri moduli richiedono almeno il permesso di
visualizzazione sul modulo di origine:

| Informazione | Modulo richiesto |
| --- | --- |
| Scadenze delle rette | Rette scolastiche (`economia`) |
| Scadenze dei fornitori | Gestione finanziaria (`gestione_finanziaria`) |
| Scadenze dei documenti anagrafici | Anagrafica |
| Attività delle famiglie interessate | Famiglie interessate |
| Compleanni di studenti e familiari nella dashboard | Anagrafica |
| Compleanni del personale nella dashboard | Gestione amministrativa |

Si usano i permessi effettivi del ruolo assegnato; in assenza di un ruolo si usano
quelli del profilo utente. Il controllo completo e i superutenti conservano accesso
ai dati dei moduli abilitati. Un modulo disattivato resta escluso. Il permesso
speciale per le comunicazioni alle famiglie non concede accesso alle scadenze.

Il controllo avviene sul server, prima delle query alle fonti non consentite, e
si applica all'agenda, ai dati JSON inviati al browser, agli elenchi con ricerca e
filtri, ai contatori delle categorie e al widget della dashboard. Le modifiche dei
permessi vengono recepite dalla richiesta successiva, dopo l'aggiornamento della
pagina. Senza un utente identificato i costruttori dei dati escludono le fonti
automatiche.

Il controllo riguarda l'origine del dato: assegnare manualmente la categoria
«Scadenze fornitori» a un evento condiviso non rende quell'evento una scadenza
finanziaria riservata.

I test in `calendario/test_permissions.py` verificano ruoli con accessi misti,
visualizzazione e gestione, revoca dei permessi, profili senza ruolo, ruoli
disattivati, controllo completo, moduli disabilitati, contatori e filtri. Nessuna
nuova migrazione del database è necessaria per questa modifica.

Verifica del 14 settembre 2026: 35 test mirati (33 superati, 2 già esclusi);
suite completa PostgreSQL di 875 test (756 superati, 119 già esclusi), nessun
fallimento o errore. Superati anche `manage.py check`,
`makemigrations --check --dry-run` e `git diff --check`. La versione locale deve
essere pubblicata su Render per applicare la correzione al sito in produzione.
