"""Güven skoru testleri için elle kurulan küçük örnekler.

Gerçek Colab sonucu kullanılmaz; kabul dokümanları ve üç mod raporları burada
elle kurulur ya da tmp_path altına yazılır. Gerçek depodaki data/gold/'a hiçbir
şey yazılmaz.
"""

from __future__ import annotations

import json
from pathlib import Path

from deney.bolunme import Bolunme, bolunme_oku
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi
from malzeme_kabul.sozlesme.sema import TestSarti as Sart

BELGE_NO, REV = "MIL-PRF-23377", "K"
TARANMIS = "MIL-PRF-55555A"  # bölünmede ocr_gerekli (taranmış) sayılan geliştirme belgesi
GELISTIRME = ("MIL-PRF-23377G", "MIL-PRF-23377K", "MIL-PRF-81733D", TARANMIS)
YENI = ("MIL-PRF-1A", "MIL-PRF-2B")


def sayisal(alt=None, ust=None, birim=None, metin="kriter metni", **kw) -> Sinir:
    return Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin=metin, **kw)


def metinsel(metin="The odor shall not be objectionable.") -> Sinir:
    return Sinir(kriter_turu="metinsel", orijinal_metin=metin)


def sart(id, ad, sinir, madde, sayfa=None, belge_no=BELGE_NO, rev=REV, metot=None) -> Sart:
    return Sart(
        id=id, test_adi=ad, test_metodu=metot, sinir=sinir,
        kaynak=Kaynak(belge_no=belge_no, revizyon=rev, madde=madde, sayfa=sayfa),
        test_turleri={"kabul"},
    )


def dok(testler=(), belge_no=BELGE_NO, rev=REV) -> KabulDokumani:
    return KabulDokumani(standart=StandartBilgisi(belge_no=belge_no, revizyon=rev), testler=list(testler))


def anlasmazlik(test_id, alan, model_id=None, madde="3.6.3") -> dict:
    return {"test_id": test_id, "model_id": model_id or test_id, "alan": alan, "kural": "40",
            "model": "60", "kural_madde": madde, "model_madde": madde}


def rapor(eklenen=(), kanitsiz=(), anlasmazliklar=(), yon_celiskileri=(), sayfalar=()) -> dict:
    """uc_mod rapor sözlüğünün güven skoru için gereken kısmı.

    kanitsiz: dil modeli kimlikleri; yon_celiskileri: dil modeli kimlikleri;
    sayfalar: {sayfa_no: hata_sayisi}.
    """
    return {
        "model": "sahte-model",
        "hibrit_raporu": {
            "eklenen": list(eklenen),
            "kuralla_eslesen": [],
            "kanitsiz": [[i, "özgün metin sayfada yok"] for i in kanitsiz],
            "sayi_atildi": [],
            "anlasmazliklar": [dict(a) for a in anlasmazliklar],
            "anlasmazlik_sayisi": len(anlasmazliklar),
            "anlasmazlikli_test_sayisi": len({a["test_id"] for a in anlasmazliklar}),
            "isaretlenemeyen": [],
        },
        "dil_modeli_raporu": {
            "sayfalar": [
                {"sayfa": no, "sure_s": 1.0, "test_sayisi": 1, "hatalar": [f"hata {k}" for k in range(n)]}
                for no, n in sayfalar.items()
            ] if isinstance(sayfalar, dict) else list(sayfalar),
            "tekrar_edenler": [],
            "yon_celiskileri": [
                {"id": i, "sayfa": 1, "metin_yonu": "en_cok", "model_yonu": "en_az", "orijinal_metin": "x"}
                for i in yon_celiskileri
            ],
            "toplam_sure_s": 1.0,
            "test_sayisi": 0,
            "devam_edilen_sayfalar": [],
        },
    }


def bolunme_dosyasi(klasor: Path) -> tuple[Path, str]:
    """Geliştirme: GELISTIRME + seçilmeyen yeni; test: tohumla seçilen; ocr_gerekli: TARANMIS.

    (yol, test kümesindeki etiket) döner.
    """
    b = Bolunme(gelistirme=list(GELISTIRME), yeni_standartlar=list(YENI), tohum=7).secimi_yap()

    def liste(ad, ogeler):
        return [f"{ad}:"] + [f"  - {x}" for x in ogeler]

    satirlar = ["test_kumesi_acik: false", "test_durumu: secildi", f"tohum: {b.tohum}",
                *liste("gelistirme", b.gelistirme), *liste("yeni_standartlar", b.yeni_standartlar),
                *liste("test", b.test), *liste("ocr_gerekli", [TARANMIS])]
    yol = Path(klasor) / "bolunme.yaml"
    yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    okunan = bolunme_oku(yol)
    assert okunan.kume(b.test[0]) == "test"
    assert okunan.belge_turu(TARANMIS) != okunan.belge_turu("MIL-PRF-23377K")
    return yol, b.test[0]


def uc_mod_yaz(klasor: Path, etiket: str, kural: KabulDokumani, dil: KabulDokumani, hibrit: KabulDokumani,
               rapor_sozlugu: dict) -> None:
    """uc_mod.py çıktı düzeni: ETIKET_kural.json, ETIKET_dil_modeli.json, ETIKET_hibrit.json, ETIKET_uc_mod_rapor.json."""
    klasor = Path(klasor)
    klasor.mkdir(parents=True, exist_ok=True)
    for mod, d in (("kural", kural), ("dil_modeli", dil), ("hibrit", hibrit)):
        (klasor / f"{etiket}_{mod}.json").write_text(d.model_dump_json(indent=2), encoding="utf-8")
    veri = dict(rapor_sozlugu, belge=etiket)
    (klasor / f"{etiket}_uc_mod_rapor.json").write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")


def gold_yaz(kok: Path, alt_klasor: str, etiket: str, gold: KabulDokumani) -> Path:
    """kok/data/<alt_klasor>/ETIKET.json (kok her zaman tmp_path; gerçek depo değil)."""
    yol = Path(kok) / "data" / alt_klasor / f"{etiket}.json"
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(gold.model_dump_json(indent=2), encoding="utf-8")
    return yol


def belge_ornegi(belge_no: str, rev: str, hatali_ust: bool = True):
    """Üç testli bir belge: (kural, dil, hibrit, rapor, gold).

    - viscosity: anlaşmazlıklı; gold ile ust farklı (hatali_ust True ise) -> hatalı
    - lead_content: anlaşmazlıksız, kanıtlı eşleşme; gold ile aynı -> doğru
    - flash_point: yalnız modelden eklenen; gold'da yok -> hatalı
    """
    def s(id, ad, sinir, madde, sayfa):
        return sart(id, ad, sinir, madde, sayfa, belge_no=belge_no, rev=rev)

    kural = dok([
        s("viscosity", "Viscosity", sayisal(ust=40, birim="s"), "3.6.3", 1),
        s("lead_content", "Lead content", sayisal(ust=1, birim="ppm"), "3.6.9", 2),
    ], belge_no, rev)
    dil = dok([
        s("viscosity", "Viscosity", sayisal(ust=60, birim="s"), "3.6.3", 1),
        s("lead_content", "Lead content", sayisal(ust=1, birim="ppm"), "3.6.9", 2),
        s("flash_point", "Flash point", sayisal(alt=20, birim="°C"), "3.6.14", 3),
    ], belge_no, rev)
    hibrit = dok([
        s("viscosity", "Viscosity", sayisal(ust=40, birim="s", yon="belirsiz"), "3.6.3", 1),
        s("lead_content", "Lead content", sayisal(ust=1, birim="ppm"), "3.6.9", 2),
        s("flash_point", "Flash point", sayisal(alt=20, birim="°C"), "3.6.14", 3),
    ], belge_no, rev)
    r = rapor(eklenen=["flash_point"], anlasmazliklar=[anlasmazlik("viscosity", "ust")], sayfalar={1: 0, 2: 0, 3: 1})
    gold = dok([
        s("viscosity", "Viscosity", sayisal(ust=50 if hatali_ust else 40, birim="s"), "3.6.3", 1),
        s("lead_content", "Lead content", sayisal(ust=1, birim="ppm"), "3.6.9", 2),
    ], belge_no, rev)
    return kural, dil, hibrit, r, gold


def klasor_snapshot(klasor: Path) -> dict[str, tuple[int, bytes]]:
    """Klasördeki her dosyanın (mtime_ns, içerik) özeti; yoksa boş sözlük."""
    klasor = Path(klasor)
    if not klasor.exists():
        return {}
    return {str(p.relative_to(klasor)): (p.stat().st_mtime_ns, p.read_bytes())
            for p in sorted(klasor.rglob("*")) if p.is_file()}
