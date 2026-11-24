"""Geliştirme / test bölünmesinin testleri (data/bolunme.yaml, docs/mimari.md madde 7)."""

from __future__ import annotations

import json

import pytest

from conftest import KOK, betik_yukle
from deney.bolunme import Bolunme, TestKumesiKilitli, bolunme_oku, bolunme_yaz, main, yariyi_sec

GELISTIRME = """# yorum
test_kumesi_acik: false
test_durumu: bekliyor
tohum: 7

gelistirme:
  - MIL-PRF-23377K   # satır sonu yorumu

yeni_standartlar:
  - MIL-PRF-1A
  - MIL-PRF-2B
  - MIL-PRF-3C
  - MIL-PRF-4D
  - MIL-PRF-5E

test:
"""
YENI = ["MIL-PRF-1A", "MIL-PRF-2B", "MIL-PRF-3C", "MIL-PRF-4D", "MIL-PRF-5E"]


def yaz(tmp_path, metin, ad="bolunme.yaml"):
    yol = tmp_path / ad
    yol.write_text(metin, encoding="utf-8")
    return yol


# --- Depodaki dosya -------------------------------------------------------------------


def test_depodaki_bolunme_nidanin_kararina_uyar():
    b = bolunme_oku()
    assert set(b.gelistirme) >= {
        "MIL-PRF-23377G", "MIL-PRF-23377H", "MIL-PRF-23377J", "MIL-PRF-23377K", "MIL-PRF-81733D", "MIL-PRF-85285E",
    }
    assert b.test_kumesi_acik is False
    if b.test_durumu == "bekliyor":
        assert b.test == []
    else:
        assert b.test == yariyi_sec(b.yeni_standartlar, b.tohum)


def test_depodaki_bolunme_yaml_ile_ayni_okunur():
    yaml = pytest.importorskip("yaml")
    veri = yaml.safe_load((KOK / "data" / "bolunme.yaml").read_text(encoding="utf-8"))
    b = bolunme_oku()
    assert (veri["gelistirme"], veri["test"] or [], veri["test_durumu"], veri["tohum"]) == (
        b.gelistirme, b.test, b.test_durumu, b.tohum,
    )


# --- Seçim ------------------------------------------------------------------------------


def test_secim_tohuma_bagli_ve_sirasiz():
    a = yariyi_sec(YENI, 7)
    assert a == yariyi_sec(list(reversed(YENI)), 7)  # girdi sırası önemsiz
    assert len(a) == 3 and set(a) <= set(YENI) and a == sorted(a)  # 5'in yarısı yukarı yuvarlanır
    assert len(yariyi_sec(YENI[:4], 7)) == 2
    farkli = {tuple(yariyi_sec(YENI, t)) for t in range(20)}
    assert len(farkli) > 1  # tohum seçimi gerçekten değiştirir


def test_bekliyorken_yeni_standartlara_bakilmaz(tmp_path):
    b = bolunme_oku(yaz(tmp_path, GELISTIRME))
    assert b.kullanima_izin_ver("MIL-PRF-23377K") == "gelistirme"
    for s in YENI:
        with pytest.raises(TestKumesiKilitli, match="test kümesi seçilene kadar"):
            b.kullanima_izin_ver(s)
    with pytest.raises(ValueError, match="bolunme.yaml içinde yok"):
        b.kullanima_izin_ver("MIL-PRF-9Z")


def test_secim_yarisini_teste_kalanini_gelistirmeye_yazar(tmp_path):
    yol = yaz(tmp_path, GELISTIRME)
    assert main(["--yol", str(yol), "--sec"]) == 0
    b = bolunme_oku(yol)
    test = yariyi_sec(YENI, 7)
    assert b.test_durumu == "secildi" and b.test == test
    assert b.gelistirme == ["MIL-PRF-23377K"] + [s for s in YENI if s not in test]
    assert yol.read_text(encoding="utf-8").startswith("# yorum\n")  # açıklamalar korunur
    for s in test:
        with pytest.raises(TestKumesiKilitli, match="test kümesinde"):
            b.kullanima_izin_ver(s)
    for s in set(YENI) - set(test):
        assert b.kullanima_izin_ver(s) == "gelistirme"
    with pytest.raises(ValueError, match="zaten seçilmiş"):
        b.secimi_yap()


def test_kilit_acilinca_test_kumesi_kullanilir(tmp_path):
    yol = yaz(tmp_path, GELISTIRME)
    main(["--yol", str(yol), "--sec"])
    b = bolunme_oku(yol)
    acik = Bolunme(**{**b.__dict__, "test_kumesi_acik": True})
    bolunme_yaz(acik, yol)
    assert bolunme_oku(yol).kullanima_izin_ver(b.test[0]) == "test"


def test_elle_degistirilmis_secim_reddedilir(tmp_path):
    yol = yaz(tmp_path, GELISTIRME)
    main(["--yol", str(yol), "--sec"])
    b = bolunme_oku(yol)
    disarida = next(s for s in YENI if s not in b.test)
    sahte = Bolunme(**{**b.__dict__, "test": sorted(b.test[1:] + [disarida]),
                       "gelistirme": [g for g in b.gelistirme if g != disarida] + [b.test[0]]})
    bolunme_yaz(sahte, yol)
    with pytest.raises(ValueError, match="uyuşmuyor"):
        bolunme_oku(yol)


@pytest.mark.parametrize(
    "metin, hata",
    [
        ("gelistirme:\n  - MIL-PRF-23377K\n  - MIL-PRF-23377K\n", "tekrar"),
        ("gelistirme:\n  - 23377K\n", "biçiminde"),
        ("egitim:\n  - MIL-PRF-23377K\n", "bilinmeyen"),
        ("  - MIL-PRF-23377K\n", "liste anahtarının altında"),
        ("test_kumesi_acik: evet\n", "bool"),
        ("test_durumu: hazir\n", "bekliyor"),
        ("gelistirme: [MIL-PRF-23377K]\n", "tanınmayan değer"),
        ("test:\n  - MIL-PRF-1A\n", "boş olmalı"),
        ("gelistirme:\n  - MIL-PRF-1A\nyeni_standartlar:\n  - MIL-PRF-1A\n", "geliştirme kümesinde olamaz"),
        ("test_kumesi_acik: true\n", "seçilmeden kilit açılamaz"),
    ],
)
def test_hatali_dosya_reddedilir(tmp_path, metin, hata):
    with pytest.raises(ValueError, match=hata):
        bolunme_oku(yaz(tmp_path, metin))


# --- Betiklerin kilidi ----------------------------------------------------------------


@pytest.fixture
def kilitli(tmp_path):
    """MIL-PRF-23377K geliştirmede, MIL-PRF-85285E bölünme bekliyor."""
    return yaz(tmp_path, "gelistirme:\n  - MIL-PRF-23377K\nyeni_standartlar:\n  - MIL-PRF-85285E\n")


def _pdf(tmp_path, ad):
    from pdf_uretici import pdf_yaz

    pdf = tmp_path / ad
    pdf_yaz(pdf, [{"metin": ["3.1 Viscosity."]}])
    return pdf


def _dokuman(tmp_path, revizyon="E", belge_no="MIL-PRF-85285"):
    yol = tmp_path / f"{belge_no}{revizyon}.json"
    yol.write_text(json.dumps({"standart": {"belge_no": belge_no, "revizyon": revizyon}}), encoding="utf-8")
    return yol


def test_dil_modeli_betigi_reddeder(tmp_path, kilitli, capsys):
    betik = betik_yukle("deney/dil_modeli_cikar.py")
    pdf = _pdf(tmp_path, "MIL-PRF-85285E.pdf")
    kod = betik.main([str(pdf), "--model", "deneme:7b", "--bolunme", str(kilitli), "--cikti", str(tmp_path / "c")])
    assert kod == 2 and "test kümesi seçilene kadar" in capsys.readouterr().err
    assert not (tmp_path / "c").exists()  # modele hiç gidilmedi


def test_kural_cikarici_betigi_reddeder(tmp_path, kilitli, capsys):
    betik = betik_yukle("scripts/kabul_dokumani_uret.py")
    pdf = _pdf(tmp_path, "MIL-PRF-85285E.pdf")
    assert betik.main([str(pdf), "--bolunme", str(kilitli), "--cikti", str(tmp_path / "c")]) == 2
    assert not (tmp_path / "c").exists()
    assert "kabul_dokumani_uret" in capsys.readouterr().err


def test_revizyon_betigi_reddeder(tmp_path, kilitli):
    betik = betik_yukle("scripts/revizyon_karsilastir.py")
    eski, yeni = _pdf(tmp_path, "MIL-PRF-85285D.pdf"), _pdf(tmp_path, "MIL-PRF-85285E.pdf")
    assert betik.main([str(eski), str(yeni), "--bolunme", str(kilitli), "--cikti", str(tmp_path / "c")]) == 2


@pytest.mark.parametrize(
    "betik_yolu, argumanlar",
    [
        ("deney/kontrol_listesi_uret.py", lambda d, t: [str(d), "--cikti", str(t / "liste.md")]),
        ("deney/degerlendir.py", lambda d, t: [str(d), str(d)]),
        ("deney/taslak_karsilastir.py", lambda d, t: [str(d), str(d)]),
        ("deney/kanit_kontrol.py", lambda d, t: [str(d), str(t / "yok.pdf")]),
    ],
    ids=["kontrol_listesi", "degerlendir", "taslak_karsilastir", "kanit_kontrol"],
)
def test_taslak_ve_olcum_betikleri_reddeder(tmp_path, kilitli, capsys, betik_yolu, argumanlar):
    betik = betik_yukle(betik_yolu)
    assert betik.main(argumanlar(_dokuman(tmp_path), tmp_path) + ["--bolunme", str(kilitli)]) == 2
    assert "bakılmaz" in capsys.readouterr().err
    assert not (tmp_path / "liste.md").exists()
