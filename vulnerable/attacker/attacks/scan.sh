#!/bin/sh
# Ricognizione della rete del negozio con Nmap.
# Gira solo dentro il container dell'attaccante, collegato soltanto alla rete
# interna del banco: non può raggiungere Internet né la rete di casa.
# L'indirizzo .1 è l'interfaccia del PC che ospita Docker e viene escluso.
set -e
RETE="${RETE:-10.77.10.0/24}"
ESCLUSI="${ESCLUSI:-10.77.10.1}"

echo "== Fase 1: host attivi nella rete $RETE =="
nmap -sn -n "$RETE" --exclude "$ESCLUSI" -oG - | grep "Status: Up"

echo
echo "== Fase 2: tutte le porte TCP aperte =="
nmap -n -sS -T4 -p- --open "$RETE" --exclude "$ESCLUSI" | grep -E "scan report|open"

echo
echo "== Fase 3: banner, pagine web e topic MQTT esposti =="
nmap -n -p 80,1883,8080 --open \
  --script http-title,http-server-header,mqtt-subscribe \
  --script-args 'mqtt-subscribe.topic={store/#,$SYS/broker/version}' \
  "$RETE" --exclude "$ESCLUSI" | grep -vE "^(Starting|Host is up|Not shown|MAC Address|Nmap done)"

echo
echo "== Fase 4: identificativo e registri del dispositivo Modbus =="
python recon_modbus.py 10.77.10.10
