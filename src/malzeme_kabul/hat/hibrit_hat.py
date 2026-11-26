"""Belge → okuma → kanıt → kural → karar → kayıt hattı; mod anahtarıyla (docs/mimari.md madde 6).

İki mod:

- `kural`: sertifika PDF'i kural tabanlı okuyucuyla okunur
  (`cikarim.sertifika_okuyucu.kural_ile_oku`). Dil modeli çağrılmaz.
- `hibrit`: sertifikayı yerel dil modeli okur (yalnız localhost,
  `cikarim.yerel_model.YerelModelIstemcisi`); her okunan satır kanıt
  doğrulayıcıdan geçer (`kural.kanit_dogrulama.satir_kaniti`). Kanıtsız
  satırlar karara girmez; `kanit` denetimi insan incelemeli olur. Kabul/red
  kararını her iki modda da kural motoru verir.

Okuma anlaşmazlığı: hibritte model başarılıysa sertifika kural okuyucuyla da
okunur ve iki okuma (standart atfı ve modelin kanıtlı satırları)
`kural.okuma_karsilastirma` ile test bazında karşılaştırılır. Karara modelin
okuması girer; anlaşmazlıkta hiçbir okuma sessizce karara girmez: değer,
birim, satır ya da atıf farkı olan şart insan incelemeli olur ("kural ve
model farklı okudu: ..."; iki okuma da sınır dışındaysa uygun değil kalır),
`okuma_uyumu` ek denetimi insan incelemeli olur ve anlaşmazlıklar `hat.anlasmazliklar` olarak karar kaydına
yazılır (ileride güven skoru girdisi).

Dil modeli yanıt vermezse ya da şemaya uymayan yanıt dönerse hat kural
okumasına düşer ve bunu karar kaydına yazar (`hat.yedek`); karar yine
kurallarla verilir.

Standart tarafı: `standart_okumalarini_dogrula` dil modelinin standarttan
okuduğu `HamOkuma`'ları kanıt doğrulayıcı ve sınır yönü kuralından
(`kural.yon_dogrulama`) geçirir: kanıtsız okumalar reddedilir, yönü metinle
çelişen okumalar `belirsiz` yapılır (insan incelemesi). Kural dokümanı
verilirse modelin sınır ve yön okuması onunla karşılaştırılır; anlaşmayan
okumanın yönü de `belirsiz` yapılır.

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
from malzeme_kabul.cikarim.yerel_model import YEDEK_HATALARI, SohbetIstemcisi, YerelModelIstemcisi
from malzeme_kabul.hat.katalog_karari import KatalogKarari, malzeme_koduyla_kontrol
from malzeme_kabul.katalog.veritabani import Katalog
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi
from malzeme_kabul.kural.kanit_dogrulama import atif_kaniti, deger_kaniti, okuma_kaniti, satir_kaniti
from malzeme_kabul.kural.karar_motoru import KararAyarlari, KararSatiri
from malzeme_kabul.kural.okuma_karsilastirma import (
    Anlasmazlik,
    sertifika_okumalarini_karsilastir,
    standart_okumalarini_karsilastir,
)
from malzeme_kabul.kural.yon_dogrulama import okuma_yonu_dogrula
from malzeme_kabul.sozlesme.okuma import HamOkuma, SertifikaOkumaYaniti
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika

FARKLI_OKUDU = "kural ve model farklı okudu"

Mod = Literal["kural", "hibrit"]
MODLAR: tuple[str, ...] = ("kural", "hibrit")


class HatHatasi(ValueError):
    """Hat ayarı hatası (bilinmeyen mod, hibritte istemci yok...)."""


def mod_sec(mod: str | None = None) -> Mod:
    """Verilen mod; mod None ise MALZEME_KABUL_MODU, o da yoksa 'kural'.

    Açıkça verilen boş mod ("") hatadır: ortam değişkenine ya da 'kural'a
    sessizce düşülmez (retro H12).
    """
    if mod is None:
        mod = os.environ.get("MALZEME_KABUL_MODU") or "kural"
    secilen = mod.strip().casefold()
    if not secilen:
        raise HatHatasi(f"mod boş verildi ({', '.join(MODLAR)})")
    if secilen not in MODLAR:
        raise HatHatasi(f"bilinmeyen mod: {secilen!r} ({', '.join(MODLAR)})")
    return secilen  # type: ignore[return-value]


def ortamdan_istemci() -> YerelModelIstemcisi:
    """Ortam değişkenlerinden yerel model istemcisi kurar (yalnız localhost)."""
    model = os.environ.get("MALZEME_KABUL_MODELI")
    if not model:
        raise HatHatasi("hibrit mod için MALZEME_KABUL_MODELI ortam değişkeni gerekli")
    try:
        return YerelModelIstemcisi(
            model,
            arka_uc=os.environ.get("MALZEME_KABUL_ARKA_UCU", "ollama"),
            adres=os.environ.get("MALZEME_KABUL_MODEL_ADRESI") or None,
        )
    except ValueError as hata:  # yerel olmayan adres, bilinmeyen arka uç
        raise HatHatasi(str(hata)) from hata


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
    anlasmazliklar: list[Anlasmazlik] = field(default_factory=list)  # kural ve model okuması farkları
    kural_sertifikasi: Sertifika | None = None  # hibritte karşılaştırılan kural okuması; yoksa karşılaştırılmadı

    def kanit_denetimi(self) -> KararSatiri | None:
        ortak = {"test_id": "kanit", "test_adi": "Okuma kanıtı (dil modeli)"}
        if self.mod != "hibrit":
            return None
        if self.yedek:
            return KararSatiri(karar="uygun", gerekce=f"dil modeli kullanılamadı, kural okuması: {self.yedek}", **ortak)
        if self.kanitsiz:
            return KararSatiri(karar="insan_incelemeli", gerekce="belgede bulunamayan okumalar: " + "; ".join(self.kanitsiz), **ortak)
        if not self.sertifika.satirlar:
            return KararSatiri(karar="insan_incelemeli", gerekce="dil modeli hiçbir test satırı okumadı", **ortak)
        return KararSatiri(karar="uygun", gerekce="okunan bütün hücreler belgede bulundu", **ortak)

    def okuma_uyumu_denetimi(self) -> KararSatiri | None:
        """Hibritte (yedeğe düşülmediyse) kural ve model okumasının uyumu; aksi halde None."""
        if self.mod != "hibrit" or self.yedek:
            return None
        ortak = {"test_id": "okuma_uyumu", "test_adi": "Kural ve model okuma uyumu"}
        if self.kural_sertifikasi is None:
            return KararSatiri(karar="insan_incelemeli",
                               gerekce="karşılaştırma yapılamadı: kabul dokümanı verilmedi", **ortak)
        if self.anlasmazliklar:
            testler = sorted({a.test_id for a in self.anlasmazliklar})
            return KararSatiri(
                karar="insan_incelemeli",
                gerekce=f"{FARKLI_OKUDU}: {len(self.anlasmazliklar)} anlaşmazlık ({', '.join(testler)})",
                **ortak,
            )
        return KararSatiri(karar="uygun", gerekce="kural ve model aynı okudu", **ortak)

    def incelemeye_alinacak(self) -> dict[str, str]:
        """Anlaşmazlığı olan test_id → gerekçe ("kural ve model farklı okudu: ...")."""
        nedenler: dict[str, list[str]] = {}
        for a in self.anlasmazliklar:
            nedenler.setdefault(a.test_id, []).append(a.aciklama)
        return {t: f"{FARKLI_OKUDU}: " + "; ".join(n) for t, n in nedenler.items()}

    def hat_bilgisi(self) -> dict:
        return {"mod": self.mod, "model": self.model, "istem_surumu": self.istem_surumu,
                "kanitsiz": self.kanitsiz, "yedek": self.yedek,
                "anlasmazliklar": [a.model_dump() for a in self.anlasmazliklar],
                "anlasmazlik_sayisi": len(self.anlasmazliklar)}


_UST_ALANLAR = {"tedarikci": "tedarikçi", "sertifika_no": "sertifika no", "parti_no": "parti no",
                "uretim_tarihi": "üretim tarihi"}


def _ust_bilgileri_dogrula(okuma: SertifikaOkumaYaniti, metinler: dict[int, str],
                           kanitsiz: list[str]) -> SertifikaOkumaYaniti:
    """Modelin okuduğu üst bilgileri ve standart atfını belgede arar (retro H5, H6).

    Belgede (sınırla; atıfta tam olarak) bulunmayan alan boşaltılır ve
    `kanitsiz`'e yazılır; boş alan karara girmez, ilgili denetim insan
    incelemesine gider (ör. tedarikçi yoksa `tedarikci` denetimi).
    """
    bosalt: dict[str, None] = {}
    for alan, ad in _UST_ALANLAR.items():
        deger = getattr(okuma, alan)
        if deger and not (k := deger_kaniti(deger, metinler, alan=alan)).kanitli:
            kanitsiz.append(f"{ad}: {k.neden}")
            bosalt[alan] = None
    atif = okuma.standart_atfi
    if atif and not (k := atif_kaniti(atif, metinler)).kanitli:
        kanitsiz.append(f"standart atfı: {k.neden}")
        bosalt["standart_atfi"] = None
    return okuma.model_copy(update=bosalt) if bosalt else okuma


def _model_adi(istemci: SohbetIstemcisi) -> str:
    return getattr(istemci, "model", None) or type(istemci).__name__


def sertifikayi_oku(
    belge: Belge,
    mod: Mod,
    istemci: SohbetIstemcisi | None = None,
    dokuman: KabulDokumani | None = None,
    tip: str | None = None,
    sinif: str | None = None,
) -> SertifikaOkumasi:
    """Sertifikayı seçilen modda okur; hibritte her satırı kanıtla doğrular.

    Hibritte model başarılı ve `dokuman` (kabul dokümanı) verilmişse sertifika
    kural okuyucuyla da okunur; modelin kanıtlı satırlarıyla farkları
    `anlasmazliklar` alanına yazılır (`tip`/`sinif`: katalogdaki malzemenin).
    Doküman verilmezse karşılaştırma yapılmaz ve `okuma_uyumu` insan
    incelemeli olur.
    """
    if mod == "kural":
        return SertifikaOkumasi(kural_ile_oku(belge), "kural", sayfalar=[s.no for s in belge.sayfalar])
    if istemci is None:
        raise HatHatasi("hibrit mod için yerel model istemcisi gerekli")
    model = _model_adi(istemci)
    try:
        okuma = dil_modeli_ile_oku(belge, istemci)
    except YEDEK_HATALARI as hata:
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
    okuma = _ust_bilgileri_dogrula(okuma, metinler, kanitsiz)
    sertifika = okumadan_sertifika(okuma, belge.dosya.stem, kabul)
    kural_sertifikasi, anlasmazliklar = None, []
    if dokuman is not None:
        kural_sertifikasi = kural_ile_oku(belge)
        anlasmazliklar = sertifika_okumalarini_karsilastir(dokuman, kural_sertifikasi, sertifika, tip, sinif)
    return SertifikaOkumasi(sertifika, "hibrit", model, ISTEM_SURUMU, sorted({s.sayfa for s in kabul}), kanitsiz,
                            anlasmazliklar=anlasmazliklar, kural_sertifikasi=kural_sertifikasi)


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
    dokuman = katalog.gecerli_dokuman(malzeme_kodu).dokuman
    malzeme = katalog.malzeme(malzeme_kodu)
    okuma = sertifikayi_oku(belge, secilen, istemci, dokuman, malzeme.tip, malzeme.sinif)
    ek = [d for d in (okuma.kanit_denetimi(), okuma.okuma_uyumu_denetimi()) if d is not None]
    karar = malzeme_koduyla_kontrol(
        katalog, malzeme_kodu, okuma.sertifika, lot_no=lot_no, ayar=ayar, defter=defter, kullanici=kullanici,
        model=okuma.model if okuma.mod == "hibrit" and not okuma.yedek else None,
        istem_surumu=okuma.istem_surumu if okuma.mod == "hibrit" and not okuma.yedek else None,
        pdf_sayfasi=",".join(map(str, okuma.sayfalar)) or None,
        ek_denetimler=ek, hat_bilgisi=okuma.hat_bilgisi(),
        incelemeye_alinacak=okuma.incelemeye_alinacak() or None, karsi_okuma=okuma.kural_sertifikasi,
    )
    return karar, okuma


# --- standart tarafı ------------------------------------------------------------------


@dataclass
class StandartOkumaDenetimi:
    kabul: list[HamOkuma] = field(default_factory=list)  # kanıtlı (yönü gerekirse 'belirsiz' yapılmış)
    reddedilen: list[tuple[HamOkuma, str]] = field(default_factory=list)  # kanıtsız
    yonu_belirsizlesen: list[tuple[HamOkuma, str]] = field(default_factory=list)
    anlasmazliklar: list[Anlasmazlik] = field(default_factory=list)  # kural dokümanıyla farklar


def standart_okumalarini_dogrula(
    okumalar: list[HamOkuma], belge: Belge, kural_dokumani: KabulDokumani | None = None
) -> StandartOkumaDenetimi:
    """Standarttan okunan ham metinleri kanıt ve sınır yönü kuralından geçirir.

    `kural_dokumani` (kural çıkarıcının dokümanı) verilirse kanıtlı her sınır
    okuması onunla karşılaştırılır; sınırı ya da yönü farklı olan okumanın
    yönü `belirsiz` yapılır (insan incelemesi) ve fark `anlasmazliklar`'a yazılır.
    """
    metinler = {s.no: s.metin for s in belge.sayfalar}
    sonuc = StandartOkumaDenetimi()
    for o in okumalar:
        k = okuma_kaniti(o, metinler)
        if not k.kanitli:
            sonuc.reddedilen.append((o, k.neden))
            continue
        farklar = standart_okumalarini_karsilastir([o], kural_dokumani) if kural_dokumani is not None else []
        y = okuma_yonu_dogrula(o)
        if y.durum == "celiski":
            o = o.model_copy(update={"sinir_yonu": "belirsiz"})
            sonuc.yonu_belirsizlesen.append((o, y.aciklama))
        elif farklar:
            o = o.model_copy(update={"sinir_yonu": "belirsiz"})
            sonuc.yonu_belirsizlesen.append((o, f"{FARKLI_OKUDU}: " + "; ".join(a.aciklama for a in farklar)))
        sonuc.anlasmazliklar.extend(farklar)
        sonuc.kabul.append(o)
    sonuc.anlasmazliklar.sort(key=lambda a: (a.test_id, a.alan))
    return sonuc


__all__ = [
    "FARKLI_OKUDU",
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
