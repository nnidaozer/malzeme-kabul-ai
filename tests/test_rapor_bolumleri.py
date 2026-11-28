"""docs/rapor/: bitirme raporu bölüm taslakları.

Denetlenenler:
- Dokuz bölüm dosyası var ve docs/rapor/README.md hepsine bağlantı veriyor.
- Sonuçlar ve sonuç bölümleri boş: başlık, not (">") ve HTML yorumu dışında
  metin yok. Sonuçlar ölçüm ve onaylı doğru cevaplar gelmeden yazılmaz.
- Deneyler bölümünde her "Sonuç" ve "Yorum" satırı boş (yalnız yorum).
- Backtick içindeki depo yolları gerçekten var (uydurma yol yok).
- Taslak bölümlerin (ilgili çalışmalar, veri, yöntem) "Kaynaklar" listesi var.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
RAPOR = KOK / "docs" / "rapor"
PAKET = KOK / "src" / "malzeme_kabul"

BOLUMLER = (
    "01_giris.md",
    "02_ilgili_calismalar.md",
    "03_mimari.md",
    "04_veri.md",
    "05_yontem.md",
    "06_deneyler.md",
    "07_sonuclar.md",
    "08_sinirliliklar.md",
    "09_sonuc.md",
)
BOS_BOLUMLER = ("07_sonuclar.md", "09_sonuc.md")
KAYNAKLI_BOLUMLER = ("02_ilgili_calismalar.md", "04_veri.md", "05_yontem.md")

# Henüz var olmayan ama planlanan klasörler (ayrı işlerde geliyor)
YOKSA_KABUL = ("deney/sonuclar/colab_uc_mod",)


def _metin(ad: str) -> str:
    return (RAPOR / ad).read_text(encoding="utf-8")


def _yorumsuz(metin: str) -> str:
    return re.sub(r"<!--.*?-->", "", metin, flags=re.S)


@pytest.mark.parametrize("ad", BOLUMLER)
def test_bolum_dosyasi_var_ve_basligi_numarali(ad):
    ilk = _metin(ad).splitlines()[0]
    assert ilk.startswith(f"# {int(ad[:2])}. "), ilk


def test_readme_butun_bolumlere_baglanir():
    readme = _metin("README.md")
    for ad in BOLUMLER:
        assert f"]({ad})" in readme, ad


@pytest.mark.parametrize("ad", BOS_BOLUMLER)
def test_sonuc_bolumleri_bos(ad):
    """Başlık ve boş satır dışında metin yok; ">" notu yalnız ilk alt başlıktan önce."""
    alt_baslik_goruldu = False
    for satir in _yorumsuz(_metin(ad)).splitlines():
        s = satir.strip()
        alt_baslik_goruldu = alt_baslik_goruldu or s.startswith("## ")
        not_satiri = s.startswith(">") and not alt_baslik_goruldu
        assert not s or s.startswith("#") or not_satiri, f"{ad}: {s!r}"


def test_deneylerde_sonuc_ve_yorum_bos():
    """Her "**Sonuç.**" / "**Yorum.**" bloğu, sonraki kalın etikete ya da başlığa kadar boş."""
    metin = _yorumsuz(_metin("06_deneyler.md"))
    bloklar = re.findall(r"\*\*(?:Sonuç|Yorum)\.\*\*(.*?)(?=\n\*\*|\n#|\Z)", metin, flags=re.S)
    deney_sayisi = len(re.findall(r"^## ", metin, flags=re.M))
    assert len(bloklar) == 2 * deney_sayisi
    for blok in bloklar:
        assert blok.strip() == "", blok


def _yol_var_mi(yol: str) -> bool:
    if yol.startswith(YOKSA_KABUL):
        return True
    return (KOK / yol).exists() or (PAKET / yol).exists()


def _yollar(metin: str) -> list[str]:
    yollar = []
    for parca in re.findall(r"`([^`\s]+)`", metin):
        parca = parca.split(":")[0].rstrip("/")
        if "/" not in parca or parca.startswith(("http", "/", "~")):
            continue
        if any(c in parca for c in "<>*…") or "..." in parca:
            continue
        if not re.search(r"\.(py|md|yaml|yml|csv|json|sh|ipynb|lock)$|^(src|docs|deney|data|scripts|tests|notebooks)/", parca):
            continue
        yollar.append(parca)
    return yollar


@pytest.mark.parametrize("ad", BOLUMLER + ("README.md",))
def test_backtick_yollari_depoda_var(ad):
    eksik = [y for y in _yollar(_metin(ad)) if not _yol_var_mi(y)]
    assert not eksik, f"{ad}: {eksik}"


@pytest.mark.parametrize("ad", KAYNAKLI_BOLUMLER)
def test_taslak_bolumlerde_kaynaklar_var(ad):
    metin = _metin(ad)
    assert "## Kaynaklar" in metin
    kaynaklar = metin.split("## Kaynaklar", 1)[1]
    assert re.search(r"https?://", kaynaklar)
