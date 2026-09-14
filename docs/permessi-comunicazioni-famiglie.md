# Permesso per le comunicazioni alle famiglie

In **Gestione Account → Ruoli → modifica ruolo → Permessi speciali** è disponibile l'opzione **Comunicazioni alle famiglie**.

L'abilitazione consente agli utenti del ruolo di aprire la funzione nella sezione Anagrafiche, preparare e inviare comunicazioni e consultare storico e dettaglio degli invii. Funziona con Anagrafica in sola visualizzazione, gestione o senza accesso, indipendentemente dal livello del modulo Economia.

L'autorizzazione viene verificata anche sulle richieste dirette alle pagine e sull'invio del modulo. La revoca vale dalla richiesta successiva. L'abilitazione non concede la modifica delle anagrafiche, l'accesso ai dati economici o la configurazione SMTP. Superuser e ruoli attivi con controllo completo mantengono l'accesso; un ruolo inattivo non concede questa funzione.

L'eventuale esclusione esplicita della voce tramite **Voci menu** continua a nascondere il collegamento: tale impostazione riguarda la visibilità, mentre **Comunicazioni alle famiglie** è il permesso di accesso.

## Implementazione e migrazione

Il campo `accesso_comunicazioni_famiglie` viene impostato sul ruolo e copiato nel profilo quando si assegna o aggiorna un ruolo, come gli altri permessi. Per gli utenti con ruolo, l'autorizzazione effettiva usa sempre il valore corrente del ruolo. Il campo del profilo serve anche agli account preesistenti senza ruolo associato.

La migrazione `sistema.0012_accesso_comunicazioni_famiglie` abilita inizialmente la funzione per i ruoli e i profili senza ruolo che già disponevano della gestione di Economia o del controllo completo. I nuovi ruoli richiedono l'abilitazione esplicita. Gli URL esistenti rimangono validi; le pagine vengono classificate nel modulo Anagrafica e i controlli di sola lettura usano il permesso specifico per questa funzione.

La migrazione è stata applicata al database locale il 14 settembre 2026.

Negli ambienti da aggiornare applicare la migrazione prima di avviare questa versione:

```powershell
.venv\Scripts\python.exe -B manage.py migrate
```

## Verifiche

I test `sistema.test_family_communication_permissions` verificano i tre livelli di Anagrafica, menu, accesso diretto, storico, invio simulato, revoca, ruoli inattivi, controllo completo, salvataggio dei ruoli, assegnazione agli utenti e conservazione degli accessi preesistenti. Gli invii nei test sono simulati: non vengono spedite email.

Verifica completa su un nuovo database PostgreSQL: 849 test totali, 730 superati e 119 già esclusi, senza errori. Superati anche i controlli Django, di coerenza delle migrazioni e delle differenze Git. Lo storico gestisce ora anche comunicazioni il cui utente mittente non è più presente.

```powershell
.venv\Scripts\python.exe -B manage.py test sistema.test_family_communication_permissions economia.tests.ComunicazioniFamiglieTests
```
