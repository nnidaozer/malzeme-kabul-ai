"""Streamlit ekranlarının arkasındaki işler (Streamlit'siz test edilir).

Ekran dosyası (`arayuz/uygulama.py`) yalnız bu fonksiyonları çağırır ve
sonuçlarını gösterir; iş kuralı ekranda değil burada ve alttaki katmanlardadır.

- M&P: `standart_yukle` (kural çıkarıcıyla taslak), `test_tablosu` /
  `tablodan_dokuman` (taslağı tabloda düzeltme), `taslak_duzelt`,
  `taslak_onayla`, `revizyon_izinli_mi`, `revizyon_raporu`.
- Giriş kalite: `parti_hazirla`, `sertifika_karari`, `karar_tablosu`.
- Depo: `depo_tablosu`.

Test kümesi kilidi: arayüz yalnız `data/bolunme.yaml` içinde geliştirme
kümesinde olan standartlardan taslak çıkarır (`standart_yukle`) ve revizyon
karşılaştırır (`revizyon_raporu`; iki revizyon da `revizyon_izinli_mi` ile
denetlenir); test kümesindeki ya da bölünmede olmayan standartları reddeder
(`standart_izinli_mi`, docs/mimari.md madde 7). Kilit dosya adını okur.
Kilidi yalnız proje sahibi açar.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

from malzeme_kabul.belge.adlandirma import belge_no_ve_revizyon
from malzeme_kabul.cikarim.kural_cikarici import cikar
from malzeme_kabul.hat.katalog_karari import KatalogKarari, malzeme_koduyla_kontrol
from malzeme_kabul.hat.raf_omru_raporu import raf_raporu
from malzeme_kabul.katalog.veritabani import DokumanSurumu, Katalog, KatalogHatasi, Parti, Taslak
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.revizyon.revizyon_karsilastirici import (
    guncelleme_onerileri,
    markdown_raporu,
    revizyonlari_karsilastir,
)
from malzeme_kabul.sozlesme.sema import KabulDokumani, Sinir
from malzeme_kabul.sozlesme.sertifika import Sertifika

# Veri kökü (data/bolunme.yaml, data/cikti): imajda paket site-packages'a kurulu
# olduğundan MALZEME_KABUL_KOK ile verilir (Dockerfile: /uygulama); yoksa depo kökü.
KOK = Path(os.environ["MALZEME_KABUL_KOK"]) if os.environ.get("MALZEME_KABUL_KOK") else Path(__file__).resolve().parents[3]
BOLUNME = KOK / "data" / "bolunme.yaml"
HAZIR_RAPORLAR = KOK / "data" / "cikti"


# --- test kümesi kilidi ------------------------------------------------------------


def _liste(metin: str, anahtar: str) -> list[str]:
    m = re.search(rf"^{anahtar}:\s*\n((?:[ \t]*(?:-.*|#.*)?\n)*)", metin + "\n", re.MULTILINE)
    if not m:
        return []
    return [s.strip()[1:].split("#")[0].strip() for s in m.group(1).splitlines() if s.strip().startswith("-")]


def standart_izinli_mi(etiket: str, bolunme_yolu: Path = BOLUNME) -> tuple[bool, str]:
    """Standart (ör. 'MIL-PRF-23377K') geliştirme kümesinde mi?"""
    if not bolunme_yolu.is_file():
        return False, f"bölünme dosyası yok ({bolunme_yolu}); test kümesi kilidi denetlenemedi"
    metin = bolunme_yolu.read_text(encoding="utf-8")
    acik = re.search(r"^test_kumesi_acik:\s*true\s*$", metin, re.MULTILINE) is not None
    if etiket in _liste(metin, "test") and not acik:
        return False, f"{etiket} test kümesinde; kilit açılana kadar çıkarıcı çalıştırılmaz"
    if etiket in _liste(metin, "gelistirme") or (acik and etiket in _liste(metin, "test")):
        return True, "geliştirme kümesinde"
    return False, f"{etiket} bölünmede yok (data/bolunme.yaml); önce bölünmeye eklenmeli"


# --- M&P: standart ve taslak ------------------------------------------------------------


def standart_yukle(katalog: Katalog, pdf_yolu: str | Path, kullanici: str, bolunme_yolu: Path = BOLUNME,
                   belge_no: str | None = None, revizyon: str | None = None) -> Taslak:
    """Standart PDF'inden kural çıkarıcıyla taslak üretir ve kaydeder."""
    if not (belge_no and revizyon):
        belge_no, revizyon = belge_no_ve_revizyon(Path(pdf_yolu).name)
    izin, neden = standart_izinli_mi(f"{belge_no}{revizyon}", bolunme_yolu)
    if not izin:
        raise KatalogHatasi(neden)
    return katalog.taslak_kaydet(cikar(pdf_yolu, belge_no, revizyon), kullanici)


TABLO_SUTUNLARI = ["id", "test_adi", "kabul", "omur_uzatma", "yeterlilik", "kriter_turu", "alt", "ust", "birim",
                   "orijinal_metin", "madde", "sayfa", "sonuc_kaynagi"]


def test_tablosu(dokuman: KabulDokumani) -> list[dict]:
    """Düzeltme tablosu: her test bir satır."""
    return [
        {
            "id": t.id, "test_adi": t.test_adi,
            "kabul": "kabul" in t.test_turleri, "omur_uzatma": "omur_uzatma" in t.test_turleri,
            "yeterlilik": "yeterlilik" in t.test_turleri,
            "kriter_turu": t.sinir.kriter_turu, "alt": t.sinir.alt, "ust": t.sinir.ust, "birim": t.sinir.birim,
            "orijinal_metin": t.sinir.orijinal_metin, "madde": t.kaynak.madde, "sayfa": t.kaynak.sayfa,
            "sonuc_kaynagi": t.sonuc_kaynagi,
        }
        for t in dokuman.testler
    ]


def _bos(x):
    if x is None:
        return None
    if isinstance(x, float) and x != x:  # NaN (pandas boş hücre)
        return None
    if isinstance(x, str) and not x.strip():
        return None
    return x


def tablodan_dokuman(dokuman: KabulDokumani, satirlar: list[dict]) -> KabulDokumani:
    """Düzeltilmiş tabloyu dokümana uygular. Satır eklenmez/silinmez; geçersizse ValueError."""
    testler = {t.id: t for t in dokuman.testler}
    if [s["id"] for s in satirlar] != list(testler):
        raise ValueError("tabloda test eklenemez, silinemez ya da kimliği değiştirilemez")
    yeni = []
    for s in satirlar:
        t = testler[s["id"]]
        turler = {tur for tur in ("kabul", "omur_uzatma", "yeterlilik") if bool(s.get(tur))}
        if not turler:
            raise ValueError(f"{t.id}: en az bir test türü seçilmeli")
        kriter = s.get("kriter_turu") or t.sinir.kriter_turu
        alt, ust, birim = _bos(s.get("alt")), _bos(s.get("ust")), _bos(s.get("birim"))
        sinir = Sinir.model_validate({
            **t.sinir.model_dump(exclude={"alt", "ust", "birim", "kriter_turu", "orijinal_metin", "yon"}),
            "kriter_turu": kriter,
            "alt": None if alt is None else float(alt), "ust": None if ust is None else float(ust),
            "birim": birim, "orijinal_metin": _bos(s.get("orijinal_metin")) or t.sinir.orijinal_metin,
            "yon": t.sinir.yon if t.sinir.yon == "belirsiz" else None,
        })
        sayfa = _bos(s.get("sayfa"))
        kaynak = t.kaynak.model_copy(update={"madde": _bos(s.get("madde")) or t.kaynak.madde,
                                             "sayfa": None if sayfa is None else int(sayfa)})
        yeni.append(t.model_copy(update={
            "test_adi": _bos(s.get("test_adi")) or t.test_adi, "test_turleri": turler, "sinir": sinir,
            "kaynak": kaynak, "sonuc_kaynagi": s.get("sonuc_kaynagi") or t.sonuc_kaynagi,
        }))
    # Bütün doğrulamalar (madde biçimi, birim, yön) yeniden çalışsın diye baştan doğrulanır.
    return KabulDokumani.model_validate(dokuman.model_copy(update={"testler": yeni}).model_dump())


def degisiklik_ozeti(eski: KabulDokumani, yeni: KabulDokumani) -> list[str]:
    """İki taslak arasındaki test düzeyindeki farklar, insan okuyacak biçimde."""
    eski_t = {t.id: t.model_dump(mode="json") for t in eski.testler}
    farklar = []
    for t in yeni.testler:
        y, e = t.model_dump(mode="json"), eski_t.get(t.id)
        if e is None:
            farklar.append(f"{t.id}: eklendi")
            continue
        for alan in sorted(set(y) | set(e)):
            if y.get(alan) != e.get(alan):
                farklar.append(f"{t.id}.{alan}: {json.dumps(e.get(alan), ensure_ascii=False)} → {json.dumps(y.get(alan), ensure_ascii=False)}")
    return farklar


def taslak_duzelt(katalog: Katalog, defter: DenetimKaydi, taslak_id: int, yeni: KabulDokumani, kullanici: str) -> list[str]:
    """Taslağı günceller ve farkları denetim kaydına `duzeltme` olarak yazar. Farkları döner.

    Defter katalogla aynı bağlantıyı paylaşmalıdır (yoksa KatalogHatasi, hiçbir şey yazılmaz).
    """
    if defter.baglanti is not katalog.baglanti:
        raise KatalogHatasi("denetim kaydı katalogla aynı bağlantıyı paylaşmalı (taslak ve kayıt tek işlem)")
    eski = katalog.taslak(taslak_id).dokuman
    farklar = degisiklik_ozeti(eski, yeni)
    if not farklar:
        return []
    std = yeni.standart
    with katalog.islem():  # taslak ve kaydı tek işlem
        katalog.taslak_guncelle(taslak_id, yeni)
        defter.ekle("duzeltme", kullanici, {"taslak": taslak_id, "farklar": farklar},
                    dokuman_surumu=f"{std.belge_no}{std.revizyon} taslak {taslak_id}")
    return farklar


def taslak_onayla(katalog: Katalog, defter: DenetimKaydi, taslak_id: int, kullanici: str, not_: str | None = None) -> DokumanSurumu:
    """Taslağı onaylı sürüm yapar ve onayı kaydeder; ikisi tek işlemdir.

    Defter katalogla aynı bağlantıyı paylaşmalıdır (yoksa KatalogHatasi, hiçbir şey yazılmaz).
    """
    if defter.baglanti is not katalog.baglanti:
        raise KatalogHatasi("denetim kaydı katalogla aynı bağlantıyı paylaşmalı (taslak ve kayıt tek işlem)")
    with katalog.islem():
        surum = katalog.taslagi_onayla(taslak_id, kullanici, not_)
        defter.ekle("onay", kullanici, {"taslak": taslak_id, "dokuman_surumu": surum.etiket, "ozet": surum.ozet, "not": not_},
                    dokuman_surumu=surum.etiket)
    return surum


def revizyon_izinli_mi(eski_ad: str | Path, yeni_ad: str | Path, bolunme_yolu: Path = BOLUNME) -> tuple[bool, str]:
    """İki revizyonun ikisi de test kümesi kilidinden geçiyor mu? İlk reddi döner."""
    for ad in (eski_ad, yeni_ad):
        no, rev = belge_no_ve_revizyon(Path(ad).name)
        izin, neden = standart_izinli_mi(f"{no}{rev}", bolunme_yolu)
        if not izin:
            return False, neden
    return True, ""


def revizyon_raporu(eski_pdf: str | Path, yeni_pdf: str | Path, dokuman: KabulDokumani | None = None,
                    bolunme_yolu: Path = BOLUNME) -> tuple[str, dict]:
    """İki revizyon PDF'ini karşılaştırır; Markdown rapor ve özet döner.

    Önce iki dosyanın aynı standart olduğu (ValueError), sonra iki revizyonun da
    test kümesi kilidinden geçtiği (KatalogHatasi) denetlenir; karşılaştırma
    ancak ondan sonra yapılır.
    """
    eski_no, eski_rev = belge_no_ve_revizyon(Path(eski_pdf).name)
    yeni_no, yeni_rev = belge_no_ve_revizyon(Path(yeni_pdf).name)
    if eski_no != yeni_no:
        raise ValueError(f"iki dosya aynı standardın revizyonu olmalı: {eski_no} / {yeni_no}")
    izin, neden = revizyon_izinli_mi(eski_pdf, yeni_pdf, bolunme_yolu)
    if not izin:
        raise KatalogHatasi(neden)
    fark = revizyonlari_karsilastir(eski_pdf, yeni_pdf, eski_no, eski_rev, yeni_rev)
    oneriler = guncelleme_onerileri(fark, dokuman) if dokuman is not None else None
    return markdown_raporu(fark, oneriler), fark.ozet()


def hazir_revizyon_raporlari(klasor: Path = HAZIR_RAPORLAR) -> dict[str, Path]:
    """Önceden üretilmiş revizyon farkı raporları (ad → .md yolu)."""
    return {p.stem.replace("_revizyon_farklari", ""): p for p in sorted(klasor.glob("*_revizyon_farklari.md"))}


# --- giriş kalite -----------------------------------------------------------------------


def parti_hazirla(katalog: Katalog, malzeme_kodu: str, lot_no: str, tedarikci: str, siparis_revizyonu: str,
                  uretim_tarihi: date | str, kap_turu: str | None = None) -> Parti:
    """Lot katalogda yoksa 'bekliyor' durumuyla ekler; varsa olduğu gibi döner."""
    try:
        return katalog.parti(malzeme_kodu, lot_no)
    except KatalogHatasi:
        return katalog.parti_ekle(lot_no, malzeme_kodu, tedarikci, siparis_revizyonu, uretim_tarihi, kap_turu=kap_turu)


def json_sertifika_karari(katalog: Katalog, defter: DenetimKaydi, malzeme_kodu: str, json_metni: str,
                          kullanici: str, lot_no: str | None = None) -> KatalogKarari:
    """Ham hücreli JSON sertifikayla karar (PDF'siz)."""
    sertifika = Sertifika.model_validate_json(json_metni)
    return malzeme_koduyla_kontrol(katalog, malzeme_kodu, sertifika, lot_no=lot_no, defter=defter, kullanici=kullanici,
                                   hat_bilgisi={"mod": "json"})


ETIKETLER = {"uygun": "✅ uygun", "uygun_degil": "❌ uygun değil", "insan_incelemeli": "⚠️ insan incelemeli"}
PARTI_ETIKETI = {"kabul": "✅ KABUL (serbest)", "red": "❌ RED (karantina)", "inceleme": "⚠️ İNCELEME (bekliyor)"}


def karar_tablosu(karar: KatalogKarari) -> list[dict]:
    k = karar.kontrol
    satirlar = [k.revizyon] + ([k.tip_sinif] if k.tip_sinif else []) + karar.ek_denetimler + k.satirlar
    return [
        {"karar": ETIKETLER[s.karar], "test": s.test_adi, "madde": s.madde or "", "sayfa": s.sayfa,
         "sertifikadaki_ad": s.sertifikadaki_ad or "", "okunan": s.okunan_sonuc or "", "gerekce": s.gerekce}
        for s in satirlar
    ]


# --- depo -----------------------------------------------------------------------------------

RAF_ETIKETI = {"gecerli": "geçerli", "yaklasiyor": "⚠️ yaklaşıyor", "doldu": "❌ doldu", "bilinmiyor": "bilinmiyor"}


def depo_tablosu(katalog: Katalog, bugun: date | None = None, uyari_esigi_gun: int = 30) -> list[dict]:
    return [
        {
            "malzeme": s.parti.malzeme_kodu, "lot": s.parti.lot_no, "tedarikçi": s.parti.tedarikci,
            "durum": s.parti.durum, "M&P": s.parti.mp_inceleme or "",
            "üretim": s.parti.uretim_tarihi.isoformat(),
            "son kullanma": s.raf.son_kullanma.isoformat() if s.raf.son_kullanma else "",
            "kalan gün": s.raf.kalan_gun, "raf": RAF_ETIKETI[s.raf.durum],
            "ömür uzatma testleri": ", ".join(t.test_adi for t in s.omur_uzatma_testleri)
            or ("tanımlı değil" if s.raf.uyari else ""),
            "not": "; ".join(s.raf.notlar),
        }
        for s in raf_raporu(katalog, bugun, uyari_esigi_gun)
    ]


__all__ = [
    "ETIKETLER",
    "PARTI_ETIKETI",
    "TABLO_SUTUNLARI",
    "degisiklik_ozeti",
    "depo_tablosu",
    "hazir_revizyon_raporlari",
    "json_sertifika_karari",
    "karar_tablosu",
    "parti_hazirla",
    "revizyon_izinli_mi",
    "revizyon_raporu",
    "standart_izinli_mi",
    "standart_yukle",
    "tablodan_dokuman",
    "taslak_duzelt",
    "taslak_onayla",
    "test_tablosu",
]
