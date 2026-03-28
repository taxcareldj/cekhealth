"""
Generator laporan PDF menggunakan ReportLab
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import Flowable

# Color palette
BLUE       = HexColor("#007BFF")
DARK_BLUE  = HexColor("#0C447C")
GREEN      = HexColor("#28A745")
LIGHT_BLUE = HexColor("#E6F1FB")
LIGHT_GREEN= HexColor("#EAF3DE")
LIGHT_GRAY = HexColor("#F5F7FA")
MID_GRAY   = HexColor("#CCCCCC")
TEXT_DARK  = HexColor("#1A1A2E")
TEXT_GRAY  = HexColor("#555555")
YELLOW_BG  = HexColor("#FFF8E1")
YELLOW_BD  = HexColor("#FFC107")
RED_LIGHT  = HexColor("#FFEBEE")


def rupiah(n):
    return "Rp {:,.0f}".format(float(n)).replace(",", ".")


def juta(n):
    j = float(n) / 1_000_000
    if j >= 1000:
        return f"Rp {j/1000:.1f} M"
    return f"Rp {j:.0f} juta"


class ColorBar(Flowable):
    """Horizontal bar untuk chart sederhana."""
    def __init__(self, nppn_pph, riil_pph, omzet, width=150*mm, height=14*mm):
        super().__init__()
        self.nppn_pph = nppn_pph
        self.riil_pph = riil_pph
        self.omzet = omzet
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        max_val = max(self.nppn_pph, self.riil_pph, 1)
        bar_max = self.width * 0.7

        labels = [("NPPN (Norma 50%)", self.nppn_pph, "#E24B4A"),
                  ("Pembukuan Riil",   self.riil_pph, "#28A745")]

        for i, (label, val, color) in enumerate(labels):
            y = self.height - (i + 1) * (self.height / 2.2)
            bar_w = (val / max_val) * bar_max

            # Label kiri
            c.setFont("Helvetica", 8)
            c.setFillColor(HexColor("#555555"))
            c.drawString(0, y + 3, label)

            # Bar
            c.setFillColor(HexColor(color))
            c.roundRect(0, y - 8, bar_w, 10, 2, fill=1, stroke=0)

            # Value
            c.setFillColor(HexColor(color))
            c.setFont("Helvetica-Bold", 8)
            c.drawString(bar_w + 4, y - 2, juta(val))

        self.height = self.height


def build_styles():
    styles = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=TEXT_DARK)

    custom = {
        "Title": ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=20,
                                textColor=DARK_BLUE, spaceAfter=4, alignment=TA_CENTER),
        "Subtitle": ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=10,
                                   textColor=TEXT_GRAY, spaceAfter=2, alignment=TA_CENTER),
        "H1": ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=13,
                              textColor=DARK_BLUE, spaceBefore=14, spaceAfter=4),
        "H2": ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11,
                              textColor=DARK_BLUE, spaceBefore=8, spaceAfter=3),
        "Body": ParagraphStyle("Body", fontName="Helvetica", fontSize=9,
                               textColor=TEXT_DARK, leading=14, spaceAfter=3),
        "BodyGray": ParagraphStyle("BodyGray", fontName="Helvetica", fontSize=9,
                                   textColor=TEXT_GRAY, leading=13),
        "Disclaimer": ParagraphStyle("Disclaimer", fontName="Helvetica-Oblique", fontSize=7.5,
                                     textColor=TEXT_GRAY, leading=11, alignment=TA_JUSTIFY),
        "TableCell": ParagraphStyle("TableCell", fontName="Helvetica", fontSize=8.5,
                                    textColor=TEXT_DARK, leading=12),
        "TableCellBold": ParagraphStyle("TableCellBold", fontName="Helvetica-Bold", fontSize=8.5,
                                        textColor=TEXT_DARK, leading=12),
        "Highlight": ParagraphStyle("Highlight", fontName="Helvetica-Bold", fontSize=11,
                                    textColor=GREEN, spaceAfter=2),
        "SmallLabel": ParagraphStyle("SmallLabel", fontName="Helvetica", fontSize=7.5,
                                     textColor=TEXT_GRAY, leading=10),
    }
    return custom


def generate_pdf(data: dict, hasil: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        title="TaxCare Tax Health Check",
        author="PT TaxCare Indonesia",
    )

    S = build_styles()
    story = []
    W = A4[0] - 40*mm  # usable width

    # ── HEADER ──────────────────────────────────────────
    header_data = [[
        Paragraph("<font color='#007BFF'><b>+</b></font> <b>TaxCare</b>", ParagraphStyle(
            "Logo", fontName="Helvetica-Bold", fontSize=16, textColor=DARK_BLUE)),
        Paragraph("Tax Health Check<br/><font size=8 color='#555555'>Doctor Edition</font>",
                  ParagraphStyle("LogoSub", fontName="Helvetica", fontSize=10,
                                 textColor=DARK_BLUE, alignment=TA_RIGHT))
    ]]
    header_tbl = Table(header_data, colWidths=[W*0.5, W*0.5])
    header_tbl.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 1, BLUE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6*mm))

    # ── TITLE ────────────────────────────────────────────
    story.append(Paragraph("Laporan Tax Health Check", S["Title"]))
    story.append(Paragraph(
        f"Tahun Pajak {hasil['tahun']}  •  {hasil['jenis_praktik']}  •  PTKP {hasil['ptkp_status']}  •  "
        f"Dibuat: {datetime.now().strftime('%d %B %Y')}",
        S["Subtitle"]
    ))
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width=W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 4*mm))

    # ── RINGKASAN OMZET ──────────────────────────────────
    story.append(Paragraph("Ringkasan Input", S["H1"]))

    sum_data = [
        ["Omzet Bruto Tahunan", rupiah(hasil["omzet"])],
        ["Jenis Praktik",       hasil["jenis_praktik"]],
        ["Tahun Pajak",         str(hasil["tahun"])],
        ["Status PTKP",         hasil["ptkp_status"] + f" (PTKP {rupiah(hasil['ptkp_nilai'])})"],
        ["Total Biaya Riil",    rupiah(hasil["riil"]["biaya_total"]) +
                                f" ({hasil['riil']['biaya_persen']:.1f}% dari omzet)"],
    ]
    sum_tbl = Table(sum_data, colWidths=[W*0.4, W*0.6])
    sum_tbl.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",  (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), TEXT_DARK),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, LIGHT_GRAY]),
        ("GRID",      (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("PADDING",   (0, 0), (-1, -1), 6),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 5*mm))

    # ── PERBANDINGAN ─────────────────────────────────────
    story.append(Paragraph("Perbandingan NPPN vs Pembukuan Riil", S["H1"]))

    nppn = hasil["nppn"]
    riil = hasil["riil"]

    # Tabel perbandingan
    comp_headers = ["Aspek", "NPPN (Norma 50%)", "Pembukuan Riil"]
    comp_rows = [
        ["Penghasilan Neto",   rupiah(nppn["neto"]),  rupiah(riil["neto"])],
        ["PTKP",               rupiah(nppn["ptkp"]),  rupiah(riil["ptkp"])],
        ["PKP",                rupiah(nppn["pkp"]),   rupiah(riil["pkp"])],
        ["Estimasi PPh Terutang", rupiah(nppn["pph"]), rupiah(riil["pph"])],
    ]

    comp_data = [comp_headers] + comp_rows
    comp_tbl = Table(comp_data, colWidths=[W*0.35, W*0.325, W*0.325])

    rec = hasil["rekomendasi"]
    rec_col = 2 if rec == "pembukuan" else 1

    comp_style = TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",    (0, 1), (0, -1), TEXT_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("GRID",         (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("PADDING",      (0, 0), (-1, -1), 7),
        ("ALIGN",        (1, 0), (-1, -1), "RIGHT"),
        # PPh row highlight
        ("FONTNAME",     (0, 4), (-1, 4), "Helvetica-Bold"),
        ("BACKGROUND",   (0, 4), (-1, 4), LIGHT_BLUE),
    ])

    # Highlight kolom rekomendasi
    if rec == "pembukuan":
        comp_style.add("TEXTCOLOR", (2, 4), (2, 4), GREEN)
        comp_style.add("TEXTCOLOR", (1, 4), (1, 4), HexColor("#E24B4A"))
    elif rec == "nppn":
        comp_style.add("TEXTCOLOR", (1, 4), (1, 4), GREEN)
        comp_style.add("TEXTCOLOR", (2, 4), (2, 4), HexColor("#E24B4A"))

    comp_tbl.setStyle(comp_style)
    story.append(comp_tbl)
    story.append(Spacer(1, 4*mm))

    # ── CHART (bar sederhana) ─────────────────────────────
    chart = ColorBar(nppn["pph"], riil["pph"], hasil["omzet"], width=W*0.7, height=28*mm)
    story.append(chart)
    story.append(Spacer(1, 3*mm))

    # ── REKOMENDASI BOX ───────────────────────────────────
    selisih = hasil["selisih_pph"]
    if rec == "pembukuan":
        rec_label = "Rekomendasi: Pembukuan Riil"
        rec_color = LIGHT_GREEN
        rec_border = GREEN
        rec_amount = f"Hemat hingga {rupiah(selisih)}"
        rec_persen = f"({hasil['selisih_persen']}% dari omzet bruto)"
    elif rec == "nppn":
        rec_label = "Rekomendasi: NPPN"
        rec_color = LIGHT_BLUE
        rec_border = BLUE
        rec_amount = f"Hemat hingga {rupiah(abs(selisih))}"
        rec_persen = f"({hasil['selisih_persen']}% dari omzet bruto)"
    else:
        rec_label = "Kedua metode setara"
        rec_color = YELLOW_BG
        rec_border = YELLOW_BD
        rec_amount = "Selisih: Rp 0"
        rec_persen = ""

    rec_data = [[
        Table([
            [Paragraph(rec_label, ParagraphStyle(
                "RecLabel", fontName="Helvetica-Bold", fontSize=11, textColor=DARK_BLUE))],
            [Paragraph(rec_amount, ParagraphStyle(
                "RecAmt", fontName="Helvetica-Bold", fontSize=14, textColor=GREEN if rec == "pembukuan" else BLUE))],
            [Paragraph(rec_persen, S["SmallLabel"])],
            [Spacer(1, 2*mm)],
            [Paragraph(hasil["insight"], S["Body"])],
        ], colWidths=[W - 16*mm])
    ]]
    rec_tbl = Table(rec_data, colWidths=[W])
    rec_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), rec_color),
        ("BOX",         (0, 0), (-1, -1), 1.5, rec_border),
        ("PADDING",     (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(rec_tbl)
    story.append(Spacer(1, 4*mm))

    # ── RINCIAN BIAYA RIIL ───────────────────────────────
    if riil["coa_detail"]:
        story.append(Paragraph("Rincian Biaya Riil (Chart of Accounts)", S["H2"]))
        coa_headers = ["Kategori Biaya", "Nominal", "% Omzet"]
        coa_rows = [[
            item["label"],
            rupiah(item["nilai"]),
            f"{item['persen']}%"
        ] for item in riil["coa_detail"]]
        coa_rows.append([
            "TOTAL BIAYA RIIL",
            rupiah(riil["biaya_total"]),
            f"{riil['biaya_persen']}%"
        ])

        coa_data = [coa_headers] + coa_rows
        coa_tbl = Table(coa_data, colWidths=[W*0.55, W*0.28, W*0.17])
        coa_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR",    (0, 0), (-1, 0), white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [white, LIGHT_GRAY]),
            ("BACKGROUND",   (0, -1), (-1, -1), LIGHT_BLUE),
            ("FONTNAME",     (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID",         (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("PADDING",      (0, 0), (-1, -1), 6),
            ("ALIGN",        (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(coa_tbl)
        story.append(Spacer(1, 4*mm))

    # ── TARIF REFERENSI ───────────────────────────────────
    story.append(HRFlowable(width=W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph("Referensi Tarif PPh Pasal 17", S["H2"]))
    tarif_data = [
        ["Lapisan PKP", "Tarif"],
        ["s/d Rp 60.000.000", "5%"],
        ["> Rp 60 jt s/d Rp 250 jt", "15%"],
        ["> Rp 250 jt s/d Rp 500 jt", "25%"],
        ["> Rp 500 jt s/d Rp 5 M", "30%"],
        ["> Rp 5 M", "35%"],
    ]
    tarif_tbl = Table(tarif_data, colWidths=[W*0.6, W*0.4])
    tarif_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), HexColor("#E8EAED")),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("GRID",         (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("PADDING",      (0, 0), (-1, -1), 5),
    ]))
    story.append(tarif_tbl)
    story.append(Spacer(1, 5*mm))

    # ── DISCLAIMER + FOOTER ───────────────────────────────
    story.append(HRFlowable(width=W, color=MID_GRAY, thickness=0.5))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "<b>Disclaimer:</b> Laporan ini hanya bersifat estimasi berdasarkan data yang dimasukkan. "
        "Bukan merupakan saran atau konsultasi pajak resmi. Konsultasikan keputusan perpajakan Anda "
        "dengan konsultan pajak bersertifikat atau Kantor Pelayanan Pajak setempat. "
        "Formula berdasarkan PER-17/PJ/2015 dan UU HPP No. 7 Tahun 2021.",
        S["Disclaimer"]
    ))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"PT TaxCare Indonesia  •  taxcare.id  •  Dokumen dibuat otomatis pada "
        f"{datetime.now().strftime('%d %B %Y pukul %H:%M')} WIB",
        ParagraphStyle("Footer", fontName="Helvetica", fontSize=7,
                       textColor=TEXT_GRAY, alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()
