# TaxCare – Tax Health Check Doctor Edition

Platform web untuk dokter Indonesia membandingkan metode pajak NPPN vs Pembukuan Riil.

## Fitur
- Simulator wizard 3 langkah
- Kalkulasi NPPN (Norma 50%) vs Pembukuan Riil
- Tarif progresif PPh Pasal 17 yang akurat
- Bar chart perbandingan visual
- Generate laporan PDF profesional (ReportLab)
- Mobile-responsive UI

## Jalankan Lokal

```bash
# Install dependencies
pip install -r requirements.txt

# Jalankan server
python main.py
# → http://localhost:8000
```

## Struktur Proyek

```
taxcare/
├── main.py                 # Entry point
├── requirements.txt
├── app/
│   ├── server.py           # HTTP server handler
│   ├── calculator.py       # Formula pajak NPPN & Pembukuan
│   ├── pdf_generator.py    # Generate PDF dengan ReportLab
│   ├── templates/
│   │   ├── base.html
│   │   ├── landing.html
│   │   ├── simulator.html
│   │   ├── hasil.html
│   │   └── 404.html
│   └── static/
│       ├── css/main.css
│       └── js/main.js
```

## Deploy ke Railway

1. Push ke GitHub repository
2. Buat project baru di railway.app
3. Connect ke repo GitHub
4. Set environment variable: `PORT=8000`
5. Railway auto-detect Python, deploy otomatis

**railway.toml** (buat di root):
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python main.py"
```

## Deploy ke Render

1. Push ke GitHub
2. Buat Web Service baru di render.com
3. Build command: `pip install -r requirements.txt`
4. Start command: `python main.py`
5. Environment: `PORT=10000` (Render default)

## Upgrade ke FastAPI (Production)

Untuk production dengan lebih banyak fitur, ganti `app/server.py` dengan FastAPI:

```bash
pip install fastapi uvicorn
```

Server sudah didesain agar mudah di-migrate ke FastAPI — semua route
dan business logic terpisah di `calculator.py` dan `pdf_generator.py`.

## Referensi Regulasi

- PER-17/PJ/2015 – Norma dokter 50%
- UU HPP No. 7 Tahun 2021 – Tarif PPh terbaru
- PMK PTKP 2016 (masih berlaku 2026)

---
PT TaxCare Indonesia © 2026
