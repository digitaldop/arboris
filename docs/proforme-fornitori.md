# Pro-forma dei fornitori

La prima versione gestisce una pro-forma per fattura definitiva, con una o più scadenze e pagamenti. Si accede da **Fatture e scadenze → Nuova pro-forma**. La vista **In attesa di fattura definitiva** comprende anche le pro-forma interamente pagate. Senza scadenze inserite, la creazione propone l'intero netto alla data di emissione.

## Righe personalizzate degli importi

Nella sezione **Importi**, il pulsante **Aggiungi riga** permette di inserire una descrizione libera e un importo fisso oppure una percentuale sull'**Importo prodotti e servizi**. Ogni percentuale usa la stessa base, senza includere le altre righe. Sono ammessi valori negativi per gli sconti e fino a 50 righe per documento. **Applica IVA** include la riga nell'imponibile e usa l'aliquota IVA del documento; le righe senza IVA vengono aggiunte al totale dopo il calcolo dell'imposta.

Le righe non modificano automaticamente l'imponibile della ritenuta, da indicare nel campo dedicato. Con righe presenti occorre inserire l'importo prodotti e servizi; IVA e totale sono calcolati automaticamente. I calcoli vengono verificati anche al salvataggio, arrotondando righe e imposte al centesimo. Le righe si possono modificare e rimuovere e restano visibili nello storico della pro-forma collegata alla fattura definitiva.

Esempio: prodotti e servizi **81,00 €**, riga **Cassa ENPACL**, percentuale **4%**, **Applica IVA** selezionato, aliquota IVA **22%**, imponibile ritenuta **81,00 €** e aliquota ritenuta **20%**. Si ottengono cassa **3,24 €**, imponibile IVA **84,24 €**, IVA **18,53 €**, totale **102,77 €**, ritenuta **16,20 €** e netto **86,57 €**.

Le righe personalizzate sono disponibili sulle pro-forma. I documenti senza righe mantengono il calcolo precedente, compreso lo scorporo dell'IVA dal totale. Applicare la migrazione `gestione_finanziaria.0015_documentofornitore_righe_importo_personalizzate` con il codice; i documenti esistenti partono senza righe e conservano gli importi. I test specifici sono in `gestione_finanziaria.test_righe_importo_proforma`.

## Import e verifica

L'import cerca le pro-forma disponibili dello stesso fornitore, senza limite di anzianità. Collega automaticamente soltanto una candidata univoca con totale e netto coincidenti e un riferimento strutturato alla pro-forma (`DatiFattureCollegate`, con data coerente se presente) o all'ordine (`DatiOrdineAcquisto`, confrontato con **Riferimento ordine**). L'XML allegato viene considerato anche per fatture già registrate quando il fornitore ha pro-forma aperte.

La sola uguaglianza degli importi, una menzione nel testo libero, più candidate o importi discordanti richiedono conferma. La fattura viene conservata in **Da verificare**, senza generare ulteriori scadenze. Dalla verifica si può collegare una pro-forma oppure scegliere **È una fattura distinta**. Questa scelta viene ricordata dagli import successivi. In assenza di candidate l'import prosegue normalmente.

Per fatture già presenti e riconciliate, il collegamento chiede prima di verificare eventuali pagamenti duplicati. Non sposta né elimina automaticamente pagamenti già registrati sulla fattura definitiva.

## Pagamenti e storico

Il collegamento trasferisce le scadenze esistenti alla fattura definitiva mantenendone gli identificativi, i pagamenti, gli abbinamenti bancari e le date. Conserva entrambi i documenti e allegati, ed eredita categoria e competenza dalla pro-forma. La pro-forma riporta **Fattura definitiva ricevuta** e non contribuisce più al debito.

Le differenze di importo richiedono la conferma del residuo. L'adeguamento parte dall'ultima scadenza; le riduzioni non intaccano gli importi già pagati. Un pagato superiore al netto del documento richiede la verifica dell'eccedenza prima del collegamento.

**Annulla collegamento** restituisce scadenze e pagamenti alla pro-forma e riporta la fattura in verifica. Se nel frattempo sono stati registrati pagamenti superiori al netto della pro-forma, occorre prima gestire l'eccedenza. Lo storico conserva autore, data, origine automatica/manuale e annullamento; i documenti che vi partecipano sono protetti dall'eliminazione e dalla pulizia dei duplicati.

Gli import successivi non ricreano le scadenze collegate e non cambiano i pagamenti. Le variazioni degli importi vengono mostrate in verifica e applicate solo dopo conferma. Per modificare i dati finanziari di documenti collegati si usa la verifica o si annulla prima il collegamento. I nuovi pagamenti restano disponibili sulla fattura definitiva.

## Installazione e collaudo

Applicare le migrazioni fino a `gestione_finanziaria.0015_documentofornitore_righe_importo_personalizzate` insieme al codice. Non serve modificare i documenti esistenti: le pro-forma già registrate sono utilizzabili.

I test sono in `gestione_finanziaria.test_proforme`; coprono collegamenti, import ripetuti, XML, ritenute, pagamenti parziali e bancari, correzioni, protezione dello storico, permessi e schermate. Le chiamate esterne sono simulate. Le migrazioni e i percorsi del browser sono stati verificati in database temporanei, senza import reali.
