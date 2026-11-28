"""Sınır karşılaştırmasında yuvarlama yok; sınıra çok yakın değerler insana gider.

Proje sahibinin kuralı (Codex incelemesi, yanlış kabul riski): "Karşılaştırma
standarttaki ve sertifikadaki değerler yuvarlanmadan yapılsın; sınıra çok yakın
değerler insan incelemesine gitsin."

Politika:
1. `birimi_cevir` sonucu yuvarlamaz; standart sınırı da olduğu gibi kullanılır.
2. Okunan değerin (birime çevrildikten sonraki) herhangi bir uç noktası şartın
   herhangi bir sınırına `math.isclose(e, b, rel_tol=SINIR_YAKINLIK_BAGIL,
   abs_tol=SINIR_YAKINLIK_MUTLAK)` ile yakınsa karar `insan_incelemeli` olur;
   gerekçede "sınıra çok yakın" ve değerin yuvarlanmamış hali (repr) geçer.
3. İstisna: birim dönüşümü yapılmadıysa (aynı birim ya da ikisi de yok) ve
   değer sınıra tam eşitse dahil/hariç kuralı geçerli kalır. Birim dönüşümü
   yapıldıysa tam eşitlik de bant içindedir (insan incelemeli).
4. Bandın dışı eskisi gibi: açıkça içeride uygun, açıkça dışarıda uygun değil.
"""

from __future__ import annotations

import pytest

from malzeme_kabul.kural import karar_motoru
from malzeme_kabul.kural.birimler import kayit
from malzeme_kabul.kural.karar_motoru import birimi_cevir, kontrol_et
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri

YAKIN = "sınıra çok yakın"


def _sinir(alt=None, ust=None, birim=None, alt_dahil=True, ust_dahil=True):
    return {
        "kriter_turu": "sayisal", "alt": alt, "ust": ust, "birim": birim,
        "alt_dahil": alt_dahil, "ust_dahil": ust_dahil, "orijinal_metin": "metin",
    }


def _dokuman(sinir) -> KabulDokumani:
    return KabulDokumani.model_validate({
        "standart": {"belge_no": "MIL-PRF-23377", "revizyon": "K"},
        "testler": [{
            "id": "olcum", "test_adi": "Drying time", "sinir": sinir, "test_turleri": ["kabul"],
            "kaynak": {"belge_no": "MIL-PRF-23377", "revizyon": "K", "madde": "3.7.2"},
        }],
    })


def _sertifika(sonuc: str, birim: str | None) -> Sertifika:
    return Sertifika(
        sertifika_no="S-YAKIN", standart_atfi="MIL-PRF-23377K Type I Class C2",
        satirlar=[SertifikaSatiri(test_adi="Drying time", sonuc=sonuc, birim=birim)],
    )


def _kontrol(sinir, sonuc, birim):
    return kontrol_et(_dokuman(sinir), _sertifika(sonuc, birim))


def _satir(sinir, sonuc, birim):
    return _kontrol(sinir, sonuc, birim).satirlar[0]


# --- sabitler ve birimi_cevir ----------------------------------------------


def test_sinir_yakinlik_sabitlerinin_degerleri():
    assert karar_motoru.SINIR_YAKINLIK_BAGIL == 1e-6
    assert karar_motoru.SINIR_YAKINLIK_MUTLAK == 1e-12


def test_birimi_cevir_ayni_birimde_degeri_yuvarlamaz():
    assert birimi_cevir(1.0000000000004, "s", "s") == 1.0000000000004


def test_birimi_cevir_cevrilen_degeri_on_iki_basamaga_yuvarlamaz():
    sonuc = birimi_cevir(1000.0000000004, "ms", "s")
    assert sonuc > 1.0
    assert sonuc == kayit().Quantity(1000.0000000004, "ms").to("s").magnitude


def test_birimi_cevir_pint_sonucunu_aynen_dondurur():
    deger = 1.23456789012345  # 12 anlamlı basamakta yuvarlanınca değişen bir değer
    beklenen = kayit().Quantity(deger, "minute").to("hour").magnitude
    assert birimi_cevir(deger, "min", "hour") == beklenen
    assert birimi_cevir(deger, "min", "hour") != float(f"{beklenen:.12g}")


# --- aynı birimde bant ------------------------------------------------------


def test_ust_sinirin_hemen_ustu_ayni_birimde_uygun_sayilmaz_insana_gider():
    satir = _satir(_sinir(ust=1, birim="s"), "1.0000000000004", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce
    assert "1.0000000000004" in satir.gerekce  # değer yuvarlanmadan yazılır


def test_alt_sinirin_hemen_alti_ayni_birimde_uygun_sayilmaz_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), "0.9999999999996", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce
    assert "0.9999999999996" in satir.gerekce


def test_ust_sinirin_hemen_alti_ayni_birimde_insana_gider():
    satir = _satir(_sinir(ust=1, birim="s"), "0.9999999999996", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_alt_sinirin_hemen_ustu_ayni_birimde_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), "1.0000000000004", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_birimsiz_sartta_alt_sinirin_hemen_alti_insana_gider():
    satir = _satir(_sinir(alt=5), "4.9999999999996", None)
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_iki_sinirli_sartta_alt_sinira_yakin_deger_insana_gider():
    satir = _satir(_sinir(alt=15, ust=23, birim="µm"), "15.000000000001", "µm")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_kucuktur_ifadesinin_ucu_sinira_yakinsa_insana_gider():
    # "<0.9999999999996 s": okunan aralığın üst ucu "en çok 1 s" sınırına yakın
    satir = _satir(_sinir(ust=1, birim="s"), "<0.9999999999996", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_bagil_bant_icindeki_deger_insana_gider():
    # 340.0003 / 340: bağıl fark ~8.8e-7 < 1e-6
    satir = _satir(_sinir(ust=340, birim="g/L"), "340.0003", "g/L")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_bagil_bant_disindaki_deger_ayni_birimde_uygun_degil():
    # 340.001 / 340: bağıl fark ~2.9e-6 > 1e-6
    assert _satir(_sinir(ust=340, birim="g/L"), "340.001", "g/L").karar == "uygun_degil"


def test_bagil_bant_disindaki_deger_ayni_birimde_icerideyse_uygun():
    assert _satir(_sinir(ust=340, birim="g/L"), "339.999", "g/L").karar == "uygun"


def test_sifir_sinirda_mutlak_bant_icindeki_deger_insana_gider():
    # sınır 0 iken bağıl tolerans işe yaramaz; mutlak bant 1e-12
    satir = _satir(_sinir(ust=0, birim="ppm"), "0.0000000000001", "ppm")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_sifir_sinirda_mutlak_bant_disindaki_deger_uygun_degil():
    assert _satir(_sinir(ust=0, birim="ppm"), "0.000000001", "ppm").karar == "uygun_degil"


# --- aynı birimde tam sınır (istisna: dahil/hariç kuralı geçerli) -------------


def test_tam_ust_sinir_ayni_birimde_dahilse_uygun():
    assert _satir(_sinir(ust=5, birim="hour"), "5", "hour").karar == "uygun"


def test_tam_alt_sinir_ayni_birimde_dahilse_uygun():
    assert _satir(_sinir(alt=4, birim="hour"), "4", "hour").karar == "uygun"


def test_tam_ust_sinir_ayni_birimde_haricse_uygun_degil():
    assert _satir(_sinir(ust=5, birim="hour", ust_dahil=False), "5", "hour").karar == "uygun_degil"


def test_tam_alt_sinir_ayni_birimde_haricse_uygun_degil():
    assert _satir(_sinir(alt=4, birim="hour", alt_dahil=False), "4", "hour").karar == "uygun_degil"


def test_tam_sinir_birimsiz_sartta_dahilse_uygun():
    assert _satir(_sinir(alt=5), "5", None).karar == "uygun"


def test_kucuktur_bir_ile_en_cok_bir_ayni_birimde_uygun():
    # "<1 s" okunan aralığı en çok 1 s'nin içindedir; tam eşit uç, dönüşüm yok
    assert _satir(_sinir(ust=1, birim="s"), "<1", "s").karar == "uygun"


def test_tam_sinir_esanlamli_birim_yazilisinda_donusum_sayilmaz_uygun():
    # "saat" ile "hour" aynı birimdir (BIRIM_ESANLAMLILARI); çarpan 1, dönüşüm yok
    assert _satir(_sinir(ust=5, birim="hour"), "5", "saat").karar == "uygun"


# --- çevrilen birimde bant ----------------------------------------------------


def test_ust_sinirin_hemen_ustu_cevrilen_birimde_insana_gider():
    # 1000.0000000004 ms = 1.0000000000004 s; 12 basamağa yuvarlansa 1 s olur ve uygun çıkardı
    satir = _satir(_sinir(ust=1, birim="s"), "1000.0000000004", "ms")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce
    assert satir.cevrilmis_deger > 1.0
    assert repr(satir.cevrilmis_deger) in satir.gerekce


def test_alt_sinirin_hemen_alti_cevrilen_birimde_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), "999.9999999996", "ms")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce
    assert satir.cevrilmis_deger < 1.0


def test_ust_sinirin_hemen_ustu_saniyeden_dakikaya_insana_gider():
    satir = _satir(_sinir(ust=1, birim="minute"), "60.000000000024", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


# --- çevrilen birimde tam sınır: bant içinde ----------------------------------


def test_tam_sinir_saniyeden_dakikaya_cevrilince_insana_gider():
    satir = _satir(_sinir(ust=1, birim="minute"), "60", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_tam_sinir_dakikadan_saate_cevrilince_insana_gider():
    satir = _satir(_sinir(ust=5, birim="hour"), "300", "dk")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_tam_alt_sinir_cevrilen_birimde_insana_gider():
    satir = _satir(_sinir(alt=1, birim="minute"), "60", "s")
    assert satir.karar == "insan_incelemeli"


def test_tam_haric_sinir_cevrilen_birimde_red_degil_insana_gider():
    satir = _satir(_sinir(ust=1, birim="minute", ust_dahil=False), "60", "s")
    assert satir.karar == "insan_incelemeli"


# --- çevrilen birimde bant dışı -----------------------------------------------


def test_bant_disinda_icerideki_deger_cevrilen_birimde_uygun():
    # 999.9 ms = 0.9999 s: bağıl 1e-4 uzak, en çok 1 s içinde
    assert _satir(_sinir(ust=1, birim="s"), "999.9", "ms").karar == "uygun"


def test_bant_disinda_disaridaki_deger_cevrilen_birimde_uygun_degil():
    # 1000.1 ms = 1.0001 s: bağıl 1e-4 uzak, en çok 1 s dışında
    assert _satir(_sinir(ust=1, birim="s"), "1000.1", "ms").karar == "uygun_degil"


def test_bant_disinda_alt_sinirin_altindaki_deger_cevrilen_birimde_uygun_degil():
    assert _satir(_sinir(alt=4, birim="hour"), "239.9", "min").karar == "uygun_degil"


def test_bant_disinda_alt_sinirin_ustundeki_deger_cevrilen_birimde_uygun():
    assert _satir(_sinir(alt=4, birim="hour"), "240.1", "min").karar == "uygun"


# --- parti kararı -------------------------------------------------------------


def test_bant_icindeki_tek_satir_parti_kararini_incelemeye_ceker():
    sonuc = _kontrol(_sinir(ust=1, birim="s"), "1.0000000000004", "s")
    assert sonuc.revizyon.karar == "uygun"
    assert sonuc.belge_karari == "inceleme"


def test_cevrilen_tam_sinirdaki_tek_satir_partiyi_kabul_ettirmez():
    sonuc = _kontrol(_sinir(ust=5, birim="hour"), "300", "dk")
    assert sonuc.belge_karari == "inceleme"


def test_bant_disindaki_uygun_satir_partiyi_kabul_ettirir():
    assert _kontrol(_sinir(ust=1, birim="s"), "999.9", "ms").belge_karari == "kabul"


# --- float'a kayıplı okunan sayı metinleri (tam eşitlik istisnası uygulanmaz) ----
# İstisna yalnız metin float'a kayıpsız sığıyorsa geçerlidir:
# Decimal(metin, virgül noktaya çevrilmiş) == Decimal(repr(float(metin))).


def test_float_a_kayipli_ust_sinir_ustu_tam_esit_sayilmaz_insana_gider():
    # "1.00000000000000001" float'ta 1.0 olur; gerçek değer en çok 1 s'nin üstünde
    satir = _satir(_sinir(ust=1, birim="s"), "1.00000000000000001", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_float_a_kayipli_alt_sinir_alti_tam_esit_sayilmaz_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), "0.99999999999999999", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_float_a_kayipli_kucuktur_ifadesi_tam_esit_sayilmaz_insana_gider():
    satir = _satir(_sinir(ust=1, birim="s"), "<1.00000000000000001", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_float_a_kayipli_buyuktur_ifadesi_tam_esit_sayilmaz_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), ">0.99999999999999999", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_kayipsiz_ondalik_tam_ust_sinirda_dahilse_uygun():
    # "0.1" float'ta tam değildir ama repr'i "0.1"dir: kayıpsız sayılır, davranış değişmez
    assert _satir(_sinir(ust=0.1, birim="s"), "0.1", "s").karar == "uygun"


def test_virgullu_ondalik_tam_alt_sinirda_dahilse_uygun():
    assert _satir(_sinir(alt=1.5, birim="s"), "1,5", "s").karar == "uygun"


def test_virgullu_ondalik_tam_alt_sinirda_haricse_uygun_degil():
    assert _satir(_sinir(alt=1.5, birim="s", alt_dahil=False), "1,5", "s").karar == "uygun_degil"


# --- büyüktür ifadesi ve iki sınırlı şartta üst sınır ------------------------


def test_buyuktur_ifadesinin_ucu_sinira_yakinsa_insana_gider():
    satir = _satir(_sinir(alt=1, birim="s"), ">1.0000000000004", "s")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce


def test_buyuktur_ifadesi_bant_disinda_alt_sinirin_ustundeyse_uygun():
    assert _satir(_sinir(alt=1, birim="s"), ">1.0001", "s").karar == "uygun"


def test_buyuktur_ifadesi_bant_disinda_ust_sinirin_ustundeyse_uygun_degil():
    assert _satir(_sinir(ust=1, birim="s"), ">1.0001", "s").karar == "uygun_degil"


def test_buyuktur_ifadesi_tam_alt_sinirda_ayni_birimde_uygun():
    # ">1 s" okunan aralığı en az 1 s'nin içindedir; tam eşit uç, dönüşüm yok, kayıpsız
    assert _satir(_sinir(alt=1, birim="s"), ">1", "s").karar == "uygun"


def test_iki_sinirli_sartta_ust_sinira_yakin_deger_insana_gider():
    satir = _satir(_sinir(alt=15, ust=23, birim="µm"), "22.999999999999", "µm")
    assert satir.karar == "insan_incelemeli"
    assert YAKIN in satir.gerekce
