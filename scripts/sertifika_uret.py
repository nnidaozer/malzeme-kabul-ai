#!/usr/bin/env python3
"""Kabul dokümanından sentetik tedarikçi sertifikaları (CoC/TR) üretir.

Çıktılar (KLASOR altında):
  json/S-001.json ...   sertifika tablosunun ham hücreleri (Sertifika şeması)
  pdf/S-001.pdf ...     aynı sertifikanın PDF görünümü (3 tedarikçi düzeni)
  dogru_kararlar.json   her sertifikanın doğru kararı (DogruKarar listesi)
  ozet.csv              sertifika, şablon, hata türü, açıklama, doğru karar
  istem_enjeksiyonu/    aynı düzende 10 sertifika (S-151...): değerler doğru,
                        içine istem enjeksiyonu metni gizli (8. hata türü,
                        docs/guvenlik.md). PDF'te metin ayrıca beyaz ve 1
                        puntoluk görünmez paragraf olarak da durur.

PDF için reportlab gerekir (pip install -e ".[dev]").

Kullanım:
  python scripts/sertifika_uret.py data/cikti/MIL-PRF-23377K_kabul_dokumani.json \
      --cikti data/sentetik/sertifikalar/MIL-PRF-23377K
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from malzeme_kabul.sema import KabulDokumani
from malzeme_kabul.sertifika_uretici import UretilenSertifika, enjeksiyon_uret, uret

KOK = Path(__file__).resolve().parents[1]
FONT_YOLLARI = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf")

BASLIKLAR = {
    "en": {
        "baslik": "CERTIFICATE OF CONFORMANCE AND TEST REPORT",
        "ad": "Test", "metot": "Method", "sart": "Requirement", "sonuc": "Result", "birim": "Units",
        "urun": "Product", "spec": "Specification", "parti": "Batch/Lot", "uretim": "Date of manufacture",
        "skt": "Expiry", "po": "Customer PO", "no": "Certificate No",
        "beyan": "We hereby certify that the material supplied conforms to the specification referenced above.",
        "imza": "Quality Assurance Manager",
    },
    "tr": {
        "baslik": "UYGUNLUK SERTİFİKASI VE TEST RAPORU",
        "ad": "Test", "metot": "Metot", "sart": "Şart", "sonuc": "Sonuç", "birim": "Birim",
        "urun": "Ürün", "spec": "Standart", "parti": "Parti No", "uretim": "Üretim tarihi",
        "skt": "Son kullanma", "po": "Sipariş No", "no": "Sertifika No",
        "beyan": "Teslim edilen malzemenin yukarıda belirtilen şartnameye uygun olduğunu beyan ederiz.",
        "imza": "Kalite Güvence Müdürü",
    },
}


def _font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for yol in FONT_YOLLARI:
        if Path(yol).exists():
            pdfmetrics.registerFont(TTFont("Govde", yol))
            return "Govde"
    return "Helvetica"


def pdf_yaz(u: UretilenSertifika, yol: Path, font: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    s, sb = u.sertifika, u.sablon
    b = BASLIKLAR[sb.dil]
    stil = ParagraphStyle("g", fontName=font, fontSize=9, leading=11)
    buyuk = ParagraphStyle("b", fontName=font, fontSize=13, leading=16)
    ogeler = [
        Paragraph(sb.tedarikci, buyuk),
        Paragraph(sb.adres, stil),
        Spacer(1, 8),
        Paragraph(b["baslik"], buyuk),
        Spacer(1, 6),
    ]
    bilgi = [
        [b["no"], s.sertifika_no, b["po"], s.siparis_no],
        [b["urun"], s.urun, b["parti"], s.parti_no],
        [b["spec"], s.standart_atfi, b["uretim"], s.uretim_tarihi],
        ["", "", b["skt"], s.son_kullanma_tarihi],
    ]
    t = Table(bilgi, colWidths=[80, 200, 90, 110])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), font, 8.5)]))
    ogeler += [t, Spacer(1, 10)]

    alan = {"ad": "test_adi", "metot": "metot", "sart": "sart", "sonuc": "sonuc", "birim": "birim"}
    tablo = [[b[k] for k in sb.sutunlar]]
    for satir in s.satirlar:
        tablo.append([Paragraph(str(getattr(satir, alan[k]) or ""), stil) for k in sb.sutunlar])
    genislik = {"ad": 170, "metot": 85, "sart": 90, "sonuc": 80, "birim": 55}
    t = Table(tablo, colWidths=[genislik[k] for k in sb.sutunlar], repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), font, 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    ogeler += [t, Spacer(1, 12), Paragraph(b["beyan"], stil)]
    if u.enjeksiyon:
        # İstem enjeksiyonu: göze görünmez (beyaz, 1 punto) ama metin katmanında var.
        gizli = ParagraphStyle("gizli", fontName=font, fontSize=1, leading=1.2, textColor=colors.white)
        ogeler.append(Paragraph(u.enjeksiyon, gizli))
    ogeler += [Spacer(1, 18), Paragraph(b["imza"], stil)]
    ogeler += [Spacer(1, 24), Paragraph("SENTETİK TEST BELGESİ - gerçek bir sertifika değildir.", stil)]
    SimpleDocTemplate(str(yol), pagesize=A4, title=s.sertifika_no, invariant=1).build(ogeler)


def seti_yaz(uretilen: list[UretilenSertifika], cikti: Path, font: str | None) -> None:
    """json/, pdf/ (font varsa), dogru_kararlar.json ve ozet.csv yazar."""
    (cikti / "json").mkdir(parents=True, exist_ok=True)
    if font:
        (cikti / "pdf").mkdir(exist_ok=True)
    for u in uretilen:
        (cikti / "json" / f"{u.sertifika.sertifika_no}.json").write_text(
            u.sertifika.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )
        if font:
            pdf_yaz(u, cikti / "pdf" / f"{u.sertifika.sertifika_no}.pdf", font)
    dogrular = [u.dogru.model_dump(mode="json") for u in uretilen]
    (cikti / "dogru_kararlar.json").write_text(json.dumps(dogrular, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with open(cikti / "ozet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sertifika_no", "sablon", "standart_atfi", "hata_turu", "aciklama", "dogru_belge_karari"])
        for u in uretilen:
            w.writerow(
                [u.sertifika.sertifika_no, u.sablon.kod, u.sertifika.standart_atfi, u.dogru.hata_turu or "temiz",
                 u.dogru.hata_aciklamasi or "", u.dogru.belge_karari]
            )


def main(argv: list[str] | None = None) -> int:
    ayr = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayr.add_argument("kabul_dokumani")
    ayr.add_argument("--cikti", default=str(KOK / "data" / "sentetik" / "sertifikalar" / "MIL-PRF-23377K"))
    ayr.add_argument("--tohum", type=int, default=23377)
    ayr.add_argument("--pdfsiz", action="store_true", help="PDF üretme (yalnız JSON)")
    args = ayr.parse_args(argv)

    cikti = Path(args.cikti)
    if re.search(r"(^|/)data/gold(/|$)", cikti.resolve().as_posix()):
        raise SystemExit("data/gold/ klasörüne yazılmaz")
    dokuman = KabulDokumani.model_validate_json(Path(args.kabul_dokumani).read_text(encoding="utf-8"))
    uretilen = uret(dokuman, tohum=args.tohum)
    enjekte = enjeksiyon_uret(dokuman)
    font = None if args.pdfsiz else _font()
    seti_yaz(uretilen, cikti, font)
    seti_yaz(enjekte, cikti / "istem_enjeksiyonu", font)
    print(f"{len(uretilen)} sertifika -> {cikti}; {len(enjekte)} istem enjeksiyonlu -> {cikti / 'istem_enjeksiyonu'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
