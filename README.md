# Cold Chain OT Testbed

Italiano · [English version](README.en.md)

Banco di prova per la sicurezza della refrigerazione commerciale connessa. Parte da un caso reale, le campagne di sabotaggio dei frigoriferi della grande distribuzione europea di ottobre e novembre 2026, e ne riproduce la **classe di debolezza** su dispositivi propri: funzioni di gestione raggiungibili dalla rete e protette male. Il banco esiste in due versioni, **vulnerabile** e **protetta**, e misura l'effetto di ogni difesa sugli stessi attacchi.

Project work da 3 CFU del corso di Cybersecurity, Laurea Magistrale in Ingegneria Informatica, Università di Bologna.

> **Stato:** in corso. Il case study è completo, il banco di prova è in sviluppo.

## Contenuto

| Parte | Stato |
|---|---|
| [Case study](case-study/case_study.pdf) (PDF, 13 pagine) | Completo |
| Threat model con MITRE ATT&CK for ICS | In lavorazione |
| Banco vulnerabile in Docker: controller simulato (web e Modbus/TCP), broker MQTT, server degli allarmi | Da fare |
| Tre scenari d'attacco: modifica di setpoint e sbrinamento, letture falsificate o ripetute, silenziamento del sensore | Da fare |
| Banco protetto: segmentazione, firewall, VPN WireGuard, autenticazione, TLS, letture firmate, heartbeat, sensore indipendente | Da fare |
| Porting su Raspberry Pi con sensore di temperatura reale (DS18B20) | Da fare |
| Rilevamento di anomalie fisiche e tabella dei risultati prima/dopo | Da fare |

---

## Case study: l'attacco ai sistemi di refrigerazione della grande distribuzione europea

**Documento completo:** [case-study/case_study.pdf](case-study/case_study.pdf). Rapporto in stile threat intelligence (TLP:CLEAR), con livelli di confidenza, cronologia, analisi tecnica, attribuzione, impatti, mappatura MITRE ATT&CK for ICS e riferimenti alle fonti. Fonti pubbliche consultate il 23 novembre 2026.

### Executive summary

Nella notte tra l'11 e il 12 ottobre 2026 un attaccante ha modificato da remoto i parametri di sbrinamento dei supervisori di refrigerazione di circa **700 punti vendita** della grande distribuzione francese, portando banchi e celle ad alte temperature. Ne sono derivate perdite di merce per decine di milioni di euro e almeno **15 principi d'incendio**. Una seconda ondata, nella notte tra l'1 e il 2 novembre, ha colpito una decina di paesi europei, **Italia compresa**, e tre siti dell'Établissement français du sang (EFS).

L'attacco non ha richiesto malware. È bastato trovare su Internet le interfacce di gestione esposte, spesso di modelli fuori supporto, e usarne le funzioni previste. È un caso OT esemplare: nessun dato è stato sottratto, ma l'alterazione di un parametro ha prodotto un danno fisico. L'ordine delle priorità è quindi safety, availability, integrity e solo per ultima confidentiality.

### Key findings

| # | Confidenza | Risultato |
|---|---|---|
| 1 | Alta | La prima ondata ha colpito circa 700 siti in Francia, con sbrinamenti forzati fino a circa 50 °C e almeno 15 principi d'incendio. |
| 2 | Alta | La seconda ondata ha colpito una decina di paesi europei, compresa l'Italia, e tre siti dell'EFS. |
| 3 | Moderata | Il governo francese attribuisce la prima ondata all'unità Shahid Kaveh dell'IRGC iraniano. Le prove forensi non sono state pubblicate. |
| 4 | Alta | I bersagli sono stati individuati con il motore di ricerca di dispositivi FOFA. |
| 5 | Bassa | Il vettore d'accesso non è chiarito: credenziali di fabbrica oppure il bypass CVE-2025-41450. |
| 6 | Alta | Nessun malware: sono state usate solo funzioni legittime dell'interfaccia. |
| 7 | Alta | All'EFS un sistema di monitoraggio indipendente dal fornitore attaccato ha evitato la perdita dei prodotti. |

### La catena d'attacco e le difese che l'avrebbero interrotta

| Passo | Cosa è successo | Misura che l'avrebbe interrotto |
|---|---|---|
| 1. Scoperta | FOFA, Shodan e Censys trovano migliaia di supervisori esposti | Nessun IP pubblico: segmentazione, accesso solo via VPN |
| 2. Accesso | Interfaccia web: credenziali di fabbrica o CVE-2025-41450 | Credenziali forti e uniche, MFA, firmware aggiornato |
| 3. Azione | Setpoint, sbrinamento e soglie d'allarme cambiati con comandi legittimi | Least privilege: il manutentore cambia solo ciò che serve |
| 4. Danno | Merce distrutta, almeno 15 principi d'incendio | Allarme indipendente, come all'EFS: danno evitato |

Tutte le misure erano note e raccomandate prima dell'attacco.

### Raccomandazioni

1. Togliere i supervisori da Internet: nessuna interfaccia di gestione su IP pubblico.
2. Accesso dei manutentori solo tramite VPN con autenticazione a più fattori.
3. Cambiare le credenziali di fabbrica, aggiornare il firmware, attivare le modalità di sicurezza restrittive.
4. Sostituire i dispositivi a fine vita e tenere un inventario degli asset esposti.
5. Affiancare alla supervisione del fornitore un allarme di temperatura indipendente.

### Dal caso al banco di prova

| Lezione dal caso | Nel banco di prova |
|---|---|
| Bastava raggiungere l'interfaccia e usarne le funzioni previste | **Scenario 1:** modifica del setpoint e sbrinamento forzato su un'interfaccia web e Modbus/TCP senza autenticazione |
| Chi controlla il canale delle misure può nascondere l'attacco | **Scenario 2:** letture MQTT falsificate o ripetute (replay) |
| Gli attaccanti hanno toccato anche le soglie d'allarme | **Scenario 3:** silenziamento del sensore perché l'allarme non scatti |
| Esposizione su IP pubblico e manutenzione remota | Segmentazione, firewall, accesso del manutentore solo via VPN WireGuard |
| Credenziali di fabbrica e autenticazione debole | Autenticazione su interfaccia web e MQTT, TLS sul canale |
| Misure non verificabili | Letture firmate e con timestamp: un messaggio ripetuto viene scartato |
| All'EFS ha funzionato un monitoraggio indipendente | Heartbeat (anche l'assenza di dati è un allarme) e secondo sensore su Arduino, collegato via USB e fuori dalla rete |
| Il danno è stato scoperto al mattino | Rilevamento di anomalie fisiche: setpoint cambiati fuori orario, sbrinamenti non programmati, curve di temperatura impossibili |

---

## Perimetro e uso responsabile

- Il banco gira solo su **dispositivi propri**, in una **rete isolata**, senza alcun contatto con supervisori reali.
- Non sfrutta vulnerabilità di prodotti commerciali. Riproduce la classe di debolezza osservata, cioè funzioni previste ma non protette, **non** il prodotto di un produttore specifico.
- Il case study non contiene codice d'attacco, algoritmi, credenziali, query di ricerca dei dispositivi né indicatori tecnici di compromissione.
- Lo scopo del lavoro è **difensivo**: mostrare quali misure interrompono l'attacco e quanto costano.

## Struttura della repository

```
case-study/    il case study in PDF
vulnerable/    il banco vulnerabile (in arrivo)
hardened/      il banco protetto (in arrivo)
docs/          threat model e relazione finale (in arrivo)
```

## Autore

Diego Bruno, Laurea Magistrale in Ingegneria Informatica, Università di Bologna.
