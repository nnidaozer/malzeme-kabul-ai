"""docs/bagimsiz_etiketleme_istemi.md denetimi.

İstem dosyası ikinci modele verilir; içindeki biçim örneği şemaya uymalı ve
dosya, data/gold_taslak altındaki taslağın kimliklerini, test adlarını ya da
koşul adlarını içermemelidir (bağımsızlık).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from malzeme_kabul.sema import KabulDokumani

KOK = Path(__file__).resolve().parents[1]
ISTEM = KOK / "docs" / "bagimsiz_etiketleme_istemi.md"
TASLAKLAR = sorted((KOK / "data" / "gold_taslak").glob("*.json"))


def _istem() -> str:
    return ISTEM.read_text(encoding="utf-8")


def test_bicim_ornegi_semaya_uyar():
    eslesme = re.search(r"```json\n(.*?)```", _istem(), re.S)
    assert eslesme, "istemde ```json bloğu yok"
    KabulDokumani.model_validate_json(eslesme.group(1))


def _taslak_adlari(yol: Path) -> set[str]:
    d = json.loads(yol.read_text(encoding="utf-8"))
    adlar = set()
    for t in d.get("testler", []):
        adlar |= {t["id"], t["test_adi"]}
        if t.get("kaynak_tablo_adi"):
            adlar.add(t["kaynak_tablo_adi"])
    for k in d.get("kosullar", []):
        adlar.add(k["ad"])
    for n in d.get("numune_hazirlama", []):
        adlar.add(n["id"])
    return adlar


@pytest.mark.skipif(not TASLAKLAR, reason="data/gold_taslak altında taslak yok")
@pytest.mark.parametrize("yol", TASLAKLAR, ids=lambda p: p.stem)
def test_istem_taslaktan_ad_sizdirmaz(yol):
    metin = _istem().casefold()
    # Kısa, genel sözcükler (ör. "Odor", "Pot life") her istemde geçebilir; yalnızca
    # taslağa özgü olabilecek, en az iki sözcüklü ya da alt çizgili adları ara.
    sizanlar = sorted(
        a for a in _taslak_adlari(yol)
        if (" " in a.strip() or "_" in a) and len(a) >= 10 and a.casefold() in metin
    )
    assert not sizanlar, f"istem taslaktaki adları içeriyor: {sizanlar}"


def test_modele_verilen_metin_sema_dosyasini_okutmaz():
    # sema.py içindeki açıklama örneklerinin bir kısmı 23377K taslağından geliyor;
    # modele verilen bölüm (çizginin altı) o dosyayı kaynak olarak göstermemeli.
    model_metni = _istem().split("\n---\n", 1)[1]
    assert "sema.py" not in model_metni
    assert "`src/`" in model_metni  # okuma yasağında


def test_istem_kaynak_tablo_adi_alanini_tanimlar():
    assert "`kaynak_tablo_adi`" in _istem()


def test_istem_goruntu_okuma_cikti_klasoru_ve_taslak_yasagini_soyler():
    model_metni = _istem().split("\n---\n", 1)[1]
    assert "görüntü olarak" in model_metni
    assert "data/gold_codex/" in model_metni
    assert "**`data/gold_taslak/` klasörünü açma" in model_metni
    # Doğrulama komutu çıktıyı gold_codex altında arar; data/gold/ altına yazdırmaz.
    assert "Path('data/gold_codex/<BELGE>.json')" in model_metni
    assert "data/gold/<" not in model_metni


def test_istem_etiketleme_kilavuzunun_kurallarini_icerir():
    model_metni = _istem().split("\n---\n", 1)[1]
    assert "## Kapsam: neyi çıkaracaksın" in model_metni
    for ifade in ("Ürün tanımları girmez", "Bir kayıt, bir kriter", "\"Notes\" bölümü", "Muayene ve örnekleme"):
        assert ifade in model_metni
    assert (KOK / "docs" / "etiketleme_kilavuzu.md").is_file()
