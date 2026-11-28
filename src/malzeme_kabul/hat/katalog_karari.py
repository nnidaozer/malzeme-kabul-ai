"""Katalogdan kabul dokümanı alıp sertifikaya karar veren hat (docs/mimari.md madde 2 ve 5).

Akış: malzeme kodu → katalogdaki en son onaylı kabul dokümanı sürümü ve
tip/sınıf → `kural.karar_motoru.kontrol_et` → parti kararı → (lot verilmişse)
katalogdaki parti durumu.

Kabul dokümanı dosyadan okunmaz; yalnız katalogdan, malzeme koduna göre gelir.

Kararı kural katmanı verir; bu modül yalnız bağlar. Katalogdan gelen iki ek
denetim de kesin kuraldır ve emin olunmayanı insana bırakır:

- `tedarikci`: sertifikadaki tedarikçi o malzeme için onaylı listede yoksa
  ya da sertifikada tedarikçi yoksa insan incelemeli (ad yazımı farklı
  olabilir; reddetmek yerine insana).
- `siparis_revizyonu`: partinin siparişteki revizyonu malzemenin kabul
  dokümanı revizyonundan farklıysa insan incelemeli.
- `parti_no` (lot verilmişse): sertifikadaki parti numarası yoksa ya da lotla
  tutmuyorsa insan incelemeli.
- `parti_tedarikcisi` (lot verilmişse): sertifikadaki tedarikçi partinin
  katalogdaki tedarikçisi değilse (başka bir onaylı firma olsa bile) insan
  incelemeli.

Parti kararı katalog durumuna şöyle yansır: kabul → serbest, red → karantina,
inceleme → bekliyor. Makine partiyi yalnız daha kısıtlayıcı bir duruma
geçirebilir (serbest < bekliyor < karantina). Tek istisna hiç karar verilmemiş
yeni partidir. Karantinadaki ya da daha önce karar verilmiş (makine ya da
insan) bekleyen partiyi makine serbest bırakmaz; durum korunur ve
`parti_durumu` ek denetimi insan incelemeli olur, gerekçesinde partinin neden
o durumda kaldığı yazar. Serbest bırakmak `karari_duzelt` ile insanın işidir;
karantinadan çıkarmayı yalnız M&P (rol 'mp') gerekçeyle yapar.

Kabul dokümanı sürümü örnek verinin demo onayıyla onaylıysa karar
`demo_onayi=True` taşır (ekranda ve kayıtta işaretlenir); karar mantığı değişmez.

Denetim kaydı (`kayit.denetim_kaydi`) verilirse her karar, onay ve düzeltme
zincire yazılır: kullanıcı, zaman, doküman sürümü, PDF sayfası, model ve
istem sürümü. Durum değişikliği ile onun kaydı tek işlemdir (`Katalog.islem`):
kayıt yazılamazsa durum da değişmez. Bunun için defter katalogla aynı SQLite
bağlantısını paylaşmalıdır. Parti durumu yazan karar (lot verilmiş,
`durumu_yaz` açık) defter olmadan verilmez.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from malzeme_kabul.katalog.veritabani import (
    DokumanSurumu,
    Katalog,
    KatalogHatasi,
    Parti,
    PartiDurumu,
    ROLLER,
)
from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi, Kayit
from malzeme_kabul.kural.karar_motoru import (
    BelgeKarari,
    Karar,
    KararAyarlari,
    KararSatiri,
    KontrolSonucu,
    kontrol_et,
    parti_karari,
)
from malzeme_kabul.kural.okuma_karsilastirma import anlasmazlik_karari
from malzeme_kabul.sozlesme.sema import KabulDokumani
from malzeme_kabul.sozlesme.sertifika import Sertifika

PARTI_DURUMU: dict[str, PartiDurumu] = {"kabul": "serbest", "red": "karantina", "inceleme": "bekliyor"}


class KatalogKarari(BaseModel):
    """Katalogla verilen kararın tamamı."""

    model_config = ConfigDict(extra="forbid")

    malzeme_kodu: str
    lot_no: str | None
    dokuman_surumu: str  # ör. "MIL-PRF-23377K v2"
    dokuman_ozeti: str
    kontrol: KontrolSonucu
    ek_denetimler: list[KararSatiri]
    parti_karari: BelgeKarari
    parti_durumu: PartiDurumu
    hat: dict | None = None  # okuma modu, model, istem sürümü, kanıtsız okumalar
    demo_onayi: bool = False  # kabul dokümanı sürümü örnek verinin demo onayıyla mı (M&P onayı değil)


def _ad(metin: str) -> str:
    return " ".join(metin.split()).casefold()


def _tedarikci_denetimi(katalog: Katalog, malzeme_kodu: str, sertifika: Sertifika) -> KararSatiri:
    onayli = katalog.onayli_tedarikciler(malzeme_kodu)
    ortak = {"test_id": "tedarikci", "test_adi": "Onaylı tedarikçi"}
    if not (sertifika.tedarikci and sertifika.tedarikci.strip()):
        return KararSatiri(karar="insan_incelemeli", gerekce="sertifikada tedarikçi yok", **ortak)
    if _ad(sertifika.tedarikci) in {_ad(t) for t in onayli}:
        return KararSatiri(karar="uygun", gerekce=f"{sertifika.tedarikci} onaylı listede", **ortak)
    return KararSatiri(
        karar="insan_incelemeli",
        gerekce=f"sertifikadaki tedarikçi {sertifika.tedarikci!r} onaylı listede yok ({', '.join(onayli) or '-'})",
        **ortak,
    )


def _parti_denetimleri(parti: Parti, sertifika: Sertifika) -> list[KararSatiri]:
    """Sertifikanın bu partiye ait olduğunu denetler: parti numarası ve partinin tedarikçisi (K3)."""
    satirlar = []
    ortak = {"test_id": "parti_no", "test_adi": "Parti numarası"}
    if not (sertifika.parti_no and sertifika.parti_no.strip()):
        satirlar.append(KararSatiri(karar="insan_incelemeli", gerekce=f"sertifikada parti numarası yok (lot {parti.lot_no})", **ortak))
    elif _ad(sertifika.parti_no) != _ad(parti.lot_no):
        satirlar.append(KararSatiri(
            karar="insan_incelemeli",
            gerekce=f"sertifikadaki parti numarası {sertifika.parti_no!r}, lot {parti.lot_no!r}",
            **ortak,
        ))
    else:
        satirlar.append(KararSatiri(karar="uygun", gerekce=f"parti numarası {parti.lot_no}", **ortak))

    ortak = {"test_id": "parti_tedarikcisi", "test_adi": "Partinin tedarikçisi"}
    if not (sertifika.tedarikci and sertifika.tedarikci.strip()):
        satirlar.append(KararSatiri(karar="insan_incelemeli", gerekce="sertifikada tedarikçi yok", **ortak))
    elif _ad(sertifika.tedarikci) != _ad(parti.tedarikci):
        satirlar.append(KararSatiri(
            karar="insan_incelemeli",
            gerekce=f"sertifikadaki tedarikçi {sertifika.tedarikci!r}, partinin tedarikçisi {parti.tedarikci!r}",
            **ortak,
        ))
    else:
        satirlar.append(KararSatiri(karar="uygun", gerekce=f"partinin tedarikçisi {parti.tedarikci}", **ortak))
    return satirlar


# Kısıtlayıcılık sırası: makine yalnız aynı ya da daha yüksek sıraya geçirebilir.
_KISITLAMA: dict[str, int] = {"serbest": 0, "bekliyor": 1, "karantina": 2}
_KAYNAK_METNI = {
    None: "kayıt sırasında verildi",
    "insan": "insan kararıyla",
    "makine": "önceki makine kararıyla",
    "bilinmiyor": "kaynağı bilinmiyor",
}


def _makine_gecebilir_mi(parti: Parti, istenen: PartiDurumu) -> bool:
    """Makine kararı partiyi `istenen` duruma geçirebilir mi?

    Daha kısıtlayıcı ya da aynı duruma her zaman; daha serbest duruma yalnız hiç
    karar verilmemiş, bekleyen yeni parti için (ilk karar).
    """
    if _KISITLAMA[istenen] >= _KISITLAMA[parti.durum]:
        return True
    return parti.durum == "bekliyor" and not parti.karar_verildi


def _parti_durumu_satiri(parti: Parti, istenen: PartiDurumu) -> KararSatiri:
    return KararSatiri(
        test_id="parti_durumu", test_adi="Parti durumu", karar="insan_incelemeli",
        gerekce=(
            f"parti katalogda {parti.durum} ({_KAYNAK_METNI.get(parti.durum_kaynagi, parti.durum_kaynagi)}); "
            f"makine kararı {istenen} olurdu ama makine partiyi {parti.durum} durumundan çıkaramaz, "
            "serbest bırakmayı M&P yapar"
        ),
    )


def malzeme_koduyla_kontrol(
    katalog: Katalog,
    malzeme_kodu: str,
    sertifika: Sertifika,
    lot_no: str | None = None,
    ayar: KararAyarlari | None = None,
    durumu_yaz: bool = True,
    defter: DenetimKaydi | None = None,
    kullanici: str | None = None,
    model: str | None = None,
    istem_surumu: str | None = None,
    pdf_sayfasi: str | int | None = None,
    ek_denetimler: list[KararSatiri] | None = None,
    hat_bilgisi: dict | None = None,
    incelemeye_alinacak: dict[str, str] | None = None,
    karsi_okuma: Sertifika | None = None,
    bekletme_nedeni: str | None = None,
) -> KatalogKarari:
    """Sertifikayı malzeme kodunun onaylı kabul dokümanıyla karşılaştırır.

    `lot_no` verilir ve parti katalogda varsa, `durumu_yaz` ise parti durumu
    karara göre güncellenir; bunun için `defter` zorunludur (yoksa
    KatalogHatasi, hiçbir şey yazılmaz). Durum ve karar kaydı tek işlemdir.
    `defter` verilirse karar denetim kaydına yazılır
    (`kullanici` zorunlu); `model` ve `istem_surumu` dil modeli kullanıldıysa,
    `pdf_sayfasi` sertifikanın okunduğu sayfa(lar).

    `incelemeye_alinacak` ({test_id: gerekçe}) verilirse o testlerin kontrol
    satırı (standart atfı için `revizyon` satırı) insan incelemeli olur;
    gerekçe mevcut gerekçenin sonuna eklenir. `karsi_okuma` (hibritte kural
    okuması) da verilmişse o okuma da kural motoruyla değerlendirilir ve iki
    okuma da uygun değilse satır uygun değil kalır
    (`okuma_karsilastirma.anlasmazlik_karari`). Kontrol satırlarında olmayan
    test için insan incelemeli bir ek denetim satırı eklenir.

    `bekletme_nedeni` verilirse (ör. hibritte dil modeli yanıt vermedi) kontrol
    satırlarından (revizyon, satırlar, tip/sınıf) uygun ya da uygun değil
    olanlar insan incelemeli olur; gerekçeye neden, "yalnız kural okumasıyla
    karar verilmez" ve kuralın kendi kararı eklenir. Eksik bilgi uygun
    sonucuna yol açmaz: parti kararı inceleme olur.
    """
    if defter is not None and not (isinstance(kullanici, str) and kullanici.strip()):
        raise KatalogHatasi("denetim kaydı için kullanıcı gerekli")
    if defter is not None:
        _ayni_baglanti(katalog, defter)
    malzeme = katalog.malzeme(malzeme_kodu)
    surum = katalog.gecerli_dokuman(malzeme_kodu)
    kontrol = kontrol_et(surum.dokuman, sertifika, ayar, tip=malzeme.tip, sinif=malzeme.sinif, katalogdan=True)

    ek: list[KararSatiri] = list(ek_denetimler or [])
    if incelemeye_alinacak:
        karsi = (
            kontrol_et(surum.dokuman, karsi_okuma, ayar, tip=malzeme.tip, sinif=malzeme.sinif, katalogdan=True)
            if karsi_okuma is not None else None
        )
        kontrol, eksik = _incelemeye_al(kontrol, incelemeye_alinacak, karsi)
        adlar = {t.id: t.test_adi for t in surum.dokuman.testler}
        ek.extend(
            KararSatiri(test_id=t, test_adi=adlar.get(t, t), karar="insan_incelemeli", gerekce=g)
            for t, g in eksik.items()
        )
    if bekletme_nedeni:
        kontrol = _bekletmeye_al(kontrol, bekletme_nedeni)
    ek.append(_tedarikci_denetimi(katalog, malzeme_kodu, sertifika))
    # Parti okuması, geçiş kararı, durum yazımı ve kayıt tek IMMEDIATE işlemdir (K2 yarışı):
    # okunan durum, yazılana kadar başka bir bağlantı tarafından değiştirilemez.
    with katalog.islem():
        parti = None
        if lot_no is not None:
            parti = katalog.parti(malzeme_kodu, lot_no)
            if durumu_yaz and defter is None:  # denetim B5: denetimsiz durum değişimi olmaz
                raise KatalogHatasi("parti durumu yazan karar denetim kaydı (defter) olmadan verilemez")
            ortak = {"test_id": "siparis_revizyonu", "test_adi": "Sipariş revizyonu"}
            if parti.siparis_revizyonu != malzeme.revizyon:
                ek.append(KararSatiri(
                    karar="insan_incelemeli",
                    gerekce=f"sipariş revizyonu {parti.siparis_revizyonu}, kabul dokümanı {malzeme.standart_etiketi}",
                    **ortak,
                ))
            else:
                ek.append(KararSatiri(karar="uygun", gerekce=f"sipariş revizyonu {parti.siparis_revizyonu}", **ortak))
            ek.extend(_parti_denetimleri(parti, sertifika))

        karar = parti_karari(_satir_kararlari(kontrol) + [s.karar for s in ek])
        durum = PARTI_DURUMU[karar]
        yazilacak = False
        if parti is not None:
            if _makine_gecebilir_mi(parti, durum):
                yazilacak = durumu_yaz
            else:
                ek.append(_parti_durumu_satiri(parti, durum))
                karar = parti_karari(_satir_kararlari(kontrol) + [s.karar for s in ek])
                durum = parti.durum
        sonuc = KatalogKarari(
            malzeme_kodu=malzeme_kodu,
            lot_no=lot_no,
            dokuman_surumu=surum.etiket,
            dokuman_ozeti=surum.ozet,
            kontrol=kontrol,
            ek_denetimler=ek,
            parti_karari=karar,
            parti_durumu=durum,
            hat=hat_bilgisi,
            demo_onayi=surum.demo_onayi,
        )
        if yazilacak:
            katalog.parti_durumu_ata(malzeme_kodu, parti.lot_no, durum, kaynak="makine")
        if defter is not None:
            defter.ekle(
                "karar", kullanici, sonuc.model_dump(mode="json"),
                malzeme_kodu=malzeme_kodu, lot_no=lot_no, dokuman_surumu=surum.etiket,
                pdf_sayfasi=pdf_sayfasi, model=model, istem_surumu=istem_surumu,
            )
    return sonuc


def dokuman_onayla(
    katalog: Katalog, defter: DenetimKaydi, dokuman: KabulDokumani, kullanici: str, not_: str | None = None
) -> DokumanSurumu:
    """Kabul dokümanını yeni onaylı sürüm olarak kaydeder ve onayı denetim kaydına yazar (tek işlem)."""
    _ayni_baglanti(katalog, defter)
    with katalog.islem():
        surum = katalog.dokuman_onayla(dokuman, kullanici, not_)
        defter.ekle(
            "onay", kullanici, {"dokuman_surumu": surum.etiket, "ozet": surum.ozet, "not": not_},
            dokuman_surumu=surum.etiket,
        )
    return surum


def karari_duzelt(
    katalog: Katalog,
    defter: DenetimKaydi,
    kullanici: str,
    malzeme_kodu: str,
    lot_no: str,
    yeni_durum: PartiDurumu,
    neden: str,
    *,
    rol: str,
) -> Kayit:
    """İnsanın parti kararını düzeltmesi: parti durumu değişir, eski ve yeni durum gerekçesiyle kaydedilir.

    `rol` zorunludur ve `ROLLER` içinde olmalıdır ('mp', 'giris_kalite').
    Kullanıcı, gerekçe ve rol hiçbir şey yazılmadan doğrulanır; durum ve kayıt
    tek işlemdir. Bağlantıda kullanıcı tablosu varsa kullanıcı orada aynı rolle
    kayıtlı olmalıdır (yoksa verilen rol kullanılır). Karantinadaki partiyi
    karantinadan çıkarmak (kaynağı makine ya da insan) yalnız M&P'nin işidir ve
    gerekçe ister.
    """
    if not isinstance(kullanici, str) or not kullanici.strip():
        raise KatalogHatasi("düzeltme için kullanıcı gerekli")
    if not isinstance(neden, str) or not neden.strip():
        raise KatalogHatasi("düzeltme için gerekçe gerekli")
    if not isinstance(rol, str) or rol not in ROLLER:
        raise KatalogHatasi(f"bilinmeyen rol: {rol!r} ({', '.join(ROLLER)})")
    _ayni_baglanti(katalog, defter)
    with katalog.islem():  # onceki_durum yazma işleminin içinde okunur (K2 yarışı)
        _rolu_dogrula(katalog, kullanici, rol)
        onceki = katalog.parti(malzeme_kodu, lot_no).durum
        if onceki == "karantina" and yeni_durum != "karantina" and rol != "mp":
            raise KatalogHatasi("karantinadaki partiyi yalnız M&P gerekçeyle karantinadan çıkarabilir")
        surum = katalog.gecerli_dokuman(malzeme_kodu).etiket
        katalog.parti_durumu_ata(malzeme_kodu, lot_no, yeni_durum, kaynak="insan")
        return defter.ekle(
            "duzeltme", kullanici,
            {"onceki_durum": onceki, "yeni_durum": yeni_durum, "neden": neden, "rol": rol},
            malzeme_kodu=malzeme_kodu, lot_no=lot_no, dokuman_surumu=surum,
        )


def _rolu_dogrula(katalog: Katalog, kullanici: str, rol: str) -> None:
    """Bağlantıda kullanıcı tablosu (`kullanicilar`, arayuz.kimlik) varsa kullanıcı orada aynı rolle kayıtlı olmalı.

    Tablo yoksa (ör. yalnız komut satırı) verilen rol kullanılır. Tablo
    doğrudan sorgulanır; hat arayüz katmanını içe aktarmaz.
    """
    b = katalog.baglanti
    if b.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'kullanicilar'").fetchone() is None:
        return
    s = b.execute("SELECT rol FROM kullanicilar WHERE ad = ?", (kullanici,)).fetchone()
    if s is None:
        raise KatalogHatasi(f"kullanıcı {kullanici!r} kullanıcı tablosunda kayıtlı değil")
    if s[0] != rol:
        raise KatalogHatasi(f"kullanıcı {kullanici!r} kayıtta {s[0]!r} rolünde; verilen rol {rol!r} tutmuyor")


def _ayni_baglanti(katalog: Katalog, defter: DenetimKaydi) -> None:
    """Durum ve kaydın tek işlem olabilmesi için defter katalogla aynı bağlantıyı paylaşmalı."""
    if defter.baglanti is not katalog.baglanti:
        raise KatalogHatasi("denetim kaydı katalogla aynı bağlantıyı paylaşmalı (durum ve kayıt tek işlem)")


def _incelemeye_al(
    kontrol: KontrolSonucu, nedenler: dict[str, str], karsi: KontrolSonucu | None = None
) -> tuple[KontrolSonucu, dict[str, str]]:
    """Anlaşmazlığı olan satırların kararını yeniden verir; kontrolde bulunmayanları ayrıca döner.

    `karsi` öteki okumanın kontrolüdür; verilmezse karar insan incelemelidir.
    """
    karsi_kararlar: dict[str, Karar] = {}
    if karsi is not None:
        karsi_kararlar = {s.test_id: s.karar for s in [karsi.revizyon, *karsi.satirlar]}

    def guncelle(s: KararSatiri) -> KararSatiri:
        if s.test_id not in nedenler:
            return s
        karar = anlasmazlik_karari(s.karar, karsi_kararlar.get(s.test_id))
        return s.model_copy(update={"karar": karar, "gerekce": f"{s.gerekce}; {nedenler[s.test_id]}"})

    yeni = kontrol.model_copy(update={"revizyon": guncelle(kontrol.revizyon),
                                      "satirlar": [guncelle(s) for s in kontrol.satirlar]})
    yeni = yeni.model_copy(update={"belge_karari": parti_karari(_satir_kararlari(yeni))})
    bulunan = {kontrol.revizyon.test_id} | {s.test_id for s in kontrol.satirlar}
    return yeni, {t: g for t, g in nedenler.items() if t not in bulunan}


def _bekletmeye_al(kontrol: KontrolSonucu, neden: str) -> KontrolSonucu:
    """Kesin kararlı (uygun / uygun değil) kontrol satırlarını insan incelemesine alır."""

    def beklet(s: KararSatiri) -> KararSatiri:
        if s.karar not in ("uygun", "uygun_degil"):
            return s
        gerekce = f"{s.gerekce}; {neden}: yalnız kural okumasıyla karar verilmez (kural okumasına göre: {s.karar})"
        return s.model_copy(update={"karar": "insan_incelemeli", "gerekce": gerekce})

    guncel: dict = {"revizyon": beklet(kontrol.revizyon), "satirlar": [beklet(s) for s in kontrol.satirlar]}
    if kontrol.tip_sinif is not None:
        guncel["tip_sinif"] = beklet(kontrol.tip_sinif)
    yeni = kontrol.model_copy(update=guncel)
    return yeni.model_copy(update={"belge_karari": parti_karari(_satir_kararlari(yeni))})


def _satir_kararlari(kontrol: KontrolSonucu) -> list[Karar]:
    kararlar = [kontrol.revizyon.karar] + [s.karar for s in kontrol.satirlar]
    if kontrol.tip_sinif is not None:
        kararlar.append(kontrol.tip_sinif.karar)
    return kararlar


__all__ = ["KatalogKarari", "PARTI_DURUMU", "dokuman_onayla", "karari_duzelt", "malzeme_koduyla_kontrol"]
