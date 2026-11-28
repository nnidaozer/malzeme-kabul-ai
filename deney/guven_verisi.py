"""Güven skoru verisi: üç mod çıktısından girdi ve etiket (docs/guven_skoru.md).

Girdi klasörü deney/uc_mod.py çıktı düzenindedir (ETIKET = belge no + revizyon):
  ETIKET_kural.json, ETIKET_dil_modeli.json, ETIKET_hibrit.json, ETIKET_uc_mod_rapor.json

Her hibrit test şartı için bir `GuvenOrnegi` üretilir: girdiler rapordan
(`girdileri_cikar`), etiket gold ile hizalamadan (`etiketle`). Gold yalnız okunur;
sıra data/gold, data/gold_taslak, data/gold_codex (ilk bulunan). Gold'u olmayan
belge atlanır. Test kümesindeki belge `TestKumesiKilitli`, taranmış belge
`OcrGerekli` yükseltir.

Kullanım (kütüphane olarak; eğitim betiği deney/guven_egitimi.py):
  from deney.guven_verisi import klasorden_oku
  ornekler, atlanan = klasorden_oku("deney/sonuclar/colab_uc_mod")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deney.bolunme import VARSAYILAN_YOL, bolunme_oku
from deney.degerlendirme import _Birim, degerler_esit
from deney.taslak_karsilastirma import kaydi_eslestir
from malzeme_kabul.kural.guven_skoru import GuvenGirdileri
from malzeme_kabul.sozlesme.sema import KabulDokumani, Sinir, TestSarti

KOK = Path(__file__).resolve().parents[1]
GOLD_SIRASI = ("gold", "gold_taslak", "gold_codex")
RAPOR_EKI = "_uc_mod_rapor.json"


@dataclass(frozen=True)
class GuvenOrnegi:
    belge: str
    test_id: str
    girdiler: GuvenGirdileri
    hatali: bool
    zorunlu_inceleme: bool


def _madde(madde: str) -> str:
    return " ".join(madde.split()).casefold()


def _test_eslesmeleri(a: KabulDokumani, b: KabulDokumani) -> dict[str, str]:
    """a test kimliği -> b test kimliği."""
    return {e.a: e.b for e in kaydi_eslestir(a, b) if e.tur == "test"}


def girdileri_cikar(
    kural: KabulDokumani, dil: KabulDokumani, hibrit: KabulDokumani, rapor: dict[str, Any]
) -> dict[str, GuvenGirdileri]:
    """Hibritin her test kimliği için güven girdileri (docs/guven_skoru.md, Girdiler)."""
    h_rapor = rapor.get("hibrit_raporu", {})
    d_rapor = rapor.get("dil_modeli_raporu", {})
    eklenen = set(h_rapor.get("eklenen", []))
    kanitsiz = {k[0] for k in h_rapor.get("kanitsiz", [])}
    anlasmazliklar = h_rapor.get("anlasmazliklar", [])
    yon_celiskili = {k["id"] for k in d_rapor.get("yon_celiskileri", [])}
    sema_hatalari: dict[int, int] = {}
    for s in d_rapor.get("sayfalar", []):
        sema_hatalari[s["sayfa"]] = sema_hatalari.get(s["sayfa"], 0) + len(s.get("hatalar", []))

    dil_testleri = {t.id: t for t in dil.testler}
    kanitsiz_sayfa: dict[int, int] = {}
    for id_ in kanitsiz:
        t = dil_testleri.get(id_)
        if t is not None and t.kaynak.sayfa is not None:
            kanitsiz_sayfa[t.kaynak.sayfa] = kanitsiz_sayfa.get(t.kaynak.sayfa, 0) + 1

    kural_testleri = {t.id: t for t in kural.testler}
    eslesen = _test_eslesmeleri(kural, dil)

    sonuc: dict[str, GuvenGirdileri] = {}
    for t in hibrit.testler:
        kayitlar = [a for a in anlasmazliklar if a.get("test_id") == t.id]
        yon = any(a.get("alan") == "yon" for a in kayitlar)
        yalniz_model = t.id in eklenen
        kanit_yok = False
        if yalniz_model:
            # Hibrit, kural kimliğiyle çakışan model kimliğine "_dm" ekler; özgün kimlik aranır.
            ozgun = t.id
            while ozgun.endswith("_dm") and ozgun not in dil_testleri:
                ozgun = ozgun[: -len("_dm")]
            yon = yon or ozgun in yon_celiskili
        else:
            dil_id = eslesen.get(t.id)
            kural_testi = kural_testleri.get(t.id, t)
            if dil_id is None or dil_id in kanitsiz:
                kanit_yok = True
            elif _madde(dil_testleri[dil_id].kaynak.madde) != _madde(kural_testi.kaynak.madde):
                kanit_yok = True
            if dil_id is not None:
                yon = yon or dil_id in yon_celiskili
        sayfa = t.kaynak.sayfa
        sonuc[t.id] = GuvenGirdileri(
            anlasmazlik_sayisi=len(kayitlar),
            kanit_yok=kanit_yok,
            yalniz_model=yalniz_model,
            sayfa_kanitsiz_sayisi=kanitsiz_sayfa.get(sayfa, 0) if sayfa is not None else 0,
            yon_celiskisi=yon,
            sayfa_sema_hatasi=sema_hatalari.get(sayfa, 0) if sayfa is not None else 0,
        )
    return sonuc


def _sayi_esit(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return degerler_esit(a, b)


def _sinir_ayni(h: Sinir, g: Sinir) -> bool:
    """Sınır alanları (kriter türü, alt, üst, dahil bilgileri, birim) aynı mı? Yön bakılmaz."""
    if h.kriter_turu != g.kriter_turu:
        return False
    if not (_sayi_esit(h.alt, g.alt) and _sayi_esit(h.ust, g.ust)):
        return False
    if (h.alt is not None or g.alt is not None) and h.alt_dahil != g.alt_dahil:
        return False
    if (h.ust is not None or g.ust is not None) and h.ust_dahil != g.ust_dahil:
        return False
    if h.birim is None or g.birim is None:
        return h.birim is None and g.birim is None
    return degerler_esit(_Birim(h.birim), _Birim(g.birim))


def etiketle(hibrit: KabulDokumani, gold: KabulDokumani) -> dict[str, bool]:
    """Hibrit test kimliği -> hatalı mı (gold'da karşılığı yok ya da sınır alanı farklı)."""
    eslesen = _test_eslesmeleri(hibrit, gold)
    gold_testleri = {t.id: t for t in gold.testler}
    sonuc = {}
    for t in hibrit.testler:
        g = gold_testleri.get(eslesen.get(t.id, ""))
        sonuc[t.id] = g is None or not _sinir_ayni(t.sinir, g.sinir)
    return sonuc


def zorunlu_inceleme(test: TestSarti) -> bool:
    """Yönü "belirsiz" sayısal sınır kurallar gereği insan incelemesine gider."""
    return test.sinir.kriter_turu == "sayisal" and test.sinir.yon == "belirsiz"


def _gold_bul(kok: Path, etiket: str) -> Path | None:
    for ad in GOLD_SIRASI:
        yol = kok / "data" / ad / f"{etiket}.json"
        if yol.is_file():
            return yol
    return None


def _dokuman(yol: Path) -> KabulDokumani:
    return KabulDokumani.model_validate_json(yol.read_text(encoding="utf-8"))


def klasorden_oku(
    klasor: str | Path, bolunme: str | Path = VARSAYILAN_YOL, kok: str | Path = KOK
) -> tuple[list[GuvenOrnegi], list[str]]:
    """Üç mod klasöründen (örnekler, gold'u olmadığı için atlanan belgeler).

    Önce bütün belgeler bölünmeye karşı denetlenir: test kümesindeki belge
    `TestKumesiKilitli`, taranmış belge (OCR gelene kadar) `OcrGerekli`,
    bölünmede olmayan belge ValueError yükseltir.
    """
    klasor, kok = Path(klasor), Path(kok)
    if not klasor.is_dir():
        return [], []
    etiketler = sorted(p.name[: -len(RAPOR_EKI)] for p in klasor.glob(f"*{RAPOR_EKI}"))
    b = bolunme_oku(bolunme)
    for etiket in etiketler:
        b.kullanima_izin_ver(etiket)

    ornekler: list[GuvenOrnegi] = []
    atlanan: list[str] = []
    for etiket in etiketler:
        gold_yolu = _gold_bul(kok, etiket)
        if gold_yolu is None:
            atlanan.append(etiket)
            continue
        kural = _dokuman(klasor / f"{etiket}_kural.json")
        dil = _dokuman(klasor / f"{etiket}_dil_modeli.json")
        hibrit = _dokuman(klasor / f"{etiket}_hibrit.json")
        rapor = json.loads((klasor / f"{etiket}{RAPOR_EKI}").read_text(encoding="utf-8"))
        gold = _dokuman(gold_yolu)
        girdiler = girdileri_cikar(kural, dil, hibrit, rapor)
        hatalar = etiketle(hibrit, gold)
        ornekler += [
            GuvenOrnegi(belge=etiket, test_id=t.id, girdiler=girdiler[t.id], hatali=hatalar[t.id],
                        zorunlu_inceleme=zorunlu_inceleme(t))
            for t in hibrit.testler
        ]
    return ornekler, atlanan
