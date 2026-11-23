"""Centro di telegestione del manutentore.

Riceve le notifiche d'allarme del supervisore e le mostra in una pagina.
Rappresenta la persona che, di notte, verrebbe avvisata del problema: se una
notifica non arriva qui, nessuno interviene.
"""

import logging
from collections import deque

from flask import Flask, jsonify, render_template, request

log = logging.getLogger("telegestione")
notifications = deque(maxlen=100)
app = Flask(__name__)


@app.post("/notifica")
def receive():
    data = request.get_json(silent=True) or {}
    notifications.appendleft(data)
    log.warning("notifica da %s: %s %s, %s °C", request.remote_addr, data.get("banco"), data.get("tipo"),
                data.get("temperatura_c"))
    return {"ricevuta": True}


@app.get("/api/notifiche")
def api_notifications():
    return jsonify(list(notifications))


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="0.0.0.0", port=8080, threaded=True, use_reloader=False)
