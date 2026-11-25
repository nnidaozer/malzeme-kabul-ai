"""Kabul dokümanını (KabulDokumani) Markdown ve Word taslağına çevirir.

Her şartın yanında dayandığı standart maddesi yazılır. İki çıktı aynı ara
yapıdan (bölüm listesi) üretilir, böylece içerikleri birbirinden ayrılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from malzeme_kabul.sozlesme.sema import KabulDokumani, Kosul, Sinir, TestSarti

TASLAK_NOTU = (
    "TASLAK: Bu doküman standarttan otomatik çıkarılmıştır. "
    "Kullanılmadan önce kalite mühendisi tarafından kontrol edilip onaylanmalıdır."
)
TEST_SUTUNLARI = ["Test", "Test metodu", "Sınır", "Uygulanabilirlik", "Sonuç kaynağı", "Madde"]
SONUC_KAYNAKLARI = {"coc": "CoC", "ic_laboratuvar": "İç laboratuvar", "ic_muayene": "İç muayene"}
YON_BELIRSIZ_NOTU = "yön belirsiz, insan incelemeli"
TEST_BOLUMLERI = [
    ("kabul", "Kabul testleri"),
    ("omur_uzatma", "Ömür uzatma testleri"),
    ("yeterlilik", "Yeterlilik testleri"),
    ("muayene", "İç muayene şartları"),
]


def _sayi(x: float) -> str:
    return f"{x:g}"


def sinir_metni(sinir: Sinir) -> str:
    """Kriteri okunur metne çevirir: '20 – 30 s', '≥ 4 hour', '≤ 340 g/L'."""
    if sinir.kriter_turu == "metinsel":
        return sinir.orijinal_metin
    if sinir.kriter_turu == "gecti_kaldi":
        return f"Geçti/kaldı: {sinir.orijinal_metin}"
    alt, ust = sinir.alt, sinir.ust
    if sinir.yon_belirsiz:
        deger = " / ".join(dict.fromkeys(_sayi(x) for x in (alt, ust) if x is not None))
        deger = f"{deger} {sinir.birim}" if sinir.birim else deger
        return f"{deger} ({YON_BELIRSIZ_NOTU})"
    if alt is not None and ust is not None:
        govde = f"= {_sayi(alt)}" if alt == ust else f"{_sayi(alt)} – {_sayi(ust)}"
    elif alt is not None:
        govde = f"{'≥' if sinir.alt_dahil else '>'} {_sayi(alt)}"
    else:
        govde = f"{'≤' if sinir.ust_dahil else '<'} {_sayi(ust)}"
    return f"{govde} {sinir.birim}" if sinir.birim else govde


@dataclass
class Bolum:
    baslik: str
    sutunlar: list[str]
    satirlar: list[list[str]]


def _test_satiri(t: TestSarti) -> list[str]:
    ad = f"{t.test_adi} (tabloda: {t.kaynak_tablo_adi})" if t.kaynak_tablo_adi else t.test_adi
    return [
        ad,
        t.test_metodu or "—",
        sinir_metni(t.sinir),
        ", ".join(t.uygulanabilirlik) or "Tümü",
        SONUC_KAYNAKLARI[t.sonuc_kaynagi],
        t.kaynak.etiket,
    ]


def _kosul_satiri(k: Kosul) -> list[str]:
    deger = sinir_metni(k.sinir) if k.sinir else ""
    if k.aciklama:
        deger = f"{deger} ({k.aciklama})" if deger else k.aciklama
    return [k.ad, deger, k.kaynak.etiket]


def bolumler(dok: KabulDokumani) -> list[Bolum]:
    """Dokümanın bölümlerini sırayla döner; boş bölümler atlanır."""
    sonuc: list[Bolum] = []
    if dok.urun_tanimi:
        satirlar = [
            [tur, k.kod, k.aciklama or "—", k.kaynak.etiket]
            for tur, kayitlar in (
                ("Tip", dok.urun_tanimi.tipler),
                ("Sınıf", dok.urun_tanimi.siniflar),
                ("Kompozisyon", dok.urun_tanimi.kompozisyonlar),
            )
            for k in kayitlar
        ]
        if satirlar:
            sonuc.append(Bolum("Ürün tanımı", ["Tür", "Kod", "Açıklama", "Madde"], satirlar))
    for tur, baslik in TEST_BOLUMLERI:
        testler = [t for t in dok.testler if tur in t.test_turleri]
        if testler:
            sonuc.append(Bolum(baslik, TEST_SUTUNLARI, [_test_satiri(t) for t in testler]))

    if dok.raf_omurleri:
        satirlar = []
        for r in dok.raf_omurleri:
            sure = f"{_sayi(r.sure)} {r.birim}" + (f" ({r.baslangic})" if r.baslangic else "")
            if r.kosul:
                sure += f", {sinir_metni(r.kosul)}"
            satirlar.append([r.kap_turu or "Tümü", sure, r.kaynak.etiket])
        sonuc.append(Bolum("Raf ömrü", ["Kap türü", "Şart", "Madde"], satirlar))

    for kategori, baslik in (("depolama", "Depolama koşulları"), ("kullanim", "Kullanım koşulları")):
        kosullar = [k for k in dok.kosullar if k.kategori == kategori]
        if kosullar:
            sonuc.append(Bolum(baslik, ["Koşul", "Şart", "Madde"], [_kosul_satiri(k) for k in kosullar]))

    if dok.numune_hazirlama:
        satirlar = []
        for n in dok.numune_hazirlama:
            kft = sinir_metni(n.kuru_film_kalinligi) if n.kuru_film_kalinligi else ""
            alanlar = [n.kupon_malzemesi, n.kupon_boyutu, n.yuzey_hazirligi, n.uygulama_yontemi, kft, n.kurlenme]
            satirlar.append([n.id] + [a or "—" for a in alanlar] + [n.kaynak.etiket])
        sonuc.append(Bolum(
            "Kupon, uygulama ve kürlenme",
            ["Numune", "Kupon", "Boyut", "Yüzey hazırlığı", "Uygulama", "Kuru film kalınlığı", "Kürlenme", "Madde"],
            satirlar,
        ))
    return sonuc


def _baslik(dok: KabulDokumani) -> str:
    return f"Kabul Dokümanı: {dok.standart.belge_no}{dok.standart.revizyon}"


def _alt_bilgi(dok: KabulDokumani) -> list[str]:
    satirlar = []
    if dok.standart.baslik:
        satirlar.append(f"Standart: {dok.standart.baslik}")
    if dok.standart.tarih:
        satirlar.append(f"Revizyon tarihi: {dok.standart.tarih}")
    satirlar.append(f"Durum: {dok.durum}")
    return satirlar


def _md_hucre(metin: str) -> str:
    return metin.replace("|", "\\|").replace("\n", " ")


def markdown_uret(dok: KabulDokumani) -> str:
    """Kabul dokümanını Markdown metni olarak döner."""
    parcalar = [f"# {_baslik(dok)}", ""]
    parcalar += [f"{s}  " for s in _alt_bilgi(dok)]
    if dok.durum == "taslak":
        parcalar += ["", f"> **{TASLAK_NOTU}**"]
    for b in bolumler(dok):
        parcalar += ["", f"## {b.baslik}", ""]
        parcalar.append("| " + " | ".join(b.sutunlar) + " |")
        parcalar.append("|" + "---|" * len(b.sutunlar))
        parcalar += ["| " + " | ".join(_md_hucre(h) for h in s) + " |" for s in b.satirlar]
    return "\n".join(parcalar) + "\n"


def word_uret(dok: KabulDokumani, yol: str | Path) -> Path:
    """Kabul dokümanını .docx olarak yazar ve yolu döner."""
    from docx import Document  # python-docx; yalnızca Word çıktısında gerekir

    yol = Path(yol)
    belge = Document()
    belge.add_heading(_baslik(dok), level=0)
    for s in _alt_bilgi(dok):
        belge.add_paragraph(s)
    if dok.durum == "taslak":
        belge.add_paragraph().add_run(TASLAK_NOTU).bold = True
    for b in bolumler(dok):
        belge.add_heading(b.baslik, level=1)
        tablo = belge.add_table(rows=1, cols=len(b.sutunlar))
        tablo.style = "Table Grid"
        for hucre, ad in zip(tablo.rows[0].cells, b.sutunlar):
            hucre.text = ad
            for run in hucre.paragraphs[0].runs:
                run.bold = True
        for satir in b.satirlar:
            for hucre, deger in zip(tablo.add_row().cells, satir):
                hucre.text = deger
    belge.save(str(yol))
    return yol
