"""
Kalkulasi pajak NPPN vs Pembukuan Riil
Sesuai PER-17/PJ/2015 dan UU PPh Pasal 17 (tarif 2026)
"""

NORMA_DOKTER = 0.50  # 50% sesuai PER-17/PJ/2015

PTKP = {
    "TK/0": 54_000_000,
    "K/0":  58_500_000,
    "K/1":  63_000_000,
    "K/2":  67_500_000,
    "K/3":  72_000_000,
}

TARIF_PPH = [
    (60_000_000,    0.05),
    (190_000_000,   0.15),
    (250_000_000,   0.25),
    (4_500_000_000, 0.30),
    (float("inf"),  0.35),
]

COA_FIELDS = [
    ("gaji_staf",     "Gaji & Tunjangan Staf/Perawat"),
    ("obat_bhp",      "Obat & Bahan Habis Pakai"),
    ("sewa_utilitas", "Sewa Klinik/Ruang + Utilitas"),
    ("depresiasi",    "Depresiasi Alat Medis & Inventaris"),
    ("maintenance",   "Maintenance, Asuransi Malpraktik, Iuran IDI/CME"),
    ("lain_lain",     "Biaya Lain-lain"),
]

PRESET_BIAYA = {"rendah": 0.40, "sedang": 0.55, "tinggi": 0.70}


def parse_rp(s) -> float:
    """Parse angka dari berbagai format: '2.000.000.000', '2000000000', 'Rp 1.250.000'"""
    if s is None:
        return 0.0
    clean = str(s).strip()
    clean = clean.replace("Rp", "").replace(" ", "")
    # Titik sebagai pemisah ribuan (format Indonesia), koma sebagai desimal
    # Jika ada koma, strip titik dulu lalu ganti koma -> titik
    if "," in clean:
        clean = clean.replace(".", "").replace(",", ".")
    else:
        clean = clean.replace(".", "")
    try:
        return float(clean)
    except (ValueError, TypeError):
        return 0.0


def hitung_pph(pkp: float) -> float:
    if pkp <= 0:
        return 0.0
    pph = 0.0
    sisa = pkp
    for batas, tarif in TARIF_PPH:
        if sisa <= 0:
            break
        kena = min(sisa, batas)
        pph += kena * tarif
        sisa -= kena
    return round(pph)


def hitung_pajak(data: dict) -> dict:
    omzet = parse_rp(data.get("omzet", 0))
    ptkp_status = data.get("ptkp_status", "K/1").strip()
    # Normalise key: "K/1" or "K1" both accepted
    if ptkp_status not in PTKP:
        ptkp_status = "K/1"
    ptkp_val = PTKP[ptkp_status]

    # --- NPPN ---
    neto_nppn = omzet * NORMA_DOKTER
    pkp_nppn  = max(0.0, neto_nppn - ptkp_val)
    pph_nppn  = hitung_pph(pkp_nppn)

    # --- Pembukuan Riil ---
    # Prioritas: jumlahkan CoA fields; fallback ke biaya_total
    biaya_coa = sum(parse_rp(data.get(k, 0)) for k, _ in COA_FIELDS)
    if biaya_coa > 0:
        biaya_total = biaya_coa
    else:
        biaya_total = parse_rp(data.get("biaya_total", 0))

    neto_riil = omzet - biaya_total
    pkp_riil  = max(0.0, neto_riil - ptkp_val)
    pph_riil  = hitung_pph(pkp_riil)

    persen_biaya = round(biaya_total / omzet * 100, 1) if omzet > 0 else 0.0
    selisih      = pph_nppn - pph_riil
    selisih_pct  = round(abs(selisih) / omzet * 100, 2) if omzet > 0 else 0.0

    if selisih > 0:
        rekomendasi = "pembukuan"
        badge = "green"
        insight = _insight_pembukuan(persen_biaya, selisih, selisih_pct)
    elif selisih < 0:
        rekomendasi = "nppn"
        badge = "yellow"
        insight = _insight_nppn(persen_biaya, abs(selisih))
    else:
        rekomendasi = "setara"
        badge = "yellow"
        insight = ("Kedua metode menghasilkan pajak yang setara. "
                   "NPPN lebih sederhana dari sisi administrasi.")

    coa_detail = []
    for key, label in COA_FIELDS:
        val = parse_rp(data.get(key, 0))
        if val > 0:
            coa_detail.append({
                "label": label,
                "nilai": val,
                "persen": round(val / omzet * 100, 1) if omzet > 0 else 0,
            })

    max_pph = max(pph_nppn, pph_riil, 1)
    return {
        "omzet":        omzet,
        "ptkp_status":  ptkp_status,
        "ptkp_nilai":   ptkp_val,
        "tahun":        data.get("tahun", "2026"),
        "jenis_praktik": data.get("jenis_praktik", "Mandiri"),

        "nppn": {
            "norma_persen": int(NORMA_DOKTER * 100),
            "neto": neto_nppn,
            "ptkp": ptkp_val,
            "pkp":  pkp_nppn,
            "pph":  pph_nppn,
        },
        "riil": {
            "biaya_total":  biaya_total,
            "biaya_persen": persen_biaya,
            "neto": neto_riil,
            "ptkp": ptkp_val,
            "pkp":  pkp_riil,
            "pph":  pph_riil,
            "coa_detail": coa_detail,
        },

        "rekomendasi":   rekomendasi,
        "badge":         badge,
        "selisih_pph":   selisih,
        "selisih_persen": selisih_pct,
        "insight":       insight,

        "chart": {
            "nppn_bar":   round(pph_nppn / max_pph * 80),
            "riil_bar":   round(pph_riil / max_pph * 80),
            "nppn_label": _fmt_juta(pph_nppn),
            "riil_label": _fmt_juta(pph_riil),
        },
    }


def _insight_pembukuan(persen_biaya, selisih, selisih_pct):
    return (
        f"Dengan biaya riil klinik Anda sekitar {persen_biaya:.0f}% dari omzet, "
        f"Pembukuan Riil menghasilkan neto lebih rendah dari NPPN. "
        f"Estimasi penghematan pajak hingga {_fmt_rupiah(selisih)} "
        f"({selisih_pct}% dari omzet bruto). "
        f"Jika Anda ingin kemudahan administrasi, NPPN tetap legal — "
        f"namun Pembukuan lebih optimal secara finansial."
    )


def _insight_nppn(persen_biaya, selisih):
    return (
        f"Dengan biaya riil sekitar {persen_biaya:.0f}%, NPPN (norma 50%) "
        f"lebih menguntungkan karena norma lebih tinggi dari biaya aktual Anda. "
        f"Menggunakan NPPN menghemat pajak sekitar {_fmt_rupiah(selisih)} "
        f"dibandingkan Pembukuan Riil. "
        f"NPPN juga lebih sederhana — tidak perlu pembukuan lengkap."
    )


def _fmt_rupiah(n: float) -> str:
    return "Rp {:,.0f}".format(n).replace(",", ".")


def _fmt_juta(n: float) -> str:
    j = n / 1_000_000
    if j >= 1000:
        return f"Rp {j/1000:.1f} M"
    return f"Rp {j:.0f} jt"


def validate_input(data: dict) -> list:
    errors = []
    omzet = parse_rp(data.get("omzet", 0))
    if omzet < 1_000_000:
        errors.append("Omzet minimal Rp 1.000.000 — pastikan kolom omzet sudah terisi.")
    if omzet > 100_000_000_000:
        errors.append("Omzet terlalu besar, periksa kembali.")
    return errors
