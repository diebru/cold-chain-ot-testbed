# SR-100 Supervisore refrigerazione: manuale d'installazione (estratto)

> Documento fittizio, parte del banco di prova. L'SR-100 e l'RC-10 non esistono e non corrispondono ad alcun prodotto commerciale. Il manuale rappresenta la documentazione tecnica che i produttori pubblicano per gli installatori, liberamente scaricabile. Nel caso reale le credenziali provate dagli attaccanti erano descritte come "documentate", cioè reperibili in documenti di questo tipo.

## 1. Architettura

Il supervisore SR-100 si collega ai regolatori di banco RC-10 tramite il bus di campo Modbus e alla rete del punto vendita tramite la porta Ethernet. Dalla rete del punto vendita offre:

| Servizio | Porta | Uso |
|---|---|---|
| Interfaccia web | TCP 80 | Configurazione e consultazione |
| Gateway Modbus/TCP | TCP 502 | Integrazione con sistemi di gestione dell'edificio |

Per la telegestione il manutentore può rendere l'interfaccia web raggiungibile da remoto.

## 2. Primo accesso

Credenziali predefinite, uguali per tutti gli esemplari:

| Utente | Password |
|---|---|
| installatore | SR100-inst |

Si raccomanda di cambiare la password al termine dell'installazione.

## 3. Mappa del gateway Modbus/TCP

Ogni banco ha un identificativo di unità: 1 per il primo regolatore, 2 per il secondo. Le temperature sono espresse in decimi di grado, intero a 16 bit con segno.

| Tipo | Indirizzo | Contenuto | Accesso |
|---|---|---|---|
| Holding register | 0 | Setpoint | Lettura e scrittura |
| Holding register | 1 | Durata dello sbrinamento, minuti | Lettura e scrittura |
| Holding register | 2 | Temperatura di fine sbrinamento | Lettura e scrittura |
| Holding register | 3 | Comando di sbrinamento: 1 avvia | Lettura e scrittura |
| Holding register | 4 | Soglia d'allarme alta | Lettura e scrittura |
| Holding register | 5 | Ritardo d'allarme, minuti | Lettura e scrittura |
| Input register | 0 | Temperatura | Sola lettura |
| Input register | 1 | Compressore acceso | Sola lettura |
| Input register | 2 | Resistenza di sbrinamento accesa | Sola lettura |
| Input register | 3 | Sbrinamento in corso | Sola lettura |
| Input register | 4 | Minuti di sbrinamento residui | Sola lettura |

## 4. Allarmi

Il supervisore genera un allarme quando la temperatura di un banco resta sopra la soglia per il ritardo impostato e lo notifica al centro di telegestione. Valori di fabbrica:

| Banco | Soglia | Ritardo |
|---|---|---|
| Congelatore | -10 °C | 5 minuti |
| Banco frigo | +12 °C | 5 minuti |
