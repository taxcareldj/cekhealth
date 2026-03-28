#!/usr/bin/env python3
"""
TaxCare Tax Health Check – Doctor Edition
Single-file server: python main.py -> http://localhost:8000
"""
import http.server, urllib.parse, json, re, io, sys, os, traceback, sqlite3
from pathlib import Path
from datetime import datetime

# ── CONFIG ───────────────────────────────────────────────────────────────────
WA_NUMBER  = "628116330050"   # nomor WA tanpa + dan tanpa spasi
ADMIN_PASS = "taxcare2026"    # password halaman /admin — ganti sebelum deploy!
DB_PATH    = Path(__file__).parent / "leads.db"

# ── DATABASE ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            nama        TEXT,
            jenis       TEXT,
            omzet       REAL,
            biaya       REAL,
            pct_biaya   REAL,
            ptkp        TEXT,
            pph_nppn    REAL,
            pph_riil    REAL,
            selisih     REAL,
            rekomendasi TEXT,
            tahun       TEXT,
            ip          TEXT,
            konsultasi  INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS konsultasi_clicks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            lead_id    INTEGER,
            ip         TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_lead(h, ip=""):
    conn = sqlite3.connect(str(DB_PATH))
    cur  = conn.execute("""
        INSERT INTO leads
          (created_at, nama, jenis, omzet, biaya, pct_biaya, ptkp,
           pph_nppn, pph_riil, selisih, rekomendasi, tahun, ip)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        h.get("nama",""),
        h.get("jenis",""),
        h.get("omzet",0),
        h.get("biaya",0),
        h.get("pct_biaya",0),
        h.get("ptkp_s",""),
        h.get("pph_n",0),
        h.get("pph_r",0),
        h.get("diff",0),
        h.get("rek",""),
        str(h.get("tahun","2026")),
        ip,
    ))
    lead_id = cur.lastrowid
    conn.commit()
    conn.close()
    return lead_id

def save_konsultasi(lead_id, ip=""):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO konsultasi_clicks (created_at, lead_id, ip) VALUES (?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), lead_id, ip)
    )
    conn.execute(
        "UPDATE leads SET konsultasi=1 WHERE id=?", (lead_id,)
    )
    conn.commit()
    conn.close()

def get_leads(limit=200):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = sqlite3.connect(str(DB_PATH))
    stats = {}
    stats["total"]       = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    stats["konsultasi"]  = conn.execute("SELECT COUNT(*) FROM leads WHERE konsultasi=1").fetchone()[0]
    stats["pembukuan"]   = conn.execute("SELECT COUNT(*) FROM leads WHERE rekomendasi='pembukuan'").fetchone()[0]
    stats["nppn"]        = conn.execute("SELECT COUNT(*) FROM leads WHERE rekomendasi='nppn'").fetchone()[0]
    avg = conn.execute("SELECT AVG(omzet) FROM leads WHERE omzet>0").fetchone()[0]
    stats["avg_omzet"]   = round(avg or 0)
    total_hemat = conn.execute("SELECT SUM(ABS(selisih)) FROM leads WHERE rekomendasi='pembukuan'").fetchone()[0]
    stats["total_hemat"] = round(total_hemat or 0)
    conn.close()
    return stats

init_db()

# ── TAX CALCULATOR ──────────────────────────────────────────────────────────
PTKP = {"TK/0":54e6,"K/0":58.5e6,"K/1":63e6,"K/2":67.5e6,"K/3":72e6}
TARIF = [(60e6,.05),(190e6,.15),(250e6,.25),(4500e6,.30),(float('inf'),.35)]

def parse_rp(s):
    if not s: return 0.0
    c = str(s).strip().replace('Rp','').replace(' ','')
    c = c.replace('.','').replace(',','.')
    try: return float(c)
    except: return 0.0

def pph(pkp):
    if pkp <= 0: return 0.0
    tax, left = 0.0, pkp
    for batas, rate in TARIF:
        if left <= 0: break
        tax += min(left, batas) * rate
        left -= batas
    return round(tax)

def hitung(data):
    omzet   = parse_rp(data.get('omzet',0))
    ptkp_s  = data.get('ptkp_status','K/1')
    ptkp_v  = PTKP.get(ptkp_s, 63e6)
    COA     = ['gaji_staf','obat_bhp','sewa_utilitas','depresiasi','maintenance','lain_lain']
    biaya   = sum(parse_rp(data.get(k,0)) for k in COA) or parse_rp(data.get('biaya_total',0))
    neto_n  = omzet * 0.5
    neto_r  = omzet - biaya
    pph_n   = pph(max(0, neto_n - ptkp_v))
    pph_r   = pph(max(0, neto_r - ptkp_v))
    diff    = pph_n - pph_r
    rek     = 'pembukuan' if diff > 0 else ('nppn' if diff < 0 else 'setara')
    pct_b   = round(biaya/omzet*100,1) if omzet else 0
    pct_d   = round(abs(diff)/omzet*100,2) if omzet else 0
    mx      = max(pph_n, pph_r, 1)
    COA_LABELS = {
        'gaji_staf':'Gaji & Tunjangan Staf/Perawat',
        'obat_bhp':'Obat & Bahan Habis Pakai',
        'sewa_utilitas':'Sewa Klinik/Ruang + Utilitas',
        'depresiasi':'Depresiasi Alat Medis & Inventaris',
        'maintenance':'Maintenance, Asuransi, Iuran IDI/CME',
        'lain_lain':'Biaya Lain-lain'
    }
    coa_detail = [{'k':k,'label':COA_LABELS[k],'nilai':parse_rp(data.get(k,0)),
                   'pct':round(parse_rp(data.get(k,0))/omzet*100,1) if omzet else 0}
                  for k in COA if parse_rp(data.get(k,0)) > 0]
    return dict(
        omzet=omzet, biaya=biaya, pct_biaya=pct_b,
        ptkp_s=ptkp_s, ptkp_v=ptkp_v,
        neto_n=neto_n, pph_n=pph_n,
        neto_r=neto_r, pph_r=pph_r,
        diff=diff, pct_diff=pct_d, rek=rek,
        bar_n=round(pph_n/mx*80), bar_r=round(pph_r/mx*80),
        tahun=data.get('tahun','2026'),
        jenis=data.get('jenis_praktik','Mandiri'),
        nama=data.get('nama_dokter','Dokter') or 'Dokter',
        coa_detail=coa_detail,
    )

def rp(n): return 'Rp {:,.0f}'.format(float(n)).replace(',','.')
def juta(n):
    j=float(n)/1e6
    return f'Rp {j/1000:.1f} M' if j>=1000 else f'Rp {j:.0f} jt'

# ── HTML PAGES ───────────────────────────────────────────────────────────────
CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --blue:#1A56FF;--bd:#0A2D99;--bl:#EEF3FF;--bxl:#F7F9FF;
  --green:#00B87A;--gl:#E6FAF3;
  --red:#F03E3E;
  --amber:#F59E0B;--al:#FFFBEB;
  --g50:#F8FAFC;--g100:#F1F5F9;--g200:#E2E8F0;--g300:#CBD5E1;
  --g400:#94A3B8;--g500:#64748B;--g600:#475569;--g700:#334155;
  --g800:#1E293B;--g900:#0F172A;
  --r:10px;--rs:8px;--rl:16px;
  --font:'Segoe UI',-apple-system,BlinkMacSystemFont,sans-serif;
}
html{font-size:16px;scroll-behavior:smooth}
body{font-family:var(--font);color:var(--g800);background:var(--g50);line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--blue);text-decoration:none}
.nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.95);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--g200);padding:0 24px;height:60px;
  display:flex;align-items:center;justify-content:space-between}
.nav-logo{font-size:17px;font-weight:800;color:var(--g900);display:flex;align-items:center;gap:9px;text-decoration:none}
.nav-mark{width:32px;height:32px;background:var(--blue);border-radius:9px;display:flex;align-items:center;
  justify-content:center;color:#fff;font-size:17px;font-weight:900;box-shadow:0 3px 10px rgba(26,86,255,.35)}
.nav-mark span{color:var(--blue)}
.btn{display:inline-flex;align-items:center;gap:6px;padding:10px 20px;border-radius:var(--rs);
  font-family:var(--font);font-size:14px;font-weight:600;cursor:pointer;
  border:1.5px solid transparent;transition:all .15s;text-decoration:none;white-space:nowrap;line-height:1}
.bp{background:var(--blue);color:#fff;border-color:var(--blue);box-shadow:0 2px 8px rgba(26,86,255,.3)}
.bp:hover{background:#1248E8;transform:translateY(-1px)}
.bs{background:var(--green);color:#fff;border-color:var(--green);box-shadow:0 2px 8px rgba(0,184,122,.3)}
.bs:hover{background:#009E69;transform:translateY(-1px)}
.bg{background:transparent;color:var(--g600);border-color:var(--g200)}
.bg:hover{background:var(--g100)}
.blg{padding:13px 28px;font-size:16px;border-radius:var(--r)}
.bblk{width:100%;justify-content:center}
.hero{padding:72px 24px 64px;background:linear-gradient(155deg,#EEF3FF 0%,#FAFBFF 55%,#E6FAF3 100%);
  border-bottom:1px solid var(--g200);text-align:center;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 60% 40% at 50% -5%,rgba(26,86,255,.07),transparent)}
.eyebrow{display:inline-flex;align-items:center;gap:6px;background:var(--bl);color:var(--bd);
  font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  padding:5px 14px;border-radius:20px;margin-bottom:18px;border:1px solid rgba(26,86,255,.15)}
.hero h1{font-size:clamp(30px,5vw,50px);font-weight:800;line-height:1.15;color:var(--g900);
  margin-bottom:16px;letter-spacing:-.03em}
.hero h1 em{font-style:normal;color:var(--blue)}
.hero-sub{font-size:17px;color:var(--g500);max-width:520px;margin:0 auto 28px;line-height:1.65}
.trust-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:20px}
.chip{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--g500);font-weight:500;
  background:#fff;padding:5px 12px;border-radius:20px;border:1px solid var(--g200);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.dot{width:6px;height:6px;border-radius:50%;background:var(--green);flex-shrink:0}
.feats{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;
  padding:52px 24px;max-width:960px;margin:0 auto}
.fc{background:#fff;border:1px solid var(--g200);border-radius:var(--rl);padding:26px;
  box-shadow:0 2px 10px rgba(0,0,0,.05);transition:transform .2s,box-shadow .2s}
.fc:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.09)}
.fi{width:48px;height:48px;border-radius:12px;background:var(--bl);
  display:flex;align-items:center;justify-content:center;font-size:22px;margin-bottom:14px}
.fc h3{font-size:15px;font-weight:700;color:var(--g900);margin-bottom:7px}
.fc p{font-size:13px;color:var(--g500);line-height:1.6}
.how{background:#fff;border-top:1px solid var(--g200);border-bottom:1px solid var(--g200);padding:56px 24px}
.how-inner{max-width:720px;margin:0 auto;text-align:center}
.slbl{font-size:12px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--blue);margin-bottom:6px}
.stitle{font-size:26px;font-weight:800;color:var(--g900);margin-bottom:6px;letter-spacing:-.02em}
.ssub{font-size:15px;color:var(--g500);margin-bottom:36px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:36px}
.step{padding:0 16px;text-align:center}
.step+.step{border-left:1px dashed var(--g200)}
.snum{width:42px;height:42px;border-radius:50%;background:var(--blue);color:#fff;
  font-size:17px;font-weight:800;display:flex;align-items:center;justify-content:center;
  margin:0 auto 12px;box-shadow:0 3px 10px rgba(26,86,255,.3)}
.snumg{background:var(--green);box-shadow:0 3px 10px rgba(0,184,122,.3)}
.stname{font-size:14px;font-weight:700;color:var(--g800);margin-bottom:4px}
.stdesc{font-size:13px;color:var(--g500);line-height:1.5}
.wrap{max-width:820px;margin:0 auto;padding:28px 16px 56px}
.sim-hd h2{font-size:24px;font-weight:800;color:var(--g900);letter-spacing:-.02em}
.sim-hd p{color:var(--g500);margin-top:3px;font-size:14px}
.deadline{background:var(--al);border:1.5px solid var(--amber);border-radius:var(--r);
  padding:11px 16px;margin:16px 0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.dl-badge{background:var(--amber);color:#fff;font-size:11px;font-weight:700;
  padding:3px 10px;border-radius:20px;letter-spacing:.04em;white-space:nowrap}
.dl-txt{font-size:13px;color:#92400E;font-weight:500}
.pbar{display:flex;align-items:center;gap:0;margin:20px 0 28px}
.ps{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;color:var(--g400)}
.ps.done{color:var(--green)}.ps.active{color:var(--blue)}
.pn{width:28px;height:28px;border-radius:50%;border:2px solid currentColor;
  display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0}
.ps.active .pn{background:var(--blue);color:#fff;border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,86,255,.15)}
.ps.done .pn{background:var(--green);color:#fff;border-color:var(--green)}
.pc{flex:1;height:2px;background:var(--g200);margin:0 6px;max-width:50px}
.pc.done{background:var(--green)}
.card{background:#fff;border:1px solid var(--g200);border-radius:var(--rl);
  padding:28px;box-shadow:0 1px 6px rgba(0,0,0,.05);margin-bottom:14px}
.slbl2{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  color:var(--g400);margin-bottom:14px;padding-bottom:9px;border-bottom:1px solid var(--g100)}
.fg{margin-bottom:16px}
.fg label{display:block;font-size:13px;font-weight:600;color:var(--g700);margin-bottom:6px}
.fg .hint{font-size:11px;color:var(--g400);font-weight:400;margin-left:3px}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.iw{display:flex;align-items:center;border:1.5px solid var(--g200);border-radius:var(--rs);
  background:#fff;transition:border-color .15s,box-shadow .15s;overflow:hidden}
.iw:focus-within{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,86,255,.1)}
.ipfx{padding:10px 13px;background:var(--g50);border-right:1px solid var(--g200);
  font-size:13px;color:var(--g500);white-space:nowrap;font-weight:500}
.iw input,.iw select{flex:1;border:none;outline:none;padding:10px 13px;
  font-size:14px;font-family:var(--font);background:transparent;color:var(--g800)}
.pi{width:100%;padding:10px 13px;border:1.5px solid var(--g200);border-radius:var(--rs);
  font-size:14px;font-family:var(--font);color:var(--g800);outline:none;
  transition:border-color .15s,box-shadow .15s}
.pi:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,86,255,.1)}
.rg{display:flex;flex-wrap:wrap;gap:8px}
.ro{display:flex;align-items:center;gap:7px;padding:9px 16px;border-radius:var(--rs);
  border:1.5px solid var(--g200);font-size:13px;font-weight:500;cursor:pointer;
  transition:all .15s;background:#fff;color:var(--g700);user-select:none}
.ro:hover{border-color:var(--blue);color:var(--blue)}
.ro.sel{border-color:var(--blue);background:var(--bl);color:var(--blue)}
.ro input{display:none}
.prow{display:flex;gap:8px;margin-bottom:16px}
.pb{flex:1;padding:9px 6px;text-align:center;border:1.5px solid var(--g200);border-radius:var(--rs);
  font-family:var(--font);font-size:12px;font-weight:600;cursor:pointer;background:#fff;
  color:var(--g600);transition:all .15s;line-height:1.3}
.pb:hover{border-color:var(--blue);color:var(--blue)}
.pb.active{border-color:var(--blue);background:var(--bl);color:var(--blue)}
.acc{border:1.5px solid var(--g200);border-radius:var(--r);overflow:hidden}
.ach{padding:13px 17px;background:var(--g50);display:flex;justify-content:space-between;
  align-items:center;cursor:pointer;font-size:14px;font-weight:700;color:var(--g700)}
.ach:hover{background:var(--g100)}
.atg{font-size:12px;color:var(--blue);font-weight:500}
.acb{display:none}.acb.open{display:block}
.cr{display:flex;align-items:center;justify-content:space-between;
  padding:10px 17px;border-bottom:1px solid var(--g100);gap:12px}
.cr:last-child{border-bottom:none}
.cl{font-size:13px;color:var(--g700);flex:1;line-height:1.4}
.cf{display:flex;align-items:center;gap:5px}
.cpfx{font-size:12px;color:var(--g400);font-weight:500}
.ci{width:150px;padding:7px 9px;text-align:right;border:1.5px solid var(--g200);border-radius:var(--rs);
  font-size:13px;color:var(--g800);outline:none;transition:border-color .15s;font-variant-numeric:tabular-nums}
.ci:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(26,86,255,.1)}
.tot{display:flex;justify-content:space-between;align-items:center;
  padding:13px 17px;background:var(--bxl);border-top:2px solid var(--bl)}
.tot-l{font-size:13px;font-weight:700;color:var(--bd)}
.tot-v{font-size:15px;font-weight:700;color:var(--blue)}
.tot-p{font-size:11px;color:var(--g500);margin-top:1px}
.fa{display:flex;justify-content:flex-end;align-items:center;gap:12px;
  padding-top:22px;border-top:1px solid var(--g100);margin-top:6px}
.err{font-size:12px;color:var(--red);margin-top:4px;min-height:16px}
.alert{padding:12px 16px;border-radius:var(--rs);font-size:13px;margin-bottom:16px}
.alert-d{background:#FFF0F0;border:1px solid #FFCDD2;color:#B71C1C}
.disc{font-size:12px;color:var(--g400);text-align:center;padding:14px 24px;
  border-top:1px solid var(--g200);line-height:1.6;background:#fff}
footer{background:var(--g900);color:var(--g400);padding:28px 24px;text-align:center;font-size:13px;line-height:2}
footer strong{color:#fff}
footer a{color:var(--g400);text-decoration:none}
footer a:hover{color:#fff}
.hw{max-width:900px;margin:0 auto;padding:28px 16px 56px}
.ht h2{font-size:22px;font-weight:800;color:var(--g900);letter-spacing:-.02em}
.ht p{color:var(--g500);font-size:13px;margin-top:3px}
.saving{background:linear-gradient(135deg,var(--gl),#F0FDF9);border:2px solid var(--green);
  border-radius:var(--rl);padding:24px 28px;margin:16px 0;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}
.saving.bl{background:linear-gradient(135deg,var(--bl),var(--bxl));border-color:var(--blue)}
.sv-l{flex:1}
.sv-lbl{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--g500);margin-bottom:3px}
.sv-amt{font-size:clamp(26px,4vw,38px);font-weight:800;color:var(--green);letter-spacing:-.03em;line-height:1.1}
.sv-amt.bl{color:var(--blue)}
.sv-pct{font-size:13px;color:var(--g500);margin-top:3px}
.sv-r{text-align:center;padding:14px 20px;background:rgba(255,255,255,.7);
  border-radius:var(--r);border:1px solid rgba(0,0,0,.06)}
.sv-rl{font-size:12px;color:var(--g500);margin-bottom:3px}
.sv-rv{font-size:18px;font-weight:800;letter-spacing:-.02em}
.cgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}
.cc{background:#fff;border:1.5px solid var(--g200);border-radius:var(--rl);padding:20px;
  box-shadow:0 1px 5px rgba(0,0,0,.04)}
.cc.wg{border-color:var(--green);border-width:2px;box-shadow:0 0 0 4px rgba(0,184,122,.07)}
.cc.wb{border-color:var(--blue);border-width:2px;box-shadow:0 0 0 4px rgba(26,86,255,.07)}
.cbadge{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:700;
  padding:3px 10px;border-radius:20px;margin-bottom:9px}
.bg2{background:var(--gl);color:#065F46}
.bb2{background:var(--bl);color:var(--bd)}
.ct{font-size:14px;font-weight:700;color:var(--g800);margin-bottom:12px;letter-spacing:-.01em}
.mr{display:flex;justify-content:space-between;align-items:baseline;
  padding:7px 0;border-bottom:1px solid var(--g100);font-size:13px}
.mr:last-child{border-bottom:none}
.ml{color:var(--g500)}
.mv{font-weight:600;color:var(--g800);font-variant-numeric:tabular-nums}
.mv.big{font-size:15px;font-weight:800}
.mv.green{color:var(--green)}.mv.red{color:var(--red)}.mv.blue{color:var(--blue)}
.mr.pph{margin-top:6px;padding-top:11px;border-top:2px solid var(--g200)}
.chrt{background:#fff;border:1px solid var(--g200);border-radius:var(--rl);
  padding:22px;margin:16px 0;box-shadow:0 1px 5px rgba(0,0,0,.04)}
.chrt-t{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--g400);margin-bottom:18px}
.bars{display:flex;flex-direction:column;gap:14px}
.bi{display:flex;align-items:center;gap:12px}
.bl2{font-size:13px;font-weight:500;color:var(--g600);min-width:140px}
.bt{flex:1;height:30px;background:var(--g100);border-radius:6px;overflow:hidden}
.bf{height:100%;border-radius:6px;display:flex;align-items:center;padding-left:10px;
  font-size:12px;font-weight:700;color:#fff;width:0%;transition:width 1.1s cubic-bezier(.16,1,.3,1)}
.bf.red{background:linear-gradient(90deg,#F03E3E,#FF6B6B)}
.bf.grn{background:linear-gradient(90deg,#00B87A,#00D68F)}
.bv{font-variant-numeric:tabular-nums;font-size:13px;font-weight:700;min-width:80px;text-align:right}
.bv.vr{color:var(--red)}.bv.vg{color:var(--green)}
.ins{border-radius:var(--rl);padding:18px 20px;margin:16px 0;
  font-size:14px;line-height:1.75;font-weight:500}
.ins.g{background:var(--gl);color:#065F46;border:1.5px solid rgba(0,184,122,.2)}
.ins.b{background:var(--bl);color:var(--bd);border:1.5px solid rgba(26,86,255,.15)}
.dtbl{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
.dtbl th{padding:8px 11px;text-align:left;font-size:11px;font-weight:700;
  letter-spacing:.05em;text-transform:uppercase;color:var(--g400);
  background:var(--g50);border-bottom:1px solid var(--g200)}
.dtbl td{padding:8px 11px;border-bottom:1px solid var(--g100);color:var(--g700)}
.dtbl td:last-child,.dtbl th:last-child{text-align:right}
.dtbl tfoot td{padding:9px 11px;font-weight:700;color:var(--bd);background:var(--bxl)}
.ra{display:flex;gap:11px;flex-wrap:wrap;margin:16px 0}
.up{background:#fff;border:2px solid var(--green);border-radius:var(--rl);
  padding:22px 26px;display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:14px;box-shadow:0 0 0 4px rgba(0,184,122,.05)}
.up-t{font-size:16px;font-weight:800;color:var(--g900);margin-bottom:3px;letter-spacing:-.01em}
.up-s{font-size:13px;color:var(--g500)}
@media(max-width:640px){
  .cgrid{grid-template-columns:1fr}.frow{grid-template-columns:1fr}
  .saving{padding:18px}.steps{grid-template-columns:1fr;gap:20px}
  .step+.step{border-left:none;border-top:1px dashed var(--g200);padding-top:20px}
  .bl2{min-width:100px;font-size:11px}.ra{flex-direction:column}
}
"""

JS = r"""
function fmtN(n){return new Intl.NumberFormat('id-ID').format(Math.round(n))}
function parseN(s){
  if(!s&&s!=='0')return 0;
  let c=String(s).trim().replace(/Rp/g,'').replace(/\s/g,'');
  // Indonesian format: dot=thousand sep, comma=decimal
  if(c.indexOf(',')>-1){c=c.replace(/\./g,'').replace(',','.')}
  else{c=c.replace(/\./g,'')}
  return parseFloat(c)||0;
}
function fmtCoa(el){const v=parseN(el.value);el.value=v>0?fmtN(v):'0'}
function rawCoa(el){const v=parseN(el.value);if(v>0)el.value=v}
function fmtOmzet(){
  const el=document.getElementById('omzet');
  if(!el)return;
  const v=parseN(el.value);
  if(v>0)el.value=fmtN(v);
}
function onOmzetInput(){
  document.getElementById('omzet-err').textContent='';
  updateTotal();
}
function toggleAcc(el){
  const b=el.nextElementSibling;
  const lbl=el.querySelector('.atg');
  const o=b.classList.toggle('open');
  if(lbl)lbl.textContent=o?'sembunyikan ▲':'tampilkan ▼';
}
const PRESETS={
  rendah:{gaji_staf:.132,obat_bhp:.116,sewa_utilitas:.072,depresiasi:.040,maintenance:.020,lain_lain:.020},
  sedang:{gaji_staf:.182,obat_bhp:.160,sewa_utilitas:.099,depresiasi:.055,maintenance:.028,lain_lain:.028},
  tinggi:{gaji_staf:.231,obat_bhp:.203,sewa_utilitas:.126,depresiasi:.070,maintenance:.035,lain_lain:.035},
};
function applyPreset(key,btn){
  document.querySelectorAll('.pb').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const omzet=parseN(document.getElementById('omzet').value);
  if(!omzet){document.getElementById('omzet-err').textContent='Isi omzet dulu';return}
  const d=PRESETS[key];
  Object.keys(d).forEach(k=>{
    const el=document.getElementById('ci-'+k);
    if(el)el.value=fmtN(Math.round(omzet*d[k]));
  });
  document.querySelector('.acb').classList.add('open');
  document.querySelector('.atg').textContent='sembunyikan ▲';
  updateTotal();
}
function updateTotal(){
  const omzet=parseN(document.getElementById('omzet').value);
  const keys=['gaji_staf','obat_bhp','sewa_utilitas','depresiasi','maintenance','lain_lain'];
  const total=keys.reduce((s,k)=>{const el=document.getElementById('ci-'+k);return s+(el?parseN(el.value):0)},0);
  const tv=document.getElementById('tot-v');
  const tp=document.getElementById('tot-p');
  if(tv)tv.textContent='Rp '+fmtN(total);
  if(tp)tp.textContent=omzet>0?((total/omzet)*100).toFixed(1)+'% dari omzet':'';
}
function selRadio(el,grp){
  document.querySelectorAll('.rg-'+grp+' .ro').forEach(o=>o.classList.remove('sel'));
  el.classList.add('sel');
  const inp=el.querySelector('input[type=radio]');
  if(inp)inp.checked=true;
}
function doSubmit(){
  // Strip format before submit
  const omzetEl=document.getElementById('omzet');
  if(omzetEl){
    const v=parseN(omzetEl.value);
    if(v<1000000){
      document.getElementById('omzet-err').textContent='Omzet minimal Rp 1.000.000';
      omzetEl.focus();
      return;
    }
    omzetEl.value=v;
  }
  const keys=['gaji_staf','obat_bhp','sewa_utilitas','depresiasi','maintenance','lain_lain'];
  keys.forEach(k=>{
    const el=document.getElementById('ci-'+k);
    if(el)el.value=parseN(el.value)||0;
  });
  document.getElementById('sim-form').submit();
}
// animate bars on hasil page
window.addEventListener('DOMContentLoaded',function(){
  updateTotal();
  setTimeout(function(){
    document.querySelectorAll('.bf[data-w]').forEach(function(b){
      b.style.width=b.dataset.w+'%';
    });
  },100);
});
"""

def page(title, body, extra_js=""):
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | TaxCare</title>
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
  <a href="/" class="nav-logo"><div class="nav-mark">+</div>Tax<span style="color:var(--blue)">Care</span></a>
  <a href="/simulator" class="btn bp">Mulai Cek Pajak</a>
</nav>
{body}
<div class="disc">Hasil simulasi hanya estimasi. Konsultasikan dengan konsultan pajak bersertifikat untuk keputusan resmi.</div>
<footer><strong>PT TaxCare Indonesia</strong> &nbsp;·&nbsp;
<a href="#">Kebijakan Privasi</a> &nbsp;·&nbsp; <a href="#">Kontak</a><br>
PER-17/PJ/2015 · UU HPP No.7/2021 · © 2026</footer>
<script>{JS}</script>
{extra_js}
</body></html>"""

def landing_html():
    return page("Cek Pajak Klinik Anda dalam 5 Menit", """
<section class="hero">
  <div class="eyebrow"><span class="dot"></span>Tax Health Check – Doctor Edition</div>
  <h1>Cek Pajak Klinik Anda<br>dalam <em>5 Menit</em></h1>
  <p class="hero-sub">NPPN 50% atau Pembukuan Riil? Ketahui mana yang lebih hemat
  sebelum deadline 31 Maret — tanpa perlu jadi ahli pajak.</p>
  <a href="/simulator" class="btn bs blg">Mulai Tax Health Check Gratis →</a>
  <div class="trust-row">
    <span class="chip"><span class="dot"></span>Didukung aturan DJP</span>
    <span class="chip"><span class="dot"></span>PER-17/PJ/2015 & PMK terkini</span>
    <span class="chip"><span class="dot"></span>100% gratis & rahasia</span>
    <span class="chip"><span class="dot"></span>Laporan PDF instan</span>
  </div>
</section>
<div class="feats">
  <div class="fc"><div class="fi">📊</div><h3>Estimasi Penghematan Pajak</h3>
  <p>Bandingkan NPPN 50% vs Pembukuan Riil secara instan. Lihat selisih PPh dalam rupiah nyata.</p></div>
  <div class="fc"><div class="fi">📋</div><h3>Template CoA Dokter</h3>
  <p>Chart of Accounts khusus praktik dokter Indonesia. Preset biaya otomatis dalam hitungan detik.</p></div>
  <div class="fc"><div class="fi">📄</div><h3>Laporan PDF Profesional</h3>
  <p>Unduh laporan lengkap dengan tabel perbandingan, grafik, dan rekomendasi TaxCare.</p></div>
</div>
<section class="how">
  <div class="how-inner">
    <div class="slbl">Cara Kerja</div>
    <div class="stitle">3 Langkah, Kurang dari 5 Menit</div>
    <div class="steps">
      <div class="step"><div class="snum">1</div><div class="stname">Profil Praktik</div>
      <div class="stdesc">Jenis praktik dan omzet bruto tahunan</div></div>
      <div class="step"><div class="snum">2</div><div class="stname">Biaya Klinik</div>
      <div class="stdesc">Preset cepat atau rincian CoA dokter</div></div>
      <div class="step"><div class="snum snumg">3</div><div class="stname">Hasil & PDF</div>
      <div class="stdesc">Rekomendasi instan + laporan siap unduh</div></div>
    </div>
    <div style="margin-top:32px"><a href="/simulator" class="btn bp blg">Mulai Sekarang — Gratis →</a></div>
  </div>
</section>""")

COA_ROWS = [
    ('gaji_staf',     'Gaji &amp; Tunjangan Staf/Perawat'),
    ('obat_bhp',      'Obat &amp; Bahan Habis Pakai'),
    ('sewa_utilitas', 'Sewa Klinik/Ruang + Utilitas'),
    ('depresiasi',    'Depresiasi Alat Medis &amp; Inventaris'),
    ('maintenance',   'Maintenance, Asuransi, Iuran IDI/CME'),
    ('lain_lain',     'Biaya Lain-lain'),
]

def simulator_html(errors=None, prev=None):
    prev = prev or {}
    err_block = ''
    if errors:
        err_block = '<div class="alert alert-d">' + ''.join(f'<div>⚠ {e}</div>' for e in errors) + '</div>'

    coa_rows = ''
    for k, lbl in COA_ROWS:
        val = prev.get(k, '0') or '0'
        coa_rows += f'''<div class="cr">
          <span class="cl">{lbl}</span>
          <div class="cf"><span class="cpfx">Rp</span>
          <input class="ci" id="ci-{k}" name="{k}" type="text" value="{val}"
                 inputmode="numeric"
                 onfocus="rawCoa(this)" onblur="fmtCoa(this)" oninput="updateTotal()">
          </div></div>'''

    jp = prev.get('jenis_praktik', 'Mandiri')
    radios = ''
    for v in ['Mandiri', 'RS Only', 'Hybrid (RS + Klinik)']:
        sel = 'sel' if (v == jp or (jp == 'Hybrid' and v.startswith('Hybrid'))) else ''
        chk = 'checked' if sel else ''
        radios += f'<label class="ro {sel} rg-jenis" onclick="selRadio(this,\'jenis\')"><input type="radio" name="jenis_praktik" value="{v}" {chk}>{v}</label>'

    ptkp_opts = ''
    for val, lbl in [('TK/0','TK/0 – Tidak kawin, tanpa tanggungan (Rp 54.000.000)'),
                     ('K/0','K/0 – Kawin, tanpa tanggungan (Rp 58.500.000)'),
                     ('K/1','K/1 – Kawin, 1 tanggungan (Rp 63.000.000)'),
                     ('K/2','K/2 – Kawin, 2 tanggungan (Rp 67.500.000)'),
                     ('K/3','K/3 – Kawin, 3 tanggungan (Rp 72.000.000)')]:
        sel = 'selected' if val == prev.get('ptkp_status', 'K/1') else ''
        ptkp_opts += f'<option value="{val}" {sel}>{lbl}</option>'

    omzet_val = prev.get('omzet', '') or ''

    body = f"""
<div class="wrap">
  <div class="sim-hd"><h2>Tax Health Check</h2>
  <p>Isi data klinik Anda — estimasi selesai dalam &lt;1 detik</p></div>
  <div class="deadline">
    <span class="dl-badge">⚠ DEADLINE</span>
    <span class="dl-txt">Pemberitahuan NPPN ke KPP paling lambat <strong>31 Maret 2026</strong>.</span>
  </div>
  <div class="pbar">
    <div class="ps done"><div class="pn">✓</div><span>Profil</span></div>
    <div class="pc done"></div>
    <div class="ps active"><div class="pn">2</div><span>Biaya Riil</span></div>
    <div class="pc"></div>
    <div class="ps"><div class="pn">3</div><span>Data Pajak</span></div>
  </div>
  {err_block}
  <form id="sim-form" method="POST" action="/simulator/hasil" autocomplete="off">
    <div class="card">
      <div class="slbl2">Langkah 1 — Profil Praktik</div>
      <div class="fg">
        <label>Nama Dokter <span class="hint">(opsional)</span></label>
        <div class="iw"><span class="ipfx">dr.</span>
        <input type="text" name="nama_dokter" placeholder="Nama lengkap"
               value="{prev.get('nama_dokter','') or ''}"></div>
      </div>
      <div class="fg">
        <label>Jenis Praktik</label>
        <div class="rg">{radios}</div>
      </div>
      <div class="frow">
        <div class="fg">
          <label>Omzet Bruto Tahunan</label>
          <div class="iw"><span class="ipfx">Rp</span>
          <input type="text" id="omzet" name="omzet"
                 placeholder="2.000.000.000" value="{omzet_val}"
                 inputmode="numeric" autocomplete="off"
                 oninput="onOmzetInput()" onblur="fmtOmzet()"></div>
          <div id="omzet-err" class="err"></div>
        </div>
        <div class="fg">
          <label>Tahun Pajak</label>
          <div class="iw"><select name="tahun">
            <option value="2026" selected>2026</option>
            <option value="2025">2025</option>
          </select></div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="slbl2">Langkah 2 — Estimasi Biaya Riil Klinik</div>
      <p style="font-size:13px;color:var(--g500);margin-bottom:14px">
        Pilih preset atau isi rincian CoA di bawah.</p>
      <div class="prow">
        <button type="button" class="pb" onclick="applyPreset('rendah',this)">
          Rendah<br><span style="font-size:10px;opacity:.75">~40% omzet</span></button>
        <button type="button" class="pb active" onclick="applyPreset('sedang',this)">
          Sedang<br><span style="font-size:10px;opacity:.75">~55% omzet</span></button>
        <button type="button" class="pb" onclick="applyPreset('tinggi',this)">
          Tinggi<br><span style="font-size:10px;opacity:.75">~70% omzet</span></button>
      </div>
      <div class="acc">
        <div class="ach" onclick="toggleAcc(this)">
          📋 Rincian Chart of Accounts Dokter
          <span class="atg">sembunyikan ▲</span>
        </div>
        <div class="acb open">
          {coa_rows}
          <div class="tot">
            <div><div class="tot-l">Total Biaya Riil</div>
            <div class="tot-p" id="tot-p">0% dari omzet</div></div>
            <div class="tot-v" id="tot-v">Rp 0</div>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="slbl2">Langkah 3 — Data Pajak Pribadi
        <span style="text-transform:none;font-size:11px;color:var(--g400);font-weight:400">(opsional)</span>
      </div>
      <div class="fg">
        <label>Status PTKP</label>
        <div class="iw"><select name="ptkp_status">{ptkp_opts}</select></div>
      </div>
      <p style="font-size:12px;color:var(--g400)">Jika tidak yakin, biarkan default K/1.</p>
    </div>
    <div style="text-align:center;padding:6px 0 12px">
      <button type="button" class="btn bp blg" style="min-width:260px" onclick="doSubmit()">
        Hitung &amp; Lihat Hasil →
      </button>
      <p style="font-size:12px;color:var(--g400);margin-top:9px">Estimasi selesai dalam &lt;1 detik</p>
    </div>
  </form>
</div>"""
    return page("Simulator Pajak Dokter", body)

def hasil_html(h, inp, lead_id=0):
    rek   = h['rek']
    is_p  = rek == 'pembukuan'
    is_n  = rek == 'nppn'
    diff  = abs(h['diff'])

    if is_p:
        saving = f'''<div class="saving">
          <div class="sv-l"><div class="sv-lbl">Estimasi penghematan pajak</div>
          <div class="sv-amt">{rp(diff)}</div>
          <div class="sv-pct">{h["pct_diff"]}% dari omzet bruto · dengan Pembukuan Riil</div></div>
          <div class="sv-r"><div class="sv-rl">Rekomendasi</div>
          <div class="sv-rv" style="color:var(--green)">Pembukuan Riil</div></div></div>'''
    elif is_n:
        saving = f'''<div class="saving bl">
          <div class="sv-l"><div class="sv-lbl">Estimasi penghematan pajak</div>
          <div class="sv-amt bl">{rp(diff)}</div>
          <div class="sv-pct">{h["pct_diff"]}% dari omzet bruto · dengan NPPN</div></div>
          <div class="sv-r"><div class="sv-rl">Rekomendasi</div>
          <div class="sv-rv" style="color:var(--blue)">NPPN (Norma 50%)</div></div></div>'''
    else:
        saving = ''

    nppn_win = 'wb' if is_n else ''
    riil_win = 'wg' if is_p else ''
    nppn_pph_cls = 'green' if is_n else 'red'
    riil_pph_cls = 'green' if is_p else 'red'
    nppn_badge = '<div class="cbadge bb2">✓ Rekomendasi TaxCare</div>' if is_n else ''
    riil_badge = '<div class="cbadge bg2">✓ Rekomendasi TaxCare</div>' if is_p else ''

    coa_rows = ''
    for item in h['coa_detail']:
        coa_rows += f"<tr><td>{item['label']}</td><td>{rp(item['nilai'])}</td><td>{item['pct']}%</td></tr>"
    coa_section = ''
    if coa_rows:
        coa_section = f'''<div class="chrt">
          <div class="chrt-t">Rincian Biaya Riil (Chart of Accounts)</div>
          <table class="dtbl">
            <thead><tr><th>Kategori</th><th style="text-align:right">Nominal</th><th style="text-align:right">% Omzet</th></tr></thead>
            <tbody>{coa_rows}</tbody>
            <tfoot><tr><td>Total Biaya Riil</td><td style="text-align:right">{rp(h['biaya'])}</td>
            <td style="text-align:right">{h['pct_biaya']}%</td></tr></tfoot>
          </table></div>'''

    if is_p:
        insight = (f"Dengan biaya riil klinik Anda sekitar <strong>{h['pct_biaya']:.0f}%</strong> dari omzet, "
                   f"Pembukuan Riil menghasilkan neto lebih rendah dari NPPN. "
                   f"Estimasi penghematan pajak hingga <strong>{rp(diff)}</strong> "
                   f"({h['pct_diff']}% dari omzet bruto). "
                   f"Jika ingin kemudahan administrasi, NPPN tetap legal — namun Pembukuan lebih optimal secara finansial.")
        ins_cls = 'g'
    elif is_n:
        insight = (f"Dengan biaya riil sekitar <strong>{h['pct_biaya']:.0f}%</strong>, NPPN (norma 50%) "
                   f"lebih menguntungkan karena norma lebih tinggi dari biaya aktual Anda. "
                   f"Menggunakan NPPN menghemat pajak sekitar <strong>{rp(diff)}</strong> "
                   f"dibandingkan Pembukuan Riil. NPPN juga lebih sederhana secara administrasi.")
        ins_cls = 'b'
    else:
        insight = f"Kedua metode menghasilkan pajak yang setara dengan biaya riil {h['pct_biaya']}%. NPPN lebih sederhana dari sisi administrasi."
        ins_cls = 'b'

    nama = inp.get('nama_dokter','Dokter') or 'Dokter'

    body = f'''<div class="hw">
  <div class="ht" style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:16px">
    <div><h2>Hasil Tax Health Check – Tahun Pajak {h["tahun"]}</h2>
    <p>Omzet: <strong>{rp(h["omzet"])}</strong> · {h["jenis"]} · PTKP {h["ptkp_s"]}</p></div>
    <a href="/simulator" class="btn bg">← Ubah Data</a>
  </div>
  {saving}
  <div class="cgrid">
    <div class="cc {nppn_win}">{nppn_badge}
      <div class="ct">NPPN – Norma 50%</div>
      <div class="mr"><span class="ml">Omzet Bruto</span><span class="mv">{rp(h["omzet"])}</span></div>
      <div class="mr"><span class="ml">Norma (50%)</span><span class="mv">× 50%</span></div>
      <div class="mr"><span class="ml">Penghasilan Neto</span><span class="mv blue">{rp(h["neto_n"])}</span></div>
      <div class="mr"><span class="ml">PTKP ({h["ptkp_s"]})</span><span class="mv">– {rp(h["ptkp_v"])}</span></div>
      <div class="mr"><span class="ml">PKP</span><span class="mv">{rp(max(0,h["neto_n"]-h["ptkp_v"]))}</span></div>
      <div class="mr pph"><span class="ml" style="font-weight:700">Est. PPh Terutang</span>
      <span class="mv big {nppn_pph_cls}">{rp(h["pph_n"])}</span></div>
    </div>
    <div class="cc {riil_win}">{riil_badge}
      <div class="ct">Pembukuan Riil</div>
      <div class="mr"><span class="ml">Omzet Bruto</span><span class="mv">{rp(h["omzet"])}</span></div>
      <div class="mr"><span class="ml">Total Biaya Riil</span><span class="mv">– {rp(h["biaya"])}</span></div>
      <div class="mr"><span class="ml">% Biaya Omzet</span><span class="mv">{h["pct_biaya"]}%</span></div>
      <div class="mr"><span class="ml">Penghasilan Neto</span><span class="mv blue">{rp(h["neto_r"])}</span></div>
      <div class="mr"><span class="ml">PTKP ({h["ptkp_s"]})</span><span class="mv">– {rp(h["ptkp_v"])}</span></div>
      <div class="mr pph"><span class="ml" style="font-weight:700">Est. PPh Terutang</span>
      <span class="mv big {riil_pph_cls}">{rp(h["pph_r"])}</span></div>
    </div>
  </div>
  <div class="chrt">
    <div class="chrt-t">Perbandingan PPh Terutang</div>
    <div class="bars">
      <div class="bi"><span class="bl2">NPPN (Norma 50%)</span>
        <div class="bt"><div class="bf red" data-w="{h["bar_n"]}" style="width:0%">{juta(h["pph_n"]) if h["bar_n"]>25 else ""}</div></div>
        <span class="bv vr">{juta(h["pph_n"])}</span></div>
      <div class="bi"><span class="bl2">Pembukuan Riil</span>
        <div class="bt"><div class="bf grn" data-w="{h["bar_r"]}" style="width:0%">{juta(h["pph_r"]) if h["bar_r"]>25 else ""}</div></div>
        <span class="bv vg">{juta(h["pph_r"])}</span></div>
    </div>
  </div>
  <div class="ins {ins_cls}">💡 {insight}</div>
  {coa_section}
  <div class="ra">
    <button class="btn bp blg" onclick="downloadPDF()">⬇ Download Laporan PDF</button>
    <a href="/simulator" class="btn bg blg">← Ubah Data</a>
  </div>
  <div class="up" id="konsul-card">
    <div>
      <div class="up-t">Ingin TaxCare yang kelola segalanya?</div>
      <div class="up-s">Paket Full Compliance: pembukuan bulanan, laporan keuangan, dan SPT tahunan.</div>
    </div>
    <button class="btn bs blg" onclick="bukaKonsultasi({lead_id})">
      💬 Konsultasi Gratis via WhatsApp →
    </button>
  </div>
</div>'''

    # PDF data embedded as JSON for download
    pdf_js = f"""<script>
const _H = {json.dumps(dict(
    omzet=h['omzet'], biaya=h['biaya'], pct_biaya=h['pct_biaya'],
    ptkp_s=h['ptkp_s'], ptkp_v=h['ptkp_v'],
    neto_n=h['neto_n'], pph_n=h['pph_n'],
    neto_r=h['neto_r'], pph_r=h['pph_r'],
    diff=float(h['diff']), pct_diff=h['pct_diff'],
    rek=h['rek'], tahun=h['tahun'], jenis=h['jenis'],
    nama=h['nama'], coa_detail=h['coa_detail'],
    pph_n_fmt=rp(h['pph_n']), pph_r_fmt=rp(h['pph_r']),
    omzet_fmt=rp(h['omzet']), biaya_fmt=rp(h['biaya']),
    diff_fmt=rp(abs(h['diff'])),
), ensure_ascii=False)};
function fmtRP(n){{return 'Rp '+new Intl.NumberFormat('id-ID').format(Math.round(n))}}
function downloadPDF(){{
  const d=_H;
  const coaRows=(d.coa_detail||[]).map(i=>`<tr><td>${{i.label}}</td><td style="text-align:right;font-family:monospace">${{fmtRP(i.nilai)}}</td><td style="text-align:right">${{i.pct}}%</td></tr>`).join('');
  const html=`<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">
<title>TaxCare Tax Health Check ${{d.tahun}}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:'Segoe UI',sans-serif;color:#1E293B;padding:32px;max-width:800px;margin:0 auto;font-size:14px}}
.hdr{{display:flex;justify-content:space-between;padding-bottom:14px;border-bottom:2px solid #1A56FF;margin-bottom:20px}}
.logo{{font-size:20px;font-weight:800;color:#0A2D99}}.logo span{{color:#1A56FF}}
.meta{{font-size:12px;color:#64748B;text-align:right}}
h1{{font-size:18px;font-weight:800;color:#0A2D99;margin:0 0 4px}}
h2{{font-size:13px;font-weight:700;color:#0A2D99;margin:18px 0 7px;text-transform:uppercase;letter-spacing:.05em}}
table{{width:100%;border-collapse:collapse;margin-bottom:14px;font-size:13px}}
th{{background:#0A2D99;color:#fff;padding:7px 11px;text-align:left;font-size:11px}}
td{{padding:7px 11px;border-bottom:1px solid #E2E8F0}}
tr:nth-child(even)td{{background:#F8FAFC}}
.pph td{{font-weight:700;background:#EEF3FF!important;font-size:14px}}
.green{{color:#00B87A}}.red{{color:#F03E3E}}
.save{{background:#E6FAF3;border:2px solid #00B87A;border-radius:8px;padding:14px 18px;margin-bottom:18px}}
.save.bl{{background:#EEF3FF;border-color:#1A56FF}}
.save-amt{{font-size:26px;font-weight:800;color:#00B87A}}.save-amt.bl{{color:#1A56FF}}
.disc{{font-size:11px;color:#94A3B8;margin-top:20px;padding-top:14px;border-top:1px solid #E2E8F0;font-style:italic;line-height:1.6}}
@media print{{button{{display:none}}}}</style></head><body>
<div class="hdr"><div><div class="logo">Tax<span>Care</span></div>
<div style="font-size:12px;color:#64748B">Tax Health Check – Doctor Edition</div></div>
<div class="meta">dr. ${{d.nama}}<br>Tahun Pajak ${{d.tahun}}<br>${{new Date().toLocaleDateString('id-ID',{{day:'2-digit',month:'long',year:'numeric'}})}}</div></div>
<h1>Laporan Tax Health Check – Tahun Pajak ${{d.tahun}}</h1>
<p style="font-size:12px;color:#64748B;margin-bottom:16px">Omzet: <strong>${{fmtRP(d.omzet)}}</strong> · ${{d.jenis}} · PTKP ${{d.ptkp_s}} · Biaya Riil: ${{d.pct_biaya}}%</p>
<div class="save ${{d.rek==='nppn'?'bl':''}}">
  <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.05em">Estimasi Penghematan Pajak</div>
  <div class="save-amt ${{d.rek==='nppn'?'bl':''}}">${{fmtRP(Math.abs(d.diff))}}</div>
  <div style="font-size:12px;color:#64748B">${{d.pct_diff}}% dari omzet · Metode: ${{d.rek==='pembukuan'?'Pembukuan Riil':'NPPN (Norma 50%)'}}</div>
</div>
<h2>Perbandingan NPPN vs Pembukuan Riil</h2>
<table><thead><tr><th>Aspek</th><th>NPPN (Norma 50%)</th><th>Pembukuan Riil</th></tr></thead>
<tbody>
<tr><td>Penghasilan Neto</td><td>${{fmtRP(d.neto_n)}}</td><td>${{fmtRP(d.neto_r)}}</td></tr>
<tr><td>PTKP (${{d.ptkp_s}})</td><td>${{fmtRP(d.ptkp_v)}}</td><td>${{fmtRP(d.ptkp_v)}}</td></tr>
<tr class="pph"><td><strong>Est. PPh Terutang</strong></td>
<td class="${{d.rek==='nppn'?'green':'red'}}"><strong>${{fmtRP(d.pph_n)}}</strong></td>
<td class="${{d.rek==='pembukuan'?'green':'red'}}"><strong>${{fmtRP(d.pph_r)}}</strong></td></tr>
</tbody></table>
${{d.coa_detail&&d.coa_detail.length?`<h2>Rincian Biaya Riil</h2><table><thead><tr><th>Kategori</th><th style="text-align:right">Nominal</th><th style="text-align:right">% Omzet</th></tr></thead><tbody>${{coaRows}}</tbody><tfoot><tr><td><strong>Total</strong></td><td style="text-align:right;font-weight:700">${{fmtRP(d.biaya)}}</td><td style="text-align:right;font-weight:700">${{d.pct_biaya}}%</td></tr></tfoot></table>`:''}}
<h2>Tarif PPh Pasal 17</h2>
<table><thead><tr><th>Lapisan PKP</th><th>Tarif</th></tr></thead><tbody>
<tr><td>s/d Rp 60.000.000</td><td>5%</td></tr>
<tr><td>Rp 60 jt – Rp 250 jt</td><td>15%</td></tr>
<tr><td>Rp 250 jt – Rp 500 jt</td><td>25%</td></tr>
<tr><td>Rp 500 jt – Rp 5 M</td><td>30%</td></tr>
<tr><td>> Rp 5 M</td><td>35%</td></tr>
</tbody></table>
<div class="disc"><strong>Disclaimer:</strong> Laporan ini hanya estimasi. Bukan saran pajak resmi. Formula berdasarkan PER-17/PJ/2015 dan UU HPP No.7/2021.<br>PT TaxCare Indonesia · ${{new Date().toLocaleString('id-ID')}} WIB</div>
<script>window.print()<\\/script></body></html>`;
  const blob=new Blob([html],{{type:'text/html'}});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;a.download='TaxCare_'+d.nama.replace(/\\s+/g,'_')+'_'+d.tahun+'.html';
  a.click();URL.revokeObjectURL(url);
  setTimeout(()=>alert('File HTML laporan diunduh.\\nBuka di browser → Ctrl+P → Save as PDF.'),300);
}}
async function bukaKonsultasi(leadId){{
  // Catat klik konsultasi ke database
  try{{
    await fetch('/api/konsultasi',{{
      method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{lead_id:leadId}})
    }});
  }}catch(e){{}}
  // Buka WhatsApp dengan pesan otomatis
  const nama=_H.nama||'Dokter';
  const omzet=new Intl.NumberFormat('id-ID').format(Math.round(_H.omzet));
  const rek=_H.rek==='pembukuan'?'Pembukuan Riil':'NPPN (Norma 50%)';
  const hemat=new Intl.NumberFormat('id-ID').format(Math.round(Math.abs(_H.diff)));
  const msg=`Halo TaxCare, saya dr. ${{nama}} ingin konsultasi lebih lanjut mengenai pajak klinik saya.%0A%0AHasil Tax Health Check:%0A- Omzet: Rp ${{omzet}}%0A- Rekomendasi: ${{rek}}%0A- Estimasi hemat: Rp ${{hemat}}%0A%0AMohon bantuannya, terima kasih.`;
  window.open(`https://wa.me/{WA_NUMBER}?text=${{msg}}`,'_blank');
}}
</script>"""
    return page(f"Hasil Tax Health Check {h['tahun']}", body, pdf_js)

def admin_html(leads, stats):
    def rp(n):
        try: return "Rp {:,.0f}".format(float(n)).replace(",",".")
        except: return "Rp 0"

    rows_html = ""
    for i, l in enumerate(leads):
        rek_color = {"pembukuan":"#00B87A","nppn":"#1A56FF","setara":"#F59E0B"}.get(l.get("rekomendasi",""),  "#94A3B8")
        konsul_icon = "✅" if l.get("konsultasi") else "–"
        rows_html += f"""<tr style="background:{'#F8FAFC' if i%2==0 else '#fff'}">
          <td style="color:#94A3B8;font-size:12px">{l.get('id','')}</td>
          <td style="font-size:12px">{l.get('created_at','')}</td>
          <td><strong>{l.get('nama','–') or '–'}</strong></td>
          <td style="font-size:12px">{l.get('jenis','–')}</td>
          <td style="font-family:monospace;font-size:12px">{rp(l.get('omzet',0))}</td>
          <td style="font-size:12px">{l.get('pct_biaya',0)}%</td>
          <td style="font-family:monospace;font-size:12px">{rp(l.get('pph_nppn',0))}</td>
          <td style="font-family:monospace;font-size:12px">{rp(l.get('pph_riil',0))}</td>
          <td style="font-weight:700;color:{rek_color};font-size:12px">{l.get('rekomendasi','–').upper()}</td>
          <td style="font-family:monospace;font-size:12px">{rp(abs(l.get('selisih',0)))}</td>
          <td style="text-align:center">{konsul_icon}</td>
          <td style="font-size:11px;color:#94A3B8">{l.get('ip','')}</td>
        </tr>"""

    if not rows_html:
        rows_html = '<tr><td colspan="12" style="text-align:center;padding:40px;color:#94A3B8">Belum ada data. Leads akan muncul setelah ada yang klik Hitung &amp; Lihat Hasil.</td></tr>'

    total_hemat_str = rp(stats.get("total_hemat", 0))
    avg_omzet_str   = rp(stats.get("avg_omzet", 0))
    conv_rate = round(stats["konsultasi"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0

    return f"""<!DOCTYPE html>
<html lang="id"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Dashboard | TaxCare</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#F1F5F9;color:#1E293B;font-size:14px}}
.topbar{{background:#0A2D99;color:#fff;padding:14px 28px;display:flex;align-items:center;justify-content:space-between}}
.topbar h1{{font-size:18px;font-weight:800}}
.topbar span{{font-size:12px;opacity:.75}}
.main{{padding:24px 28px;max-width:1400px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:24px}}
.sc{{background:#fff;border-radius:12px;padding:16px 18px;border:1px solid #E2E8F0;box-shadow:0 1px 4px rgba(0,0,0,.05)}}
.sc-lbl{{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#94A3B8;margin-bottom:5px}}
.sc-val{{font-size:26px;font-weight:800;color:#0A2D99}}
.sc-sub{{font-size:11px;color:#94A3B8;margin-top:2px}}
.card{{background:#fff;border-radius:12px;border:1px solid #E2E8F0;box-shadow:0 1px 4px rgba(0,0,0,.05);overflow:hidden}}
.card-hd{{padding:14px 18px;border-bottom:1px solid #E2E8F0;display:flex;align-items:center;justify-content:space-between}}
.card-hd h2{{font-size:15px;font-weight:700;color:#0A2D99}}
.card-hd a{{font-size:12px;color:#1A56FF;text-decoration:none;border:1px solid #1A56FF;padding:5px 12px;border-radius:6px}}
.card-hd a:hover{{background:#EEF3FF}}
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:900px}}
th{{padding:9px 11px;text-align:left;font-size:11px;font-weight:700;letter-spacing:.05em;
   text-transform:uppercase;color:#94A3B8;background:#F8FAFC;border-bottom:1px solid #E2E8F0;white-space:nowrap}}
td{{padding:9px 11px;border-bottom:1px solid #F1F5F9;vertical-align:middle}}
tr:hover td{{background:#F0F9FF!important}}
.badge{{display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:20px}}
.export-bar{{padding:12px 18px;background:#F8FAFC;border-top:1px solid #E2E8F0;
  display:flex;align-items:center;gap:12px;font-size:13px;color:#64748B}}
</style>
</head><body>
<div class="topbar">
  <h1>🏥 TaxCare – Admin Dashboard</h1>
  <span>Leads & Konsultasi Tracker · {datetime.now().strftime("%d %b %Y %H:%M")}</span>
</div>
<div class="main">
  <div class="stats">
    <div class="sc">
      <div class="sc-lbl">Total Leads</div>
      <div class="sc-val">{stats["total"]}</div>
      <div class="sc-sub">Hitung &amp; Lihat Hasil diklik</div>
    </div>
    <div class="sc">
      <div class="sc-lbl">Klik Konsultasi WA</div>
      <div class="sc-val" style="color:#00B87A">{stats["konsultasi"]}</div>
      <div class="sc-sub">Konversi {conv_rate}% dari leads</div>
    </div>
    <div class="sc">
      <div class="sc-lbl">Rekomen Pembukuan</div>
      <div class="sc-val" style="color:#00B87A">{stats["pembukuan"]}</div>
      <div class="sc-sub">Potensi klien pembukuan</div>
    </div>
    <div class="sc">
      <div class="sc-lbl">Rekomen NPPN</div>
      <div class="sc-val" style="color:#1A56FF">{stats["nppn"]}</div>
      <div class="sc-sub">Perlu edukasi pembukuan</div>
    </div>
    <div class="sc">
      <div class="sc-lbl">Rata-rata Omzet</div>
      <div class="sc-val" style="font-size:18px">{avg_omzet_str}</div>
      <div class="sc-sub">Per lead</div>
    </div>
    <div class="sc">
      <div class="sc-lbl">Total Potensi Hemat</div>
      <div class="sc-val" style="font-size:18px">{total_hemat_str}</div>
      <div class="sc-sub">Agregat semua leads</div>
    </div>
  </div>

  <div class="card">
    <div class="card-hd">
      <h2>Daftar Leads ({stats["total"]} total)</h2>
      <a href="/admin/export" onclick="exportCSV();return false">⬇ Export CSV</a>
    </div>
    <div class="tbl-wrap">
      <table>
        <thead><tr>
          <th>#</th><th>Waktu</th><th>Nama Dokter</th><th>Jenis</th>
          <th>Omzet</th><th>% Biaya</th><th>PPh NPPN</th><th>PPh Riil</th>
          <th>Rekomendasi</th><th>Hemat</th><th>WA</th><th>IP</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <div class="export-bar">
      <span>Menampilkan {min(len(leads),500)} data terbaru</span>
      <span>·</span>
      <span>Password admin: ubah ADMIN_PASS di main.py sebelum deploy</span>
    </div>
  </div>
</div>
<script>
function exportCSV(){{
  const rows=[['ID','Waktu','Nama','Jenis','Omzet','%Biaya','PPh NPPN','PPh Riil','Rekomendasi','Hemat','Konsultasi WA','IP']];
  document.querySelectorAll('tbody tr').forEach(tr=>{{
    const cols=[...tr.querySelectorAll('td')].map(td=>'"'+td.textContent.trim().replace(/"/g,'""')+'"');
    if(cols.length>1) rows.push(cols);
  }});
  const csv=rows.map(r=>r.join(',')).join('\n');
  const blob=new Blob(['\uFEFF'+csv],{{type:'text/csv;charset=utf-8'}});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='TaxCare_Leads_{datetime.now().strftime("%Y%m%d")}.csv';
  a.click();
}}
</script>
</body></html>"""


# ── HTTP SERVER ───────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt%args}")

    def _html(self, html, status=200):
        b = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _json(self, d, status=200):
        b = json.dumps(d).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get('Content-Length',0))
        if not n: return {}
        raw = self.rfile.read(n).decode('utf-8','replace')
        ct = self.headers.get('Content-Type','')
        if 'json' in ct:
            try: return json.loads(raw)
            except: return {}
        return dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))

    def _require_auth_and_show_admin(self):
        auth = self.headers.get('Authorization','')
        import base64
        ok = False
        if auth.startswith('Basic '):
            try:
                decoded = base64.b64decode(auth[6:]).decode('utf-8','replace')
                _, pw = decoded.split(':',1)
                ok = (pw == ADMIN_PASS)
            except: pass
        if not ok:
            self.send_response(401)
            self.send_header('WWW-Authenticate','Basic realm="TaxCare Admin"')
            self.send_header('Content-Length','0')
            self.end_headers()
            return
        leads = get_leads(500)
        stats = get_stats()
        self._html(admin_html(leads, stats))

    def do_GET(self):
        try:
            p = urllib.parse.urlparse(self.path).path.rstrip('/') or '/'
            if p == '/':
                self._html(landing_html())
            elif p == '/simulator':
                self._html(simulator_html())
            elif p in ('/hasil', '/simulator/hasil'):
                self.send_response(302)
                self.send_header('Location','/simulator')
                self.end_headers()
            elif p == '/admin':
                self._require_auth_and_show_admin()
            else:
                self._html(f'<h2 style="padding:60px;text-align:center">404 – <a href="/">Kembali</a></h2>', 404)
        except Exception:
            traceback.print_exc()

    def do_POST(self):
        try:
            p = urllib.parse.urlparse(self.path).path.rstrip('/')
            data = self._body()
            if p == '/simulator/hasil':
                errors = []
                omzet = parse_rp(data.get('omzet',0))
                if omzet < 1e6:
                    errors.append('Omzet minimal Rp 1.000.000 — pastikan kolom omzet sudah terisi.')
                if errors:
                    self._html(simulator_html(errors=errors, prev=data))
                    return
                h = hitung(data)
                ip = self.client_address[0] if self.client_address else ""
                lead_id = save_lead(h, ip)
                self._html(hasil_html(h, data, lead_id))
            elif p == '/api/simulate':
                omzet = parse_rp(data.get('omzet',0))
                if omzet < 1e6:
                    self._json({'ok':False,'error':'Omzet minimal Rp 1.000.000'}, 400)
                    return
                self._json({'ok':True,'hasil':hitung(data)})
            elif p == '/api/konsultasi':
                lead_id = int(data.get('lead_id', 0) or 0)
                ip = self.client_address[0] if self.client_address else ""
                if lead_id:
                    save_konsultasi(lead_id, ip)
                self._json({'ok': True, 'wa': f'https://wa.me/{WA_NUMBER}'})
            else:
                self._json({'ok':False,'error':'Not found'}, 404)
        except Exception:
            traceback.print_exc()
            try:
                self._html('<h2 style="padding:60px;text-align:center">500 – Server Error. Lihat terminal.<br><a href="/simulator">Kembali</a></h2>', 500)
            except: pass

def run(host='0.0.0.0', port=8000):
    httpd = http.server.HTTPServer((host, port), Handler)
    print(f'\n  ╔══════════════════════════════════╗')
    print(f'  ║  TaxCare Tax Health Check        ║')
    print(f'  ║  http://localhost:{port}            ║')
    print(f'  ╚══════════════════════════════════╝\n')
    try: httpd.serve_forever()
    except KeyboardInterrupt: print('\n  Stopped.')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    run(port=port)
