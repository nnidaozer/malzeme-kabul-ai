"""Etiketleme kararları (Nida, 25 Kasım 2026): iç muayene şartları, test koşulu
alanı ve bölüm bazında F1.

- Etiketleme, ambalaj ve işaretleme şartları `muayene` türüyle işaretlenir;
  sonuç kaynağı `ic_muayene`dir. CoC'de aranmaz, yanlış kabul ölçümüne girmez.
- Tek bir kriterin koşulları (sıcaklık, süre) kaydı bölmez; `test_kosulu`
  alanına yazılır.
- F1 hem genel (mikro) hem bölüm bazında (bölümlerin ortalaması) raporlanır;
  tek bir tablo ölçümü domine etmesin.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import betik_yukle

from deney.degerlendirme import degerlendir
from deney.sertifika_uretici import uret
from malzeme_kabul.arayuz.dokuman_uretici import bolumler, markdown_uret
from malzeme_kabul.kural.karar_motoru import kontrol_et
from malzeme_kabul.sozlesme.sema import KabulDokumani, Kaynak, Sinir, StandartBilgisi
from malzeme_kabul.sozlesme.sema import TestSarti as Sart
from malzeme_kabul.sozlesme.sertifika import Sertifika, SertifikaSatiri


KOK = Path(__file__).resolve().parents[1]


def kaynak(madde, sayfa=None):
    return Kaynak(belge_no="MIL-PRF-23377", revizyon="K", madde=madde, sayfa=sayfa)


def sayisal(alt=None, ust=None, birim="cP"):
    return Sinir(kriter_turu="sayisal", alt=alt, ust=ust, birim=birim, orijinal_metin="x")


METIN = Sinir(kriter_turu="metinsel", orijinal_metin="Containers shall be labeled.")


def sart(id, turler=("kabul",), madde="3.5", sinir=None, **k):
    return Sart(id=id, test_adi=id.replace("_", " ").capitalize(), sinir=sinir or sayisal(ust=100),
                kaynak=kaynak(madde), test_turleri=set(turler), **k)


def dok(*testler):
    return KabulDokumani(standart=StandartBilgisi(belge_no="MIL-PRF-23377", revizyon="K"), testler=list(testler))


# --- şema ---------------------------------------------------------------------

def test_muayene_sartinin_sonuc_kaynagi_ic_muayene_olur():
    t = sart("container_labeling", turler=("muayene",), sinir=METIN)
    assert t.sonuc_kaynagi == "ic_muayene"
    assert t.muayene_sarti
    assert not t.kabul_testi


def test_muayene_baska_test_turuyle_birlesmez():
    with pytest.raises(ValidationError, match="muayene"):
        sart("container_labeling", turler=("muayene", "kabul"), sinir=METIN)


def test_muayene_sarti_ic_laboratuvara_baglanamaz():
    with pytest.raises(ValidationError, match="ic_muayene"):
        sart("container_labeling", turler=("muayene",), sinir=METIN, sonuc_kaynagi="ic_laboratuvar")


def test_ic_muayene_yalniz_muayene_sartinda_kullanilir():
    with pytest.raises(ValidationError, match="ic_muayene"):
        sart("viscosity", sonuc_kaynagi="ic_muayene")


def test_test_kosulu_alani_istege_baglidir():
    assert sart("viscosity").test_kosulu is None
    t = sart("peel_strength_jp_4", test_kosulu="7 gün JP-4 içinde, 140 °F")
    assert t.test_kosulu == "7 gün JP-4 içinde, 140 °F"


# --- karar motoru ve ölçüm ---------------------------------------------------------

def test_muayene_sarti_cocde_aranmaz_ve_karar_satiri_olmaz():
    d = dok(sart("viscosity"), sart("container_labeling", turler=("muayene",), sinir=METIN))
    s = Sertifika(sertifika_no="S-1", standart_atfi="MIL-PRF-23377K",
                  satirlar=[SertifikaSatiri(test_adi="Viscosity", sonuc="50", birim="cP"),
                            SertifikaSatiri(test_adi="Container labeling", sonuc="Conforms")])
    sonuc = kontrol_et(d, s)
    assert [r.test_id for r in sonuc.satirlar] == ["viscosity"]
    assert sonuc.eslesmeyen_satirlar == []  # dokümanda var, yalnız CoC'de aranmıyor
    assert sonuc.belge_karari == "kabul"


def test_muayene_sarti_sentetik_sertifikaya_ve_dogru_karara_girmez():
    d = KabulDokumani.model_validate_json((KOK / "data" / "cikti" / "MIL-PRF-23377K_kabul_dokumani.json").read_text(encoding="utf-8"))
    d.testler.append(sart("container_labeling", turler=("muayene",), sinir=METIN))
    for u in uret(d):
        assert "container_labeling" not in u.dogru.satirlar
        assert all("labeling" not in r.test_adi.casefold() for r in u.sertifika.satirlar)


# --- kabul dokümanı ------------------------------------------------------------------

def test_kabul_dokumaninda_ic_muayene_bolumu_olur():
    d = dok(sart("viscosity"), sart("container_labeling", turler=("muayene",), sinir=METIN))
    basliklar = [b.baslik for b in bolumler(d)]
    assert "İç muayene şartları" in basliklar
    assert "İç muayene" in markdown_uret(d)


# --- bölüm bazında F1 --------------------------------------------------------------

def _tablo_dok():
    # 3.3.2.8: büyük tablo (dört satır), 3.4: tek şart
    satirlar = [sart(f"peel_{i}", madde="3.3.2.8", sinir=sayisal(alt=15, birim="lbf/in")) for i in range(4)]
    return dok(*satirlar, sart("viscosity", madde="3.4", sinir=sayisal(ust=100)))


def test_bolum_bazinda_f1_buyuk_tablonun_agirligini_dengeler():
    gold = _tablo_dok()
    tahmin = _tablo_dok()
    tahmin.testler[-1] = sart("viscosity", madde="3.4", sinir=sayisal(ust=999))  # 3.4 yanlış
    sonuc = degerlendir(tahmin, gold)
    assert set(sonuc.bolumler) == {"3.3.2.8", "3.4"}
    assert sonuc.bolumler["3.3.2.8"].f1 == 1.0
    assert sonuc.bolumler["3.4"].f1 < 1.0
    beklenen = (sonuc.bolumler["3.3.2.8"].f1 + sonuc.bolumler["3.4"].f1) / 2
    assert sonuc.bolum_ortalamasi["f1"] == pytest.approx(beklenen)
    assert sonuc.bolum_ortalamasi["f1"] < sonuc.genel.f1  # büyük tablo mikro ortalamayı şişirir


def test_fazladan_tahmin_kendi_bolumune_yazilir():
    gold = dok(sart("viscosity", madde="3.4"))
    tahmin = dok(sart("viscosity", madde="3.4"), sart("odor", madde="3.6.3"))
    sonuc = degerlendir(tahmin, gold)
    assert sonuc.bolumler["3.6.3"].dp == 0 and sonuc.bolumler["3.6.3"].yp > 0
    assert sonuc.bolumler["3.4"].f1 == 1.0


def test_tabloda_bolum_ortalamasi_satiri_var():
    satirlar = degerlendir(_tablo_dok(), _tablo_dok()).tablo()
    adlar = [s["alan"] for s in satirlar]
    assert adlar[-2:] == ["GENEL (mikro)", "GENEL (bölüm ortalaması)"]
    assert satirlar[-1]["f1"] == 1.0


def test_degerlendir_betigi_bolum_tablosunu_yazar(tmp_path, capsys):
    yol = tmp_path / "d.json"
    yol.write_text(_tablo_dok().model_dump_json(), encoding="utf-8")
    betik = betik_yukle("deney/degerlendir.py")
    assert betik.main([str(yol), str(yol), "--bolumler"]) == 0
    cikti = capsys.readouterr().out
    assert "GENEL (bölüm ortalaması)" in cikti
    assert "3.3.2.8" in cikti
