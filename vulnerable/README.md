# Banco vulnerabile

Impianto di refrigerazione simulato, configurato in modo volutamente insicuro, con una macchina dell'attaccante per gli scenari del [threat model](../docs/threat_model.md). I dispositivi SR-100, RC-10 e TP-1 sono fittizi. Il loro [manuale](manuale_SR-100.md) rappresenta la documentazione pubblica del prodotto.

## Componenti

| Servizio | Indirizzo | Cosa fa | Pagina sul computer ospite |
|---|---|---|---|
| `regolatore1` | 10.77.20.11 (bus di campo) | Regolatore RC-10 del congelatore (-20 °C) | Nessuna |
| `regolatore2` | 10.77.20.12 (bus di campo) | Regolatore RC-10 del banco frigo (+3 °C) | Nessuna |
| `supervisore` | 10.77.10.10 e 10.77.20.10 | Supervisore SR-100: web con login (80), gateway Modbus/TCP (502), allarmi, notifiche | http://127.0.0.1:8080 |
| `telegestione` | 10.77.10.50 | Riceve le notifiche d'allarme del supervisore | http://127.0.0.1:8082 |
| `broker` | 10.77.10.20 | Mosquitto del monitoraggio indipendente, MQTT anonimo (1883) | Nessuna |
| `sonda` | 10.77.10.30 | Sonda TP-1 del monitoraggio indipendente sul banco 1 | Nessuna |
| `centrale` | 10.77.10.40 | Centrale del monitoraggio indipendente, allarme a due livelli | http://127.0.0.1:8081 |
| `attaccante` | 10.77.10.66 | Nmap e script degli attacchi | Nessuna |

Credenziali di fabbrica del supervisore (dal manuale): utente `installatore`, password `SR100-inst`.

La simulazione è accelerata di 60 volte: un secondo reale vale un minuto di impianto.

## Isolamento

- Le reti `negozio` e `campo` sono interne a Docker: l'attaccante non ha una rotta verso Internet né verso la rete di casa, e non raggiunge il bus di campo.
- Le pagine web sono pubblicate solo su 127.0.0.1, quindi non sono raggiungibili da altri computer.
- Gli script d'attacco puntano agli indirizzi 10.77.x.x del banco. La scansione esclude 10.77.10.1, che è l'interfaccia del computer ospite.

## Requisiti

Docker Engine con il plugin Compose, su Linux x86_64 o arm64 (Raspberry Pi OS a 64 bit). Le immagini di base sono multi architettura, quindi gli stessi file funzionano sul PC e sul Raspberry Pi senza modifiche.

## Avvio e arresto

```sh
cd vulnerable
docker compose up -d --build     # costruisce le immagini e avvia il banco
docker compose ps                # tutti gli 8 servizi devono essere "running"
docker compose logs -f supervisore sonda centrale telegestione   # log (Ctrl+C per uscire)
docker compose restart           # riporta tutto allo stato iniziale in circa 10 secondi
docker compose down              # ferma e rimuove i container
```

Su un Raspberry Pi senza schermo le pagine web si aprono dal PC con un tunnel SSH:

```sh
ssh -L 8080:127.0.0.1:8080 -L 8081:127.0.0.1:8081 -L 8082:127.0.0.1:8082 utente@indirizzo-del-raspberry
```

## Attacchi

Si lanciano dentro il container dell'attaccante, con `docker compose exec attaccante` seguito dal comando:

| Comando | Cosa fa | Cosa si osserva |
|---|---|---|
| `./scan.sh` | Host, porte, banner, topic MQTT, registri del gateway, raggiungibilità del bus di campo | Modello e firmware del supervisore, pagina di login, topic della sonda, regolatori irraggiungibili |
| `python scenario1_supervisore.py web` | Login con le credenziali del manuale, soglia d'allarme a +60 °C, sbrinamento di 480 minuti fino a 50 °C | Supervisore muto, nessuna notifica, il monitoraggio indipendente va in allarme |
| `python scenario1_supervisore.py web --lascia-soglie` | Come sopra senza toccare la soglia | Allarme del supervisore e notifica alla telegestione |
| `python scenario1_supervisore.py modbus` | Le stesse modifiche dal gateway Modbus, senza login | Come la variante web |
| `python scenario1_supervisore.py ripristina` | Parametri e soglie di fabbrica | |
| `python scenario2_letture.py ascolta` | Legge tutti i topic del broker | Letture e messaggio di presentazione della sonda |
| `python scenario2_letture.py falsifica` | Letture false a -20 °C, quattro al secondo | Con lo scenario 1: allarme nascosto, allarme critico no |
| `python scenario2_letture.py replay` | Letture autentiche registrate e ripetute | Come sopra, con messaggi indistinguibili da quelli veri |
| `python scenario3_silenzia.py` | Spegne l'invio della sonda con un comando MQTT | Con lo scenario 1: nessun allarme, l'ultima lettura invecchia |
| `python scenario3_silenzia.py ripristina` | Riaccende la sonda | |

Catena completa, nessun allarme da nessuna parte: avviare `scenario2_letture.py replay`, attendere la fine della registrazione, poi `scenario3_silenzia.py` e `scenario1_supervisore.py web`.

Gli script nella cartella `attaccante/attacks/` sono montati nel container: una modifica è subito attiva, senza ricostruire l'immagine.

## Sorgente della sonda indipendente

La variabile `SENSOR_SOURCE` sceglie da dove la sonda legge la temperatura:

| Valore | Sorgente |
|---|---|
| `plant` (predefinito) | Il banco 1 simulato, tramite un volume condiviso con il regolatore che rappresenta il mondo fisico |
| `synthetic` | Dati sintetici attorno a -20 °C |
| `ds18b20` | Sonda reale DS18B20 sul bus 1-Wire del Raspberry Pi (in preparazione) |

## Registri e topic

La mappa del gateway Modbus è nel [manuale](manuale_SR-100.md), paragrafo 3. I regolatori usano gli stessi registri da 0 a 3 per i parametri e da 0 a 4 per le misure.

| Topic MQTT | Contenuto |
|---|---|
| `monitoraggio/banco1/temperatura` | Letture: `{"sensor", "temp_c", "ts", "seq"}` |
| `monitoraggio/banco1/sonda1/info` | Presentazione della sonda, messaggio retained |
| `monitoraggio/banco1/sonda1/config` | Configurazione remota: `{"enabled": true/false, "interval_s": secondi}` |
