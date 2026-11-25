"""Deney: "yalnız dil modeli" çıkarıcısı (ürünün parçası değildir).

Bu modül yalnız deney/ altından çalıştırılır (docs/mimari.md madde 6). Model
her sayfa için doğrudan `TestSarti` şemasına zorlanmış JSON döner; sınırları,
birimleri ve yönü model yazar. Hibrit yaklaşımın karşılaştırıldığı iki taban
çizgisinden biridir (öteki yalnız kural: `malzeme_kabul.cikarim.kural_cikarici`).

Ürünün içinde dil modeli yalnız ham metin, kaynak konum ve sınır yönü döndürür
(`malzeme_kabul.sozlesme.okuma.HamOkuma`); normalleştirme ve birim dönüşümü
kurallarda yapılır. Bu deney bu sınırı bilerek aşar ve bu yüzden src/ dışında
durur.

Çözülen şartlar Pydantic ile doğrulanır; geçmeyenler atılır ve rapora
yazılır. İsteğe bağlı ara kayıt klasörüne her sayfanın sonucu ayrı bir JSON
dosyası olarak (atomik) yazılır; çalışma yarıda kalırsa (ör. Colab oturumu
koparsa) yeniden çalıştırmada kaydı olan sayfalar modele gönderilmez. İstemci `malzeme_kabul.cikarim.yerel_model.YerelModelIstemcisi`
olup yalnızca localhost'a bağlanır.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from malzeme_kabul.belge.pdf_okuyucu import Belge
from malzeme_kabul.cikarim.kural_cikarici import metni_normallestir
from malzeme_kabul.cikarim.yerel_model import Mesaj, SohbetIstemcisi
from malzeme_kabul.kural.yon_dogrulama import yonu_guvenli_yap
from malzeme_kabul.sozlesme.sema import KabulDokumani, StandartBilgisi, TestSarti


# --- Şema ve istem ----------------------------------------------------------------


class CikarimYaniti(BaseModel):
    """Modelin bir sayfa için döndüğü yanıt: o sayfadaki test şartları."""

    model_config = ConfigDict(extra="forbid")

    testler: list[TestSarti]


def cikarim_semasi() -> dict[str, Any]:
    """Modelin çıktısını zorlayan JSON şeması (`CikarimYaniti`)."""
    return CikarimYaniti.model_json_schema()


_SISTEM = """Sen bir askeri malzeme standardından test şartlarını okuyan bir yardımcısın.
Görevin yalnızca okumak: sayfada yazan test adını, test metodunu, sınır değerlerini,
birimi ve madde numarasını olduğu gibi aktar.

Kurallar:
- Birimi dönüştürme, değerleri hesaplama ya da karşılaştırma yapma. Sayıyı sayfada
  yazdığı gibi, birimi pint biçiminde yaz (ör. "s", "minute", "hour", "°C", "g/L",
  "%", "ppm", "mil", "µm").
- "en az" yalnız alt sınır, "en çok"/"not greater than" yalnız üst sınırdır.
  Sayısal sınır yoksa kriter_turu "gecti_kaldi" ya da "metinsel" olur ve alt, ust,
  birim boş kalır.
- orijinal_metin alanına standarttaki kriter cümlesini aynen yaz.
- kaynak.madde, şartın yazdığı madde numarasıdır (ör. "3.6.3" ya da "TABLE I").
- test_turleri: her partide yapılan kabul (conformance) testi "kabul", yalnız
  yeterlilikte yapılan "yeterlilik", raf ömrü uzatma testi "omur_uzatma".
- id: test adından küçük harf, alt çizgili kısa ad (ör. "viscosity").
- Sayfada test şartı yoksa boş liste dön: {"testler": []}.
- Uydurma; sayfada olmayan bir şeyi yazma."""


def istem_olustur(sayfa_metni: str, sayfa_no: int, belge_no: str, revizyon: str) -> list[Mesaj]:
    """Bir sayfa için sistem ve kullanıcı mesajlarını kurar."""
    sema = json.dumps(cikarim_semasi(), ensure_ascii=False)
    kullanici = (
        f"Belge: {belge_no}, revizyon \"{revizyon}\". Aşağıdaki metin PDF'in sayfa {sayfa_no}. "
        f"Her şartın kaynağında belge_no=\"{belge_no}\", revizyon=\"{revizyon}\", sayfa={sayfa_no} yaz.\n\n"
        f"JSON şeması:\n{sema}\n\n"
        f"--- SAYFA {sayfa_no} ---\n{sayfa_metni}\n--- SAYFA SONU ---"
    )
    return [{"role": "system", "content": _SISTEM}, {"role": "user", "content": kullanici}]


# --- Yanıtı çözme -----------------------------------------------------------------


def _ilk_hata(hata: ValidationError) -> str:
    e = hata.errors()[0]
    yer = ".".join(str(p) for p in e["loc"])
    return f"{yer}: {e['msg']}" if yer else e["msg"]


def yaniti_coz(metin: str) -> tuple[list[TestSarti], list[str]]:
    """Model yanıtını test şartlarına çözer.

    Geçerli şartlar ve her geçersiz şart (ya da çözülemeyen yanıt) için bir
    hata açıklaması döner. Bir şartın geçersiz olması diğerlerini düşürmez.
    """
    try:
        veri = json.loads(metin)
    except json.JSONDecodeError as hata:
        return [], [f"JSON çözülemedi: {hata.msg} (konum {hata.pos})"]
    if not isinstance(veri, dict) or not isinstance(veri.get("testler"), list):
        return [], ["yanıtta 'testler' listesi yok"]

    testler: list[TestSarti] = []
    hatalar: list[str] = []
    for i, ham in enumerate(veri["testler"]):
        try:
            testler.append(TestSarti.model_validate(ham))
        except ValidationError as hata:
            ad = ham.get("id") if isinstance(ham, dict) else None
            hatalar.append(f"test {i} ({ad or '?'}): {_ilk_hata(hata)}")
    return testler, hatalar


# --- Ara kayıt -----------------------------------------------------------------------


def ara_kayit_parmak_izi(istemci: Any = None) -> str:
    """Ara kaydın hangi ayarlarla üretildiğini gösteren sha256 (hex).

    Model adı, arka uç, düşünme ayarı, bağlam (istemcide varsa), sistem istemi ve
    çıkarım şemasından türetilir; biri değişirse eski ara kayıtlar kullanılmaz.
    """
    veri = {
        ad: getattr(istemci, ad, None) for ad in ("model", "arka_uc", "dusunme", "baglam")
    }
    veri["sistem_istemi"] = _SISTEM
    veri["sema"] = cikarim_semasi()
    metin = json.dumps(veri, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def _ara_kayit_yolu(klasor: Path | str, sayfa_no: int) -> Path:
    return Path(klasor) / f"sayfa_{sayfa_no:03d}.json"


def _ara_kaydi_yaz(
    klasor: Path | str, sayfa_no: int, sure_s: float, testler: list[TestSarti], hatalar: list[str],
    parmak_izi: str,
) -> Path:
    """Sayfa sonucunu geçici dosyaya yazıp `os.replace` ile yerine koyar (yarım dosya kalmaz)."""
    hedef = _ara_kayit_yolu(klasor, sayfa_no)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    veri = {
        "sayfa": sayfa_no,
        "sure_s": float(sure_s),
        "testler": [t.model_dump(mode="json") for t in testler],
        "hatalar": list(hatalar),
        "parmak_izi": parmak_izi,
    }
    gecici = hedef.with_name(f".{hedef.name}.{os.getpid()}.tmp")
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, hedef)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise
    return hedef


def _ara_kaydi_oku(
    klasor: Path | str, sayfa_no: int, parmak_izi: str
) -> tuple[list[TestSarti], list[str], float] | None:
    """Sayfanın ara kaydını okur: (testler, hatalar, süre). Yoksa, bozuksa ya da parmak izi farklıysa None."""
    yol = _ara_kayit_yolu(klasor, sayfa_no)
    if not yol.is_file():
        return None
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        if not isinstance(veri, dict) or veri.get("sayfa") != sayfa_no or veri.get("parmak_izi") != parmak_izi:
            return None
        testler = [TestSarti.model_validate(t) for t in veri["testler"]]
        hatalar = [str(h) for h in veri["hatalar"]]
        sure = float(veri["sure_s"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError):
        return None
    return testler, hatalar, sure


# --- Belgeden çıkarma ---------------------------------------------------------------


@dataclass
class SayfaSonucu:
    sayfa: int
    sure_s: float
    test_sayisi: int
    hatalar: list[str] = field(default_factory=list)


@dataclass
class CikarimRaporu:
    sayfalar: list[SayfaSonucu] = field(default_factory=list)
    tekrar_edenler: list[str] = field(default_factory=list)
    yon_celiskileri: list[dict[str, Any]] = field(default_factory=list)
    toplam_sure_s: float = 0.0
    test_sayisi: int = 0
    devam_edilen_sayfalar: list[int] = field(default_factory=list)

    def sozluk(self) -> dict[str, Any]:
        return asdict(self)


def belgeden_cikar(
    belge: Belge,
    belge_no: str,
    revizyon: str,
    istemci: SohbetIstemcisi,
    sayfalar: set[int] | None = None,
    ara_kayit: Path | str | None = None,
    parmak_izi: str | None = None,
) -> tuple[KabulDokumani, CikarimRaporu]:
    """Belgeyi sayfa sayfa modele okutur, test şartlarını kabul dokümanında toplar.

    Metni boş sayfalar (taranmış) atlanır. Aynı `id` birden çok sayfada çıkarsa
    ilki tutulur, diğerleri `tekrar_edenler` listesine yazılır. Kaynağın belge
    no, revizyon ve sayfa alanları koddan yazılır (madde modelden gelir). Numune hazırlama
    bilgisi bu adımda çıkarılmadığı için testlerin numune bağlantısı boşaltılır.
    Bir sayfadaki bağlantı ya da zaman aşımı hatası rapora yazılır, kalan
    sayfalar okunmaya devam eder. Her sınırın yönü özgün metinden kuralla
    denetlenir; çelişenler `yon="belirsiz"` yapılır ve `yon_celiskileri`ne yazılır.

    `ara_kayit` verilirse her işlenen sayfanın sonucu (`sayfa_NNN.json`: sayfa,
    süre, modelin testleri, hatalar) bu klasöre atomik olarak yazılır. Kaydı
    olan sayfa modele gönderilmez, sonucu dosyadan okunur ve
    `devam_edilen_sayfalar`a eklenir. Bozuk kayıt yok sayılır, sayfa yeniden okunur.
    Her kayıtta `parmak_izi` bulunur (verilmezse `ara_kayit_parmak_izi(istemci)`);
    izi farklı ya da izsiz kayıt kullanılmaz, üzerine yazılır. İstek hatası
    (bağlantı, zaman aşımı) kayda yazılmaz; o sayfa sonraki çalıştırmada yeniden istenir.
    """
    sema = cikarim_semasi()
    if ara_kayit is not None and parmak_izi is None:
        parmak_izi = ara_kayit_parmak_izi(istemci)
    rapor = CikarimRaporu()
    testler: dict[str, TestSarti] = {}
    baslangic = time.perf_counter()

    for sayfa in belge.sayfalar:
        if sayfalar is not None and sayfa.no not in sayfalar:
            continue
        metin = metni_normallestir(sayfa.metin)
        if not metin:
            continue
        kayitli = _ara_kaydi_oku(ara_kayit, sayfa.no, parmak_izi) if ara_kayit is not None else None
        if kayitli is not None:
            bulunan, hatalar, sure = kayitli
            rapor.devam_edilen_sayfalar.append(sayfa.no)
        else:
            mesajlar = istem_olustur(metin, sayfa.no, belge_no, revizyon)
            t0 = time.perf_counter()
            istek_hatasi = False
            try:
                bulunan, hatalar = yaniti_coz(istemci.sohbet(mesajlar, sema))
            except (OSError, http.client.HTTPException, ValueError, KeyError, IndexError) as hata:
                bulunan, hatalar = [], [f"istek başarısız: {type(hata).__name__}: {hata}"]
                istek_hatasi = True
            sure = round(time.perf_counter() - t0, 3)
            if ara_kayit is not None and not istek_hatasi:  # istek hatası kayda girmez, sonra yeniden istenir
                _ara_kaydi_yaz(ara_kayit, sayfa.no, sure, bulunan, hatalar, parmak_izi)

        for t in bulunan:
            if t.id in testler:
                rapor.tekrar_edenler.append(t.id)
                continue
            # Belge no, revizyon ve sayfa kodca bilinir; modelin yazdığı değil bunlar tutulur.
            kaynak = t.kaynak.model_copy(update={"belge_no": belge_no, "revizyon": revizyon, "sayfa": sayfa.no})
            # Sınır yönü modelden bağımsız olarak özgün metinden denetlenir (kör nokta 6);
            # çelişen yön "belirsiz" yapılır, karar motoru bunu insan incelemesine gönderir.
            sinir, denetim = yonu_guvenli_yap(t.sinir)
            if denetim.durum == "celiski":
                rapor.yon_celiskileri.append({
                    "id": t.id, "sayfa": sayfa.no, "metin_yonu": denetim.metin_yonu,
                    "model_yonu": denetim.model_yonu, "orijinal_metin": t.sinir.orijinal_metin,
                })
            testler[t.id] = t.model_copy(update={"numune_hazirlama_id": None, "kaynak": kaynak, "sinir": sinir})
        rapor.sayfalar.append(SayfaSonucu(sayfa.no, sure, len(bulunan), hatalar))

    rapor.toplam_sure_s = round(time.perf_counter() - baslangic, 3)
    rapor.test_sayisi = len(testler)
    dokuman = KabulDokumani(
        standart=StandartBilgisi(belge_no=belge_no, revizyon=revizyon),
        testler=list(testler.values()),
    )
    return dokuman, rapor
