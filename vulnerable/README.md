# Banco vulnerabile

Impianto di refrigerazione simulato, configurato in modo volutamente insicuro, con una macchina dell'attaccante per i tre scenari del [threat model](../docs/threat_model.md).

## Componenti

| Servizio | Indirizzo nella rete del banco | Cosa fa | Porta sul computer ospite |
|---|---|---|---|
| `controller` | 10.77.10.10 | Controller SR-100: congelatore virtuale, interfaccia web (80), Modbus/TCP (502) | http://127.0.0.1:8080 |
| `broker` | 10.77.10.20 | Mosquitto, MQTT anonimo sulla 1883 | Nessuna |
| `sensor` | 10.77.10.30 | Sonda TP-1: legge la temperatura e la pubblica via MQTT | Nessuna |
| `alarm` | 10.77.10.40 | Centrale allarmi: allarme sopra -10 °C per 3 letture consecutive, pagina web (8080) | http://127.0.0.1:8081 |
| `attacker` | 10.77.10.66 | Nmap e script degli attacchi | Nessuna |

La simulazione è accelerata di 60 volte: un secondo reale vale un minuto di impianto.

## Isolamento

- La rete `negozio` è interna a Docker: l'attaccante non ha una rotta verso Internet né verso la rete di casa.
- Le pagine web sono pubblicate solo su 127.0.0.1, quindi non sono raggiungibili da altri computer.
- Gli script d'attacco puntano agli indirizzi 10.77.10.x del banco. La scansione esclude 10.77.10.1, che è l'interfaccia del computer ospite.

## Requisiti

Docker Engine con il plugin Compose, su Linux x86_64 o arm64 (Raspberry Pi OS a 64 bit). Le immagini di base sono multi architettura, quindi gli stessi file funzionano sul PC e sul Raspberry Pi senza modifiche.

## Avvio e arresto

```sh
cd vulnerable
docker compose up -d --build     # costruisce le immagini e avvia il banco
docker compose ps                # tutti i servizi devono essere "running"
docker compose logs -f           # log di tutti i servizi (Ctrl+C per uscire)
docker compose restart controller alarm   # riporta impianto e allarmi allo stato iniziale
docker compose down              # ferma e rimuove i container
```

Su un Raspberry Pi senza schermo le pagine web si aprono dal PC con un tunnel SSH:

```sh
ssh -L 8080:127.0.0.1:8080 -L 8081:127.0.0.1:8081 utente@indirizzo-del-raspberry
```

## Attacchi

Si lanciano dentro il container dell'attaccante:

```sh
docker compose exec attacker ./scan.sh
docker compose exec attacker python recon_modbus.py
docker compose exec attacker python scenario1_parametri.py web
docker compose exec attacker python scenario1_parametri.py modbus
docker compose exec attacker python scenario1_parametri.py ripristina
docker compose exec attacker python scenario2_letture.py ascolta
docker compose exec attacker python scenario2_letture.py falsifica
docker compose exec attacker python scenario2_letture.py replay
docker compose exec attacker python scenario3_silenzia.py
docker compose exec attacker python scenario3_silenzia.py ripristina
```

| Script | Cosa fa | Cosa si osserva |
|---|---|---|
| `scan.sh` | Host attivi, porte aperte, banner web, topic MQTT, identificativo Modbus | Modello e firmware del controller, formato delle letture, topic di configurazione della sonda |
| `scenario1_parametri.py web` | Setpoint a +25 °C dal modulo web, senza login | La temperatura sale, dopo circa 90 secondi la centrale va in allarme |
| `scenario1_parametri.py modbus` | Sbrinamento di 480 minuti fino a 50 °C, via Modbus | La temperatura sale di circa 3 °C ogni 10 secondi |
| `scenario2_letture.py falsifica` | Letture false a -20 °C, quattro al secondo | Con lo scenario 1 attivo la centrale resta su "NORMALE" |
| `scenario2_letture.py replay` | Letture autentiche registrate e ripetute | Come sopra, con messaggi indistinguibili da quelli veri |
| `scenario3_silenzia.py` | Spegne l'invio della sonda con un comando MQTT | Con lo scenario 1 attivo nessun allarme, l'ultima lettura invecchia |

Gli script nella cartella `attacker/attacks/` sono montati nel container: una modifica è subito attiva, senza ricostruire l'immagine.

## Sorgente della sonda

La variabile `SENSOR_SOURCE` sceglie da dove la sonda legge la temperatura:

| Valore | Sorgente |
|---|---|
| `plant` (predefinito) | Il congelatore virtuale, tramite un volume condiviso con il controller che rappresenta il mondo fisico |
| `synthetic` | Dati sintetici attorno a -20 °C |
| `ds18b20` | Sonda reale DS18B20 sul bus 1-Wire del Raspberry Pi (in preparazione) |

## Registri Modbus del controller

Temperature in decimi di grado, intero a 16 bit con segno. Identificativo di unità 1.

| Tipo | Indirizzo | Contenuto |
|---|---|---|
| Holding register | 0 | Setpoint |
| Holding register | 1 | Durata dello sbrinamento, minuti |
| Holding register | 2 | Temperatura di fine sbrinamento |
| Holding register | 3 | Comando: 1 avvia uno sbrinamento |
| Input register | 0 | Temperatura |
| Input register | 1 | Compressore acceso |
| Input register | 2 | Resistenza di sbrinamento accesa |
| Input register | 3 | Sbrinamento in corso |
| Input register | 4 | Minuti di sbrinamento residui |

## Topic MQTT

| Topic | Contenuto |
|---|---|
| `store/freezer1/temperature` | Letture: `{"sensor", "temp_c", "ts", "seq"}` |
| `store/freezer1/probe1/info` | Presentazione della sonda, messaggio retained |
| `store/freezer1/probe1/config` | Configurazione remota: `{"enabled": true/false, "interval_s": secondi}` |
