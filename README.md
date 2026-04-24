# Arboris School Management

Gestionale per scuole paritarie basato su Django 5 e PostgreSQL. Include moduli
per anagrafica famiglie/studenti, iscrizioni, economia, calendario, sistema
permessi e **gestione finanziaria** (conti bancari, import estratti conto,
integrazione PSD2, riconciliazione movimenti e report per categoria).

---

## Prerequisiti

- **Python 3.12+** (testato con Python 3.14)
- **PostgreSQL 14+** attivo e raggiungibile
- Un database dedicato al progetto e un utente con permessi su di esso

---

## Setup

### 1. Virtualenv dedicato (consigliato)

Evita di installare le dipendenze nel Python di sistema: il progetto ha diverse
librerie (Django, psycopg, cryptography, pandas…) e un virtualenv mantiene
l'ambiente isolato e riproducibile.

```powershell
# Windows PowerShell
cd C:\SVILUPPO_SOFTWARE\Arboris
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

```bash
# Linux / macOS
cd ~/Arboris
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Nota importante**: ricordati di **attivare il venv** prima di lanciare
> `python manage.py runserver`, `makemigrations`, `migrate`, ecc. Se in un
> terminale nuovo parte il Python di sistema anziche' quello del venv, le
> dipendenze installate sembreranno "sparite" e otterrai errori tipo
> `ModuleNotFoundError: No module named 'cryptography'`.
> In PowerShell puoi verificarlo con `python -c "import sys; print(sys.executable)"`.

### 2. Variabili d'ambiente

Crea un file `.env` (o imposta variabili nel tuo sistema) con almeno:

```
DATABASE_URL=postgres://utente:password@localhost:5432/arboris
DJANGO_SECRET_KEY=<chiave-random-lunga>

# Solo per il modulo Gestione finanziaria (PSD2):
# Chiave Fernet per cifrare i token dei provider. Se non impostata viene
# derivata da DJANGO_SECRET_KEY (ok in sviluppo, NON in produzione).
# Generane una con:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ARBORIS_FERNET_KEY=
```

### 3. Inizializzazione database

```powershell
python manage.py migrate
python manage.py createsuperuser
```

### 4. Avvio sviluppo

```powershell
python manage.py runserver
```

L'applicazione e' raggiungibile su http://127.0.0.1:8000/ .

---

## Struttura del progetto

```
arboris/
+-- anagrafica/            Famiglie, studenti, contatti
+-- calendario/            Eventi e calendari
+-- economia/              Iscrizioni, rate, tariffe, metodi pagamento
+-- gestione_finanziaria/  Conti bancari, movimenti, PSD2, report
+-- sistema/               Utenti, permessi, audit, backup
+-- config/                settings, urls, wsgi
+-- templates/             Template HTML (base + per modulo)
+-- requirements.txt
+-- manage.py
```

---

## Modulo Gestione Finanziaria

Permette di:

- Registrare **conti bancari** e **provider** (manuali o PSD2).
- Importare estratti conto in formato **CAMT.053** o **CSV** configurabile.
- Collegare conti bancari in lettura tramite **PSD2** (adapter GoCardless Bank
  Account Data gia' disponibile), con flusso di consenso standard.
- Categorizzare i movimenti con **categorie gerarchiche** definite dall'utente
  e **regole automatiche**.
- Pianificare la **sincronizzazione periodica** dei conti PSD2 (singleton
  configurabile + middleware + management command).
- **Riconciliare** i movimenti bancari con le rate iscrizione del modulo
  Economia, con suggerimenti automatici in base a importo e data.
- Generare **report per categoria** mensili e annuali con rollup gerarchico.

### Scheduler PSD2

La pianificazione della sincronizzazione si configura da
*Gestione finanziaria -> Connessioni PSD2 -> Pianificazione sincronizzazione*.

Per farla girare **indipendentemente dal traffico web** (consigliato), pianifica
il comando:

```powershell
# Windows Task Scheduler: azione = Avvia programma
# Programma/script: C:\SVILUPPO_SOFTWARE\Arboris\.venv\Scripts\python.exe
# Argomenti: manage.py run_scheduled_psd2_sync
# Avvia in: C:\SVILUPPO_SOFTWARE\Arboris
python manage.py run_scheduled_psd2_sync
```

```bash
# cron Linux (ogni ora):
0 * * * * cd /app && /app/.venv/bin/python manage.py run_scheduled_psd2_sync
```

Il comando e' **idempotente**: rispetta l'intervallo configurato anche se
chiamato piu' spesso.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'cryptography'` (o simili)

Il venv non e' attivo e stai usando il Python di sistema. Attiva il venv
(`.venv\Scripts\Activate.ps1`) oppure, se preferisci usare l'interprete di
sistema, installa li' le dipendenze:

```powershell
& "C:\Users\<utente>\AppData\Local\Programs\Python\Python314\python.exe" -m pip install -r requirements.txt
```

### `DisallowedHost` durante i test

Aggiungi `testserver` a `ALLOWED_HOSTS` nel proprio `settings.py` (o solo per i
test) oppure usa l'override in runtime.

---

## Licenza

Software proprietario. Tutti i diritti riservati.
