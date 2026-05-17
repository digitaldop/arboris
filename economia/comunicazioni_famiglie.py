from collections import Counter, OrderedDict
from email.utils import formataddr
from hashlib import sha1
import socket
import smtplib

from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.db.models import Prefetch

from anagrafica.models import StudenteFamiliare
from economia.models import Iscrizione
from sistema.models import (
    ComunicazioneFamigliaLog,
    ConfigurazioneEmailSMTP,
    SicurezzaEmailSMTP,
    StatoComunicazioneFamiglia,
)


class ComunicazioneFamiglieError(Exception):
    pass


class ComunicazioneFamiglieSMTPError(ComunicazioneFamiglieError):
    pass


SMTP_WEB_TIMEOUT_SECONDS = 6


def smtp_timeout_sicuro(value=None):
    try:
        timeout = int(value or SMTP_WEB_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = SMTP_WEB_TIMEOUT_SECONDS
    return max(1, min(timeout, SMTP_WEB_TIMEOUT_SECONDS))


def descrivi_errore_smtp(exc, configurazione=None):
    host = getattr(configurazione, "host", "") or "server SMTP"
    port = getattr(configurazione, "port", "") or "porta configurata"

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return (
            f"Connessione SMTP scaduta verso {host}:{port}. "
            "Il server non risponde da Render: verifica host, porta e sicurezza. "
            "Di solito si usa 587 con STARTTLS oppure 465 con SSL/TLS; evita la porta 25."
        )

    if isinstance(exc, socket.gaierror):
        return f"Server SMTP non risolto: {host}. Verifica che l'host sia scritto correttamente."

    if isinstance(exc, ConnectionRefusedError):
        return f"Connessione rifiutata da {host}:{port}. Verifica porta e tipo di sicurezza SMTP."

    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "Autenticazione SMTP non riuscita. Verifica username, password o app password del provider."

    if isinstance(exc, smtplib.SMTPConnectError):
        return f"Il server SMTP {host}:{port} ha rifiutato la connessione iniziale."

    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "Il server SMTP ha chiuso la connessione. Verifica sicurezza, porta e credenziali."

    if isinstance(exc, smtplib.SMTPException):
        return f"Errore SMTP: {exc}"

    return str(exc)


def normalizza_email(value):
    return (value or "").strip().lower()


def email_valida(value):
    email = normalizza_email(value)
    if not email:
        return ""
    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def chiave_destinatario(iscrizione_id, familiare_id, email):
    digest = sha1(normalizza_email(email).encode("utf-8")).hexdigest()[:12]
    return f"{iscrizione_id}:{familiare_id}:{digest}"


def classe_iscrizione_label(iscrizione):
    if iscrizione.gruppo_classe_id:
        return str(iscrizione.gruppo_classe)
    if iscrizione.classe_id:
        return str(iscrizione.classe)
    return ""


def relazione_familiare_label(relazione):
    if relazione.relazione_familiare_id:
        return str(relazione.relazione_familiare)
    if relazione.familiare_id and relazione.familiare.relazione_familiare_id:
        return str(relazione.familiare.relazione_familiare)
    return "Familiare"


def iscrizioni_attive_per_anni(anni_scolastici):
    anno_ids = [anno.pk if hasattr(anno, "pk") else anno for anno in anni_scolastici]
    relazioni_qs = (
        StudenteFamiliare.objects.filter(attivo=True)
        .select_related("familiare__persona", "familiare__relazione_familiare", "relazione_familiare")
        .order_by("-referente_principale", "familiare__persona__cognome", "familiare__persona__nome", "id")
    )
    return (
        Iscrizione.objects.filter(
            anno_scolastico_id__in=anno_ids,
            attiva=True,
            stato_iscrizione__attiva=True,
            studente__attivo=True,
        )
        .exclude(stato_iscrizione__stato_iscrizione__icontains="annull")
        .select_related("anno_scolastico", "studente", "classe", "gruppo_classe", "stato_iscrizione")
        .prefetch_related(Prefetch("studente__relazioni_familiari", queryset=relazioni_qs, to_attr="relazioni_email"))
        .order_by("anno_scolastico__data_inizio", "studente__cognome", "studente__nome", "id")
    )


def costruisci_destinatari_famiglie(anni_scolastici):
    gruppi = []
    destinatari = []
    studenti_senza_email = 0

    for iscrizione in iscrizioni_attive_per_anni(anni_scolastici):
        gruppo_destinatari = []
        relazioni = getattr(iscrizione.studente, "relazioni_email", [])
        for relazione in relazioni:
            familiare = relazione.familiare
            email = email_valida(getattr(familiare, "email_principale", "") or getattr(familiare, "email", ""))
            if not email:
                continue

            destinatario = {
                "key": chiave_destinatario(iscrizione.pk, familiare.pk, email),
                "iscrizione_id": iscrizione.pk,
                "anno_scolastico_id": iscrizione.anno_scolastico_id,
                "anno_label": str(iscrizione.anno_scolastico),
                "studente_id": iscrizione.studente_id,
                "studente_label": str(iscrizione.studente),
                "classe_label": classe_iscrizione_label(iscrizione),
                "familiare_id": familiare.pk,
                "familiare_label": str(familiare),
                "relazione_label": relazione_familiare_label(relazione),
                "email": email,
                "email_norm": normalizza_email(email),
                "referente_principale": relazione.referente_principale,
                "duplicato": False,
            }
            gruppo_destinatari.append(destinatario)
            destinatari.append(destinatario)

        if not gruppo_destinatari:
            studenti_senza_email += 1

        gruppi.append(
            {
                "iscrizione_id": iscrizione.pk,
                "anno_label": str(iscrizione.anno_scolastico),
                "studente_label": str(iscrizione.studente),
                "classe_label": classe_iscrizione_label(iscrizione),
                "stato_label": str(iscrizione.stato_iscrizione),
                "destinatari": gruppo_destinatari,
            }
        )

    conteggio_email = Counter(destinatario["email_norm"] for destinatario in destinatari)
    for destinatario in destinatari:
        destinatario["duplicato"] = conteggio_email[destinatario["email_norm"]] > 1

    statistiche = {
        "studenti": len(gruppi),
        "studenti_senza_email": studenti_senza_email,
        "destinatari": len(destinatari),
        "email_uniche": len(conteggio_email),
        "duplicati": len(destinatari) - len(conteggio_email),
    }
    return gruppi, destinatari, statistiche


def destinatari_da_chiavi(destinatari, chiavi_selezionate):
    chiavi = set(chiavi_selezionate or [])
    return [destinatario for destinatario in destinatari if destinatario["key"] in chiavi]


def crea_connessione_smtp(configurazione, *, timeout_secondi=None):
    if not configurazione or not configurazione.configurata:
        raise ComunicazioneFamiglieError("Configura il server SMTP prima di inviare comunicazioni alle famiglie.")

    timeout = timeout_secondi if timeout_secondi is not None else configurazione.timeout_secondi
    kwargs = {
        "backend": "django.core.mail.backends.smtp.EmailBackend",
        "host": configurazione.host,
        "port": configurazione.port,
        "username": configurazione.username or None,
        "password": configurazione.password or None,
        "timeout": smtp_timeout_sicuro(timeout),
        "use_tls": configurazione.sicurezza == SicurezzaEmailSMTP.STARTTLS,
        "use_ssl": configurazione.sicurezza == SicurezzaEmailSMTP.SSL,
    }
    return get_connection(**kwargs)


def mittente_configurato(configurazione):
    if configurazione.nome_mittente:
        return formataddr((configurazione.nome_mittente, configurazione.email_mittente))
    return configurazione.email_mittente


def invia_email_singola(configurazione, *, destinatario, oggetto, messaggio, connection=None):
    email = EmailMessage(
        subject=oggetto,
        body=messaggio,
        from_email=mittente_configurato(configurazione),
        to=[destinatario],
        reply_to=[configurazione.reply_to] if configurazione.reply_to else None,
        connection=connection,
    )
    return email.send(fail_silently=False)


def invia_email_test_smtp(configurazione, *, destinatario, oggetto, messaggio):
    connection = None
    try:
        connection = crea_connessione_smtp(
            configurazione,
            timeout_secondi=SMTP_WEB_TIMEOUT_SECONDS,
        )
        return invia_email_singola(
            configurazione,
            destinatario=destinatario,
            oggetto=oggetto,
            messaggio=messaggio,
            connection=connection,
        )
    except Exception as exc:
        raise ComunicazioneFamiglieSMTPError(descrivi_errore_smtp(exc, configurazione)) from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def invia_comunicazione_famiglie(*, configurazione, destinatari, oggetto, messaggio, anni_scolastici, utente=None):
    if not destinatari:
        raise ComunicazioneFamiglieError("Seleziona almeno un destinatario prima di inviare.")

    destinatari_unici = OrderedDict()
    dettagli = []
    duplicati_saltati = 0

    for destinatario in destinatari:
        email_norm = destinatario["email_norm"]
        if email_norm in destinatari_unici:
            duplicati_saltati += 1
            dettagli.append({**destinatario, "esito": "duplicato", "errore": ""})
            continue
        destinatari_unici[email_norm] = destinatario

    connection = crea_connessione_smtp(configurazione)
    inviate = 0
    fallite = 0
    errore_generale = ""

    try:
        connection.open()
    except Exception as exc:  # noqa: BLE001 - il log deve registrare anche errori infrastrutturali.
        errore_generale = descrivi_errore_smtp(exc, configurazione)
        fallite = len(destinatari_unici)
        for destinatario in destinatari_unici.values():
            dettagli.append({**destinatario, "esito": "errore", "errore": errore_generale})
    else:
        try:
            for destinatario in destinatari_unici.values():
                try:
                    invia_email_singola(
                        configurazione,
                        destinatario=destinatario["email"],
                        oggetto=oggetto,
                        messaggio=messaggio,
                        connection=connection,
                    )
                except Exception as exc:  # noqa: BLE001 - gli altri destinatari devono continuare a partire.
                    fallite += 1
                    dettagli.append(
                        {
                            **destinatario,
                            "esito": "errore",
                            "errore": descrivi_errore_smtp(exc, configurazione),
                        }
                    )
                else:
                    inviate += 1
                    dettagli.append({**destinatario, "esito": "inviata", "errore": ""})
        finally:
            connection.close()

    if fallite and inviate:
        stato = StatoComunicazioneFamiglia.PARZIALE
    elif fallite:
        stato = StatoComunicazioneFamiglia.ERRORE
    else:
        stato = StatoComunicazioneFamiglia.INVIATA

    log = ComunicazioneFamigliaLog.objects.create(
        utente=utente if getattr(utente, "is_authenticated", False) else None,
        stato=stato,
        oggetto=oggetto,
        messaggio=messaggio,
        anni_scolastici=[
            {
                "id": anno.pk,
                "label": str(anno),
            }
            for anno in anni_scolastici
        ],
        destinatari_selezionati=len(destinatari),
        destinatari_unici=len(destinatari_unici),
        inviate=inviate,
        fallite=fallite,
        duplicati_saltati=duplicati_saltati,
        dettagli_destinatari=dettagli,
        errore_generale=errore_generale,
    )

    return {
        "log": log,
        "stato": stato,
        "inviate": inviate,
        "fallite": fallite,
        "destinatari_selezionati": len(destinatari),
        "destinatari_unici": len(destinatari_unici),
        "duplicati_saltati": duplicati_saltati,
        "dettagli": dettagli,
        "errore_generale": errore_generale,
    }
