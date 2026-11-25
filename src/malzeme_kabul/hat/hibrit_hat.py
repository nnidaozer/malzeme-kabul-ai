"""Belge → okuma → kanıt → kural → karar → kayıt hattı; mod anahtarıyla (docs/mimari.md madde 6).

İki mod:

- `kural`: sertifika PDF'i kural tabanlı okuyucuyla okunur
  (`cikarim.sertifika_okuyucu.kural_ile_oku`). Dil modeli çağrılmaz.
- `hibrit`: sertifikayı yerel dil modeli okur (yalnız localhost,
  `cikarim.yerel_model.YerelModelIstemcisi`); her okunan satır kanıt
  doğrulayıcıdan geçer (`kural.kanit_dogrulama.satir_kaniti`). Kanıtsız
  satırlar karara girmez; `kanit` denetimi insan incelemeli olur. Kabul/red
  kararını her iki modda da kural motoru verir.

Dil modeli yanıt vermezse ya da şemaya uymayan yanıt dönerse hat kural
okumasına düşer ve bunu karar kaydına yazar (`hat.yedek`); karar yine
kurallarla verilir.

Standart tarafı: `standart_okumalarini_dogrula` dil modelinin standarttan
okuduğu `HamOkuma`'ları kanıt doğrulayıcı ve sınır yönü kuralından
(`kural.yon_dogrulama`) geçirir: kanıtsız okumalar reddedilir, yönü metinle
çelişen okumalar `belirsiz` yapılır (insan incelemesi).

Mod `MALZEME_KABUL_MODU` ortam değişkeniyle de seçilebilir (varsayılan
`kural`); model adı `MALZEME_KABUL_MODELI`, arka uç `MALZEME_KABUL_ARKA_UCU`,
adres `MALZEME_KABUL_MODEL_ADRESI` (yalnız localhost kabul edilir).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from malzeme_kabul.belge.pdf_okuyucu import Belge, pdf_oku
from malzeme_kabul.cikarim.sertifika_okuyucu import ISTEM_SURUMU, dil_modeli_ile_oku, kural_ile_oku, okumadan_sertifika
from malzeme_kabul.cikarim.yerel_model import SohbetIstemcisi, YerelModelIstemcisi
from malzeme_kabul.hat.katalog_karari import KatalogKarari, malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.kural.kanit_dogrulama import metin_sayfada_mi, okuma_kaniti, satir_kaniti
from malzeme_kabul.kural.karar_motoru import KararAyarlari, KararSatiri
from malzeme_kabul.kural.yon_dogrulama import okuma_yonu_dogrula
from malzeme_kabul.sozlesme.okuma import HamOkuma
from malzeme_kabul.sozlesme.sertifika import Sertifika

Mod = Literal["kural", "hibrit"]
MODLAR: tuple[str, ...] = ("kural", "hibrit")


class HatHatasi(ValueError):
    """Hat ayarı hatası (bilinmeyen mod, hibritte istemci yok...)."""


def mod_sec(mod: str | None = None) -> Mod:
    """Verilen mod, yoksa MALZEME_KABUL_MODU, yoksa 'kural'."""
    secilen = (mod or os.environ.get("MALZEME_KABUL_MODU") or "kural").strip().casefold()
    if secilen not in MODLAR:
        raise HatHatasi(f"bilinmeyen mod: {secilen!r} ({', '.join(MODLAR)})")
    return secilen  # type: ignore[return-value]


def ortamdan_istemci() -> YerelModelIstemcisi:
    """Ortam değişkenlerinden yerel model istemcisi kurar (yalnız localhost)."""
    model = os.environ.get("MALZEME_KABUL_MODELI")
    if not model:
        raise HatHatasi("hibrit mod için MALZEME_KABUL_MODELI ortam değişkeni gerekli")
    return YerelModelIstemcisi(
        model,
        arka_uc=os.environ.get("MALZEME_KABUL_ARKA_UCU", "ollama"),
        adres=os.environ.get("MALZEME_KABUL_MODEL_ADRESI") or None,
    )


@dataclass
class SertifikaOkumasi:
    """Hattın sertifika okuması: karara giren sertifika ve kanıt sonuçları."""

    sertifika: Sertifika
    mod: Mod
    model: str | None = None
    istem_surumu: str | None = None
    sayfalar: list[int] = field(default_factory=list)
    kanitsiz: list[str] = field(default_factory=list)  # "test adı: neden"
    yedek: str | None = None  # dil modeli başarısız olup kurala düşüldüyse nedeni

    def kanit_denetimi(self) -> KararSatiri | None:
        ortak = {"test_id": "kanit", "test_adi": "Okuma kanıtı (dil modeli)"}
        if self.mod != "hibrit":
            return None
        if self.yedek:
            return KararSatiri(karar="uygun", gerekce=f"dil modeli kullanılamadı, kural okuması: {self.yedek}", **ortak)
        if self.kanitsiz:
            return KararSatiri(karar="insan_incelemeli", gerekce="belgede bulunamayan okumalar: " + "; ".join(self.kanitsiz), **ortak)
        return KararSatiri(karar="uygun", gerekce="okunan bütün hücreler belgede bulundu", **ortak)

    def hat_bilgisi(self) -> dict:
        return {"mod": self.mod, "model": self.model, "istem_surumu": self.istem_surumu,
                "kanitsiz": self.kanitsiz, "yedek": self.yedek}


def _model_adi(istemci: SohbetIstemcisi) -> str:
    return getattr(istemci, "model", None) or type(istemci).__name__


def sertifikayi_oku(belge: Belge, mod: Mod, istemci: SohbetIstemcisi | None = None) -> SertifikaOkumasi:
    """Sertifikayı seçilen modda okur; hibritte her satırı kanıtla doğrular."""
    if mod == "kural":
        return SertifikaOkumasi(kural_ile_oku(belge), "kural", sayfalar=[s.no for s in belge.sayfalar])
    if istemci is None:
        raise HatHatasi("hibrit mod için yerel model istemcisi gerekli")
    model = _model_adi(istemci)
    try:
        okuma = dil_modeli_ile_oku(belge, istemci)
    except (OSError, ValueError) as hata:  # bağlantı yok, zaman aşımı, şemaya uymayan yanıt
        s = kural_ile_oku(belge)
        return SertifikaOkumasi(s, "hibrit", model, ISTEM_SURUMU, [x.no for x in belge.sayfalar],
                                yedek=f"{type(hata).__name__}: {hata}")
    metinler = {s.no: s.metin for s in belge.sayfalar}
    kabul, kanitsiz = [], []
    for satir in okuma.satirlar:
        k = satir_kaniti(satir, metinler)
        if k.kanitli:
            kabul.append(satir)
        else:
            kanitsiz.append(f"{satir.test_adi}: {k.neden}")
    atif = okuma.standart_atfi
    if atif and not any(metin_sayfada_mi(atif, m) for m in metinler.values()):
        kanitsiz.append(f"standart atfı: {atif!r} belgede yok")
        okuma = okuma.model_copy(update={"standart_atfi": None})
    sertifika = okumadan_sertifika(okuma, belge.dosya.stem, kabul)
    return SertifikaOkumasi(sertifika, "hibrit", model, ISTEM_SURUMU, sorted({s.sayfa for s in kabul}), kanitsiz)


def sertifika_hatti(
    katalog: Katalog,
    malzeme_kodu: str,
    pdf_yolu: str | Path,
    mod: str | None = None,
    istemci: SohbetIstemcisi | None = None,
    lot_no: str | None = None,
    defter: DenetimKaydi | None = None,
    kullanici: str | None = None,
    ayar: KararAyarlari | None = None,
) -> tuple[KatalogKarari, SertifikaOkumasi]:
    """Sertifika PDF'inden parti kararına kadar bütün hat."""
    secilen = mod_sec(mod)
    if secilen == "hibrit" and istemci is None:
        istemci = ortamdan_istemci()
    belge = pdf_oku(pdf_yolu)
    okuma = sertifikayi_oku(belge, secilen, istemci)
    ek = [d] if (d := okuma.kanit_denetimi()) is not None else []
    karar = malzeme_koduyla_kontrol(
        katalog, malzeme_kodu, okuma.sertifika, lot_no=lot_no, ayar=ayar, defter=defter, kullanici=kullanici,
        model=okuma.model if okuma.mod == "hibrit" and not okuma.yedek else None,
        istem_surumu=okuma.istem_surumu if okuma.mod == "hibrit" and not okuma.yedek else None,
        pdf_sayfasi=",".join(map(str, okuma.sayfalar)) or None,
        ek_denetimler=ek, hat_bilgisi=okuma.hat_bilgisi(),
    )
    return karar, okuma


# --- standart tarafı ------------------------------------------------------------------


@dataclass
class StandartOkumaDenetimi:
    kabul: list[HamOkuma] = field(default_factory=list)  # kanıtlı (yönü gerekirse 'belirsiz' yapılmış)
    reddedilen: list[tuple[HamOkuma, str]] = field(default_factory=list)  # kanıtsız
    yonu_belirsizlesen: list[tuple[HamOkuma, str]] = field(default_factory=list)


def standart_okumalarini_dogrula(okumalar: list[HamOkuma], belge: Belge) -> StandartOkumaDenetimi:
    """Standarttan okunan ham metinleri kanıt ve sınır yönü kuralından geçirir."""
    metinler = {s.no: s.metin for s in belge.sayfalar}
    sonuc = StandartOkumaDenetimi()
    for o in okumalar:
        k = okuma_kaniti(o, metinler)
        if not k.kanitli:
            sonuc.reddedilen.append((o, k.neden))
            continue
        y = okuma_yonu_dogrula(o)
        if y.durum == "celiski":
            o = o.model_copy(update={"sinir_yonu": "belirsiz"})
            sonuc.yonu_belirsizlesen.append((o, y.aciklama))
        sonuc.kabul.append(o)
    return sonuc


__all__ = [
    "HatHatasi",
    "MODLAR",
    "Mod",
    "SertifikaOkumasi",
    "StandartOkumaDenetimi",
    "mod_sec",
    "ortamdan_istemci",
    "sertifika_hatti",
    "sertifikayi_oku",
    "standart_okumalarini_dogrula",
]
