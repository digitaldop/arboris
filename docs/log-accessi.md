# Login e pagine visualizzate

Il menu **LOG → Elenco** comprende le operazioni sui dati, i **Login** riusciti
e le **Visualizzazioni pagina**, con utente, data e ora. Il filtro **Operazione**
separa i tipi di evento; **Ricerca** permette di cercare il nome dell'utente,
il suo username oppure il percorso della pagina. Restano disponibili il filtro
per modulo e la lettura delle singole voci dal menu LOG.

Le notifiche rapide e il loro contatore mostrano solo le attività degli altri
account, inclusi gli altri amministratori. Le proprie attività restano nella
cronologia generale e non richiedono di essere segnate come lette. Questa regola
si applica anche ai login e alle pagine visualizzate.

Una visualizzazione corrisponde a una richiesta GET autenticata per cui il server
ha restituito una pagina HTML completa con esito positivo. Sono comprese le schede
aperte nei popup tramite iframe. Ogni caricamento o ricaricamento genera un evento;
il percorso distingue anche le singole schede consultate.

Richieste automatiche, frammenti HTML, download, file statici, reindirizzamenti,
errori e accessi negati non generano visualizzazioni. Non vengono salvati query
string, contenuti delle pagine, password o dati di sessione. Il registro non misura
il tempo di permanenza e non rileva riaperture dalla cache del browser senza una
richiesta al server. I tentativi di login falliti non sono inclusi.

La consultazione resta riservata agli amministratori già abilitati al LOG.
I nuovi eventi seguono la conservazione configurata per la cronologia e sono
disponibili dall'attivazione della funzionalità, senza ricostruzione dello storico.

L'aggiornamento include la migrazione `sistema.0011_cronologia_login_visualizzazioni`,
da applicare con `python manage.py migrate` durante l'aggiornamento dell'applicazione.
