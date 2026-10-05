# -*- coding: utf-8 -*-
"""Vietinis Flask API serveris, per kurį naršyklės plėtinys siunčia užsakymo dizainus."""
from PySide6.QtCore import QThread, Signal
from flask import Flask, request, jsonify
from werkzeug.serving import make_server

from podbase_core import load_models_data, load_jigs_data, log


# ----------------- FLASK API SERVER (QThread) -----------------
class FlaskServerThread(QThread):
    designs_received = Signal(dict)
    server_failed = Signal(str)

    def __init__(self, port=5000, host="127.0.0.1"):
        super().__init__()
        self.port = port
        self.host = host
        self.app = Flask(__name__)
        self.server = None
        self.setup_routes()

    def setup_routes(self):
        @self.app.route("/api/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "app": "Podbase UV Studio"})

        @self.app.route("/api/models", methods=["GET"])
        def get_models():
            return jsonify(load_models_data())

        @self.app.route("/api/jigs", methods=["GET"])
        def get_jigs():
            return jsonify(load_jigs_data())

        @self.app.before_request
        def check_host():
            # Apsauga nuo DNS rebinding: priimame tik užklausas, adresuotas šiam kompiuteriui
            if self.host in ("127.0.0.1", "localhost"):
                host = (request.host or "").rsplit(":", 1)[0].strip("[]").lower()
                if host not in ("127.0.0.1", "localhost"):
                    return jsonify({"success": False, "error": "Forbidden host"}), 403

        @self.app.route("/api/add_designs", methods=["POST"])
        def add_designs():
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"success": False, "error": "Netinkamas JSON"}), 400
            designs = []
            for d in data.get("designs") or []:
                if not isinstance(d, dict):
                    continue
                d = dict(d)
                d["name"] = str(d.get("name") or "").strip()
                url = str(d.get("url") or "").strip()
                # Tik http(s): vietiniai ir UNC keliai (\\serveris\...) iš išorės neleidžiami,
                # kitaip Windows prisijungtų prie svetimo serverio ir atskleistų NTLM duomenis
                d["url"] = url if url.lower().startswith(("http://", "https://")) else ""
                designs.append(d)
            model = data.get("model")
            model = str(model) if isinstance(model, (str, int)) else None
            job_name = data.get("jobName") or data.get("bidNumber")
            job_name = str(job_name) if isinstance(job_name, (str, int)) else None
            
            log.info(f"Iš plėtinio gauta: {len(designs)} dizain., modelis={model!r}, užsakymas={job_name!r}")
            self.designs_received.emit({
                "designs": designs,
                "model": model,
                "jobName": job_name
            })
            return jsonify({"success": True, "count": len(designs)})

    def run(self):
        try:
            self.server = make_server(self.host, self.port, self.app, threaded=True)
            self.server.serve_forever()
        except Exception as e:
            log.error(f"[Flask server error]: {e}")
            self.server_failed.emit(str(e))

    def stop(self):
        if self.server:
            self.server.shutdown()
