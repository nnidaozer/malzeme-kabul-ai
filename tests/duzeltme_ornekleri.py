"""Düzeltme döngüsü testlerinin ortak küçük örnekleri (data/gold/ kullanılmaz)."""

from __future__ import annotations

from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, RafOmru, Sinir, StandartBilgisi
from malzeme_kabul.sozlesme.sema import TestSarti as Sart

BELGE = "MIL-PRF-23377K"


def kaynak(madde: str, sayfa: int | None = 5) -> Kaynak:
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde, sayfa=sayfa)


def sart(id: str, alt: float | None = 20.0, ust: float | None = 30.0, birim: str | None = "s",
         madde: str = "3.6.2", sayfa: int | None = 5, ad: str | None = None, metot: str | None = "ASTM D 1200") -> Sart:
    return Sart(
        id=id,
        test_adi=ad or id.title(),
        test_metodu=metot,
        sinir=Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin="20 to 30 s"),
        kaynak=kaynak(madde, sayfa),
        test_turleri={"kabul"},
    )


def dok(testler, raf=()) -> KabulDokumani:
    return KabulDokumani(
        standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"),
        testler=list(testler),
        raf_omurleri=list(raf),
    )


def raf(sure: float = 12, birim: str = "month") -> RafOmru:
    return RafOmru(sure=sure, birim=birim, kaynak=kaynak("3.11", 9))


def taban() -> KabulDokumani:
    """İki testli küçük taban: viskozite (3.6.2 s.5) ve kap_omru (3.6.4 s.7)."""
    return dok([sart("viskozite"), sart("kap_omru", alt=None, ust=70.0, madde="3.6.4", sayfa=7)])


def viskozite_ust(ust: float, kap_omru_ust: float = 70.0) -> KabulDokumani:
    """Tabanın viskozite üst sınırı (ve istenirse kap ömrü üst sınırı) değişmiş hâli."""
    return dok([sart("viskozite", ust=ust), sart("kap_omru", alt=None, ust=kap_omru_ust, madde="3.6.4", sayfa=7)])


def kirilim_satiri(kirilim, ad: str) -> dict:
    """Pano kırılımı list[dict] ya da dict olabilir; `ad` adlı satırı döner."""
    if isinstance(kirilim, dict):
        return kirilim[ad]
    satir = next((s for s in kirilim if ad in s.values()), None)
    assert satir is not None, f"kırılımda {ad!r} satırı yok: {kirilim}"
    return satir


# Tablodan düzenlenen ama F1 düzleştirmesinde olmayan test alanları (koordinatör kararı: paydaya girer).
EK_TEST_ALANLARI = {
    "test.kaynak.sayfa": lambda t: t.kaynak.sayfa,
    "test.sinir.orijinal_metin": lambda t: t.sinir.orijinal_metin,
    "test.sonuc_kaynagi": lambda t: t.sonuc_kaynagi,
}


def alan_anahtarlari(dokuman: KabulDokumani) -> set[tuple[str, str]]:
    """Düzeltme panosunun saydığı alanlar: F1 alanları + dolu (None olmayan) ek alanlar.

    Modülden bağımsız hesaplanır; `duzeltme_alanlari` beklentisinin ölçütüdür.
    """
    from malzeme_kabul.sozlesme.alanlar import alanlari_duzlestir

    anahtarlar = set(alanlari_duzlestir(dokuman))
    for t in dokuman.testler:
        for alan, oku in EK_TEST_ALANLARI.items():
            if oku(t) is not None:
                anahtarlar.add((alan, t.id))
    return anahtarlar


def alan_sayisi(dokuman: KabulDokumani) -> int:
    return len(alan_anahtarlari(dokuman))
