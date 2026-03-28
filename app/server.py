"""
TaxCare Tax Health Check – Main HTTP server
Python stdlib + Jinja2 + ReportLab
"""
import http.server
import json
import os
import re
import io
import traceback
import urllib.parse
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

BASE_DIR     = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR   = BASE_DIR / "app" / "static"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)
jinja_env.filters["rupiah"] = lambda v: "Rp {:,.0f}".format(float(v or 0)).replace(",", ".")
jinja_env.filters["abs"]    = abs


def render(template_name: str, context: dict = {}) -> str:
    t = jinja_env.get_template(template_name)
    return t.render(**context)


class TaxCareHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"  {self.address_string()} [{self.log_date_time_string()}] {format % args}")

    # ── response helpers ─────────────────────────────────────────────────────

    def send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_pdf(self, pdf_bytes: bytes, filename: str):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def send_error_page(self, status: int, title: str, detail: str = ""):
        html = render("error.html", {"status": status, "title": title, "detail": detail})
        self.send_html(html, status)

    # ── static files ─────────────────────────────────────────────────────────

    def serve_static(self, path: str):
        relative  = re.sub(r"^/static/", "", path)   # proper prefix strip
        file_path = STATIC_DIR / relative
        if not file_path.exists() or not file_path.is_file():
            self.send_error_page(404, "File tidak ditemukan", path)
            return
        ext = file_path.suffix.lower()
        content_types = {
            ".css": "text/css",
            ".js":  "application/javascript",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".woff2": "font/woff2",
        }
        ct   = content_types.get(ext, "application/octet-stream")
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    # ── request body ─────────────────────────────────────────────────────────

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        ct  = self.headers.get("Content-Type", "")
        if "application/json" in ct:
            try:
                return json.loads(raw)
            except Exception:
                return {}
        return dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path   = parsed.path.rstrip("/") or "/"

            if path.startswith("/static"):
                self.serve_static(path)
            elif path == "/":
                self.send_html(render("landing.html"))
            elif path == "/simulator":
                self.send_html(render("simulator.html"))
            elif path == "/hasil":
                # Direct GET on /hasil → redirect back to simulator
                self.send_response(302)
                self.send_header("Location", "/simulator")
                self.end_headers()
            else:
                self.send_html(render("404.html"), 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_error_page(500, "Server Error", str(exc))

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path   = parsed.path.rstrip("/")

            if path == "/simulator/hasil":
                self._handle_simulator_hasil()
            elif path == "/api/simulate":
                self._handle_api_simulate()
            elif path == "/api/pdf":
                self._handle_api_pdf()
            else:
                self.send_json({"ok": False, "error": "Not found"}, 404)

        except Exception as exc:
            traceback.print_exc()
            try:
                self.send_error_page(500, "Terjadi kesalahan server", str(exc))
            except Exception:
                pass  # connection already closed

    # ── route handlers ────────────────────────────────────────────────────────

    def _handle_simulator_hasil(self):
        from app.calculator import hitung_pajak, validate_input
        data   = self.read_body()
        errors = validate_input(data)
        if errors:
            self.send_html(render("simulator.html", {"errors": errors, "prev": data}))
            return
        hasil = hitung_pajak(data)
        self.send_html(render("hasil.html", {"hasil": hasil, "input": data}))

    def _handle_api_simulate(self):
        from app.calculator import hitung_pajak, validate_input
        data   = self.read_body()
        errors = validate_input(data)
        if errors:
            self.send_json({"ok": False, "errors": errors}, 400)
            return
        hasil = hitung_pajak(data)
        self.send_json({"ok": True, "hasil": hasil})

    def _handle_api_pdf(self):
        from app.calculator import hitung_pajak, validate_input
        from app.pdf_generator import generate_pdf
        data   = self.read_body()
        errors = validate_input(data)
        if errors:
            self.send_json({"ok": False, "errors": errors}, 400)
            return
        hasil     = hitung_pajak(data)
        pdf_bytes = generate_pdf(data, hasil)
        nama  = data.get("nama_dokter", "Dokter").replace(" ", "_") or "Dokter"
        tahun = data.get("tahun", "2026")
        self.send_pdf(pdf_bytes, f"TaxCare_{nama}_{tahun}.pdf")


def run(host: str = "0.0.0.0", port: int = 8000):
    import sys
    sys.path.insert(0, str(BASE_DIR))
    httpd = http.server.HTTPServer((host, port), TaxCareHandler)
    print(f"\n  ╔══════════════════════════════════════╗")
    print(f"  ║  TaxCare Tax Health Check            ║")
    print(f"  ║  http://localhost:{port}                ║")
    print(f"  ╚══════════════════════════════════════╝\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    run()
