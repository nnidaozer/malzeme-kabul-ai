"""Geliştirme / test bölünmesinin testleri (data/bolunme.yaml, docs/mimari.md madde 7)."""

from __future__ import annotations

import pytest

from conftest import KOK, betik_yukle
from deney.bolunme import Bolunme, TestKumesiKilitli, bolunme_oku

YAML = """# yorum
test_kumesi_acik: false
gelistirme:
  - MIL-PRF-23377K   # satır sonu yorumu
test:
  - MIL-PRF-85285E
"""


def yaz(tmp_path, metin):
    yol = tmp_path / "bolunme.yaml"
    yol.write_text(metin, encoding="utf-8")
    return yol


def test_depodaki_bolunme_gecerli_ve_test_kumesi_kilitli():
    b = bolunme_oku()
    assert b.gelistirme and b.test
    assert not set(b.gelistirme) & set(b.test)
    assert b.test_kumesi_acik is False
    assert all(r in b.gelistirme for r in ("MIL-PRF-23377G", "MIL-PRF-23377H", "MIL-PRF-23377J", "MIL-PRF-23377K"))


def test_depodaki_bolunme_yaml_ile_ayni_okunur():
    yaml = pytest.importorskip("yaml")
    veri = yaml.safe_load((KOK / "data" / "bolunme.yaml").read_text(encoding="utf-8"))
    b = bolunme_oku()
    assert (veri["gelistirme"], veri["test"], veri["test_kumesi_acik"]) == (b.gelistirme, b.test, b.test_kumesi_acik)


def test_okuma(tmp_path):
    assert bolunme_oku(yaz(tmp_path, YAML)) == Bolunme(gelistirme=["MIL-PRF-23377K"], test=["MIL-PRF-85285E"])


def test_kullanim_izni(tmp_path):
    b = bolunme_oku(yaz(tmp_path, YAML))
    assert b.kullanima_izin_ver("MIL-PRF-23377K") == "gelistirme"
    with pytest.raises(TestKumesiKilitli):
        b.kullanima_izin_ver("MIL-PRF-85285E")
    with pytest.raises(ValueError, match="bolunme.yaml içinde yok"):
        b.kullanima_izin_ver("MIL-PRF-81733D")
    acik = bolunme_oku(yaz(tmp_path, YAML.replace("false", "true")))
    assert acik.kullanima_izin_ver("MIL-PRF-85285E") == "test"


@pytest.mark.parametrize(
    "metin, hata",
    [
        ("gelistirme:\n  - MIL-PRF-23377K\ntest:\n  - MIL-PRF-23377K\n", "yalnız bir kümede"),
        ("gelistirme:\n  - 23377K\n", "biçiminde"),
        ("egitim:\n  - MIL-PRF-23377K\n", "bilinmeyen"),
        ("  - MIL-PRF-23377K\n", "anahtarın altında"),
        ("test_kumesi_acik: evet\n", "true/false"),
        ("gelistirme: [MIL-PRF-23377K]\n", "true/false"),
    ],
)
def test_hatali_dosya_reddedilir(tmp_path, metin, hata):
    with pytest.raises(ValueError, match=hata):
        bolunme_oku(yaz(tmp_path, metin))


def test_dil_modeli_betigi_test_kumesini_reddeder(tmp_path, capsys):
    from pdf_uretici import pdf_yaz

    pdf = tmp_path / "MIL-PRF-85285E.pdf"
    pdf_yaz(pdf, [{"metin": ["3.1 Viscosity."]}])
    betik = betik_yukle("deney/dil_modeli_cikar.py")
    kod = betik.main([str(pdf), "--model", "deneme:7b", "--bolunme", str(yaz(tmp_path, YAML)), "--cikti", str(tmp_path / "c")])
    assert kod == 2
    assert "test kümesinde" in capsys.readouterr().err
    assert not (tmp_path / "c").exists()  # modele hiç gidilmedi
