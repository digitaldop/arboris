"""
Adapter verso provider bancari PSD2 (Account Information Services).

Ogni provider espone la stessa API (``BasePsd2Adapter``) in modo che le view
siano indipendenti dal provider scelto:

- lista istituti bancari supportati per un paese;
- creazione di una requisition/consenso e generazione del link di autorizzazione;
- lettura dei conti collegati dopo l'autorizzazione dell'utente;
- lettura dei saldi e dei movimenti di un conto.

Il modulo ``registry`` mappa l'istanza ``ProviderBancario`` (identificata dal
campo ``tipo`` e dalla ``configurazione`` JSON) sull'adapter concreto.
"""

from .base import (  # noqa: F401
    BasePsd2Adapter,
    ProviderConnectionInfo,
    ProviderInstitution,
    ProviderAccount,
    ProviderBalance,
    ProviderTransaction,
)
from .registry import (  # noqa: F401
    ADAPTER_ENABLEBANKING,
    ADAPTER_GOCARDLESS_BAD,
    ADAPTER_SALTEDGE,
    ADAPTER_TRUELAYER,
    adapter_for_provider,
    is_enablebanking_adapter,
    is_oauth_adapter,
    is_redirect_callback_adapter,
    is_saltedge_adapter,
)
