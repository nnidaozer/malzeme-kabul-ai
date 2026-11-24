"""Standartların geliştirme / test bölünmesi (data/bolunme.yaml).

Test kümesi dil modeli çıkarıcısı bitene kadar kullanılmaz (docs/mimari.md
madde 7). Deney betikleri bir standardı işlemeden önce `kullanima_izin_ver`
çağırır; test kümesindeki standart, dosyada `test_kumesi_acik: true` yazana
kadar reddedilir. Bölünmede olmayan standart da reddedilir, böylece yeni bir
belge sessizce geliştirme kümesine karışmaz.

Dosya YAML'ın küçük bir alt kümesiyle yazılır (yorum, `anahtar: true/false`
ve `- öğe` listeleri); bağımlılık kilidine yeni paket eklememek için burada
okunur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

VARSAYILAN_YOL = Path(__file__).resolve().parents[1] / "data" / "bolunme.yaml"
BELGE_ETIKETI = re.compile(r"^[A-Z]+(-[A-Z]+)?-\d+[A-Z]$")
Kume = Literal["gelistirme", "test"]


class TestKumesiKilitli(PermissionError):
    """Test kümesindeki bir standart, kilit açılmadan kullanılmak istendi."""

    __test__ = False


@dataclass(frozen=True)
class Bolunme:
    gelistirme: list[str] = field(default_factory=list)
    test: list[str] = field(default_factory=list)
    test_kumesi_acik: bool = False

    __test__ = False

    def kume(self, belge_etiketi: str) -> Kume | None:
        if belge_etiketi in self.gelistirme:
            return "gelistirme"
        if belge_etiketi in self.test:
            return "test"
        return None

    def kullanima_izin_ver(self, belge_etiketi: str) -> Kume:
        """Standart kullanılabiliyorsa kümesini döner, değilse hata verir."""
        kume = self.kume(belge_etiketi)
        if kume is None:
            raise ValueError(f"{belge_etiketi} data/bolunme.yaml içinde yok; önce geliştirme ya da test kümesine ekle")
        if kume == "test" and not self.test_kumesi_acik:
            raise TestKumesiKilitli(
                f"{belge_etiketi} test kümesinde; dil modeli çıkarıcısı bitene kadar kullanılmaz "
                "(data/bolunme.yaml, test_kumesi_acik: false)"
            )
        return kume


def _ayristir(metin: str) -> dict[str, object]:
    veri: dict[str, object] = {}
    liste: list[str] | None = None
    for no, satir in enumerate(metin.splitlines(), 1):
        satir = satir.split("#", 1)[0].rstrip()
        if not satir.strip():
            continue
        if m := re.fullmatch(r"\s+-\s+(\S+)", satir):
            if liste is None:
                raise ValueError(f"satır {no}: liste öğesi bir anahtarın altında olmalı")
            liste.append(m.group(1))
            continue
        m = re.fullmatch(r"([a-z_]+):\s*(\S*)", satir)
        if not m:
            raise ValueError(f"satır {no}: tanınmayan satır: {satir!r}")
        anahtar, deger = m.groups()
        if anahtar in veri:
            raise ValueError(f"satır {no}: {anahtar} iki kez yazılmış")
        if deger == "":
            liste = []
            veri[anahtar] = liste
        elif deger in ("true", "false"):
            veri[anahtar] = deger == "true"
            liste = None
        else:
            raise ValueError(f"satır {no}: {anahtar} için true/false ya da liste bekleniyor: {deger!r}")
    return veri


def bolunme_oku(yol: str | Path = VARSAYILAN_YOL) -> Bolunme:
    veri = _ayristir(Path(yol).read_text(encoding="utf-8"))
    bilinmeyen = set(veri) - {"gelistirme", "test", "test_kumesi_acik"}
    if bilinmeyen:
        raise ValueError(f"bilinmeyen anahtarlar: {sorted(bilinmeyen)}")
    gelistirme, test = list(veri.get("gelistirme", [])), list(veri.get("test", []))
    hepsi = gelistirme + test
    tekrar = sorted({b for b in hepsi if hepsi.count(b) > 1})
    if tekrar:
        raise ValueError(f"bir standart yalnız bir kümede ve bir kez bulunur: {tekrar}")
    hatali = [b for b in hepsi if not BELGE_ETIKETI.match(b)]
    if hatali:
        raise ValueError(f"belge etiketi 'MIL-PRF-23377K' biçiminde olmalı: {hatali}")
    acik = veri.get("test_kumesi_acik", False)
    if not isinstance(acik, bool):
        raise ValueError("test_kumesi_acik true ya da false olmalı")
    return Bolunme(gelistirme=gelistirme, test=test, test_kumesi_acik=acik)
