"""docs/arayuz_sozlesmesi.md koddan sapmaz.

Doküman biçimi:
- Her fonksiyon/metot/sabit/sınıf için bir `### ` başlığı; başlıkta tek bir kod parçası.
- Fonksiyon ve metotlar parantezli, parametre adları gerçek imzadaki sırayla
  (`self` yazılmaz, `*args`/`**kwargs` yıldızlı, salt-anahtar parametreler yıldızsız):
  ### `malzeme_kabul.katalog.veritabani.Katalog.malzeme(kod)`
- Sabitler ve sınıflar parantezsiz:
  ### `malzeme_kabul.arayuz.ekran_verisi.PARTI_ETIKETI`
- Fonksiyon bölümlerinde (bir sonraki `##`/`###` başlığa kadar) `**Girdiler**` ve `**Çıktı**` bulunur.

Streamlit kurulu olmayabilir; uygulama.py içe aktarılmaz, yalnız ast ile okunur.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
DOKUMAN = KOK / "docs" / "arayuz_sozlesmesi.md"
UYGULAMA = KOK / "src" / "malzeme_kabul" / "arayuz" / "uygulama.py"


def paket_koku() -> Path:
    """İçe aktarılan malzeme_kabul paketinin depo kökü (src/malzeme_kabul/__init__.py -> kök).

    Kodun varsayılan yolları bu köke göre kurulur; test başka bir çalışma ağacından
    (ör. git worktree) koşsa da editable kurulum başka bir depoyu gösterebilir.
    """
    import malzeme_kabul

    return Path(malzeme_kabul.__file__).resolve().parents[2]

# uygulama.py içinde metot çağrılarının izlendiği değişkenler -> sınıf adı
NESNE_SINIFLARI = {"katalog": "Katalog", "defter": "DenetimKaydi"}
# Parantezsiz başlıkla mutlaka yer alması gereken sınıflar
ZORUNLU_SINIFLAR = ("Katalog", "DenetimKaydi", "KatalogHatasi", "HatHatasi")

_BASLIK = re.compile(r"^###\s+(.*?)\s*$")
_KOD_BASLIK = re.compile(r"^`([^`]+)`$")
_BOLUM_SONU = re.compile(r"^#{1,3}\s")
_AD = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:\((.*)\))?$")


# --- ayrıştırma yardımcıları -----------------------------------------------------------


@dataclass
class Baslik:
    satir: int  # 1 tabanlı
    ham: str  # başlıktaki ham metin
    ad: str | None  # tam nitelikli ad; biçim bozuksa None
    parametreler: list[str] | None  # parantezsizse None
    bolum: str  # başlığın altındaki metin (sonraki ##/### başlığa kadar)

    @property
    def parantezli(self) -> bool:
        return self.parametreler is not None


def _dokuman_metni() -> str:
    if not DOKUMAN.exists():
        pytest.fail(f"{DOKUMAN.relative_to(KOK)} yok; arayüz sözleşmesi yazılmalı.")
    return DOKUMAN.read_text(encoding="utf-8")


def basliklari_ayristir(metin: str) -> list[Baslik]:
    satirlar = metin.splitlines()
    sonuc: list[Baslik] = []
    for i, satir in enumerate(satirlar):
        m = _BASLIK.match(satir)
        if not m:
            continue
        ham = m.group(1)
        bolum_satirlari = []
        for sonraki in satirlar[i + 1:]:
            if _BOLUM_SONU.match(sonraki):
                break
            bolum_satirlari.append(sonraki)
        ad = parametreler = None
        kod = _KOD_BASLIK.match(ham)
        if kod:
            a = _AD.match(kod.group(1).strip())
            if a:
                ad = a.group(1)
                if a.group(2) is not None:
                    ic = a.group(2).strip()
                    parametreler = [p.strip() for p in ic.split(",")] if ic else []
        sonuc.append(Baslik(i + 1, ham, ad, parametreler, "\n".join(bolum_satirlari)))
    return sonuc


def ad_coz(tam_ad: str):
    """Tam nitelikli adı (modül + öznitelik zinciri) çözer; (nesne, üst nesne, son ad) döner."""
    parcalar = tam_ad.split(".")
    for bol in range(len(parcalar), 0, -1):
        modul_adi = ".".join(parcalar[:bol])
        try:
            modul = importlib.import_module(modul_adi)
        except ImportError:
            continue
        nesne, ust = modul, None
        for p in parcalar[bol:]:
            if not hasattr(nesne, p):
                raise AttributeError(f"{modul_adi} içinde '{'.'.join(parcalar[bol:])}' yok")
            ust, nesne = nesne, getattr(nesne, p)
        return nesne, ust, parcalar[-1]
    raise ImportError(f"'{tam_ad}' için içe aktarılabilir modül bulunamadı")


def gercek_parametreler(nesne, ust, son_ad: str) -> list[str]:
    imza = inspect.signature(nesne)
    adlar = []
    for p in imza.parameters.values():
        if p.kind is inspect.Parameter.VAR_POSITIONAL:
            adlar.append(f"*{p.name}")
        elif p.kind is inspect.Parameter.VAR_KEYWORD:
            adlar.append(f"**{p.name}")
        else:
            adlar.append(p.name)
    # Sınıf üzerinden alınan düz fonksiyon (örnek metodu): ilk parametre self'tir
    if inspect.isclass(ust) and not isinstance(inspect.getattr_static(ust, son_ad), (staticmethod, classmethod)):
        if inspect.isfunction(nesne) and adlar:
            adlar = adlar[1:]
    return adlar


def _fonksiyon_mu(nesne) -> bool:
    return callable(nesne) and not inspect.isclass(nesne)


def uygulama_kapsami(kaynak: str | None = None, zorunlu: tuple[str, ...] = ZORUNLU_SINIFLAR) -> set[str]:
    """Kaynağın (varsayılan uygulama.py) malzeme_kabul'dan kullandığı her şeyin tam nitelikli adları."""
    agac = ast.parse(UYGULAMA.read_text(encoding="utf-8") if kaynak is None else kaynak)
    takma: dict[str, str] = {}  # yerel ad -> tam nitelikli ad
    kapsam: set[str] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.ImportFrom) and dugum.module and dugum.module.split(".")[0] == "malzeme_kabul":
            for a in dugum.names:
                tam = f"{dugum.module}.{a.name}"
                takma[a.asname or a.name] = tam
                if importlib.util.find_spec(dugum.module) is not None:
                    try:
                        alt_modul = importlib.util.find_spec(tam) is not None
                    except ModuleNotFoundError:
                        alt_modul = False
                    if alt_modul:
                        continue  # modülün kendisi (ör. ekran_verisi as ev); erişimleri ayrıca toplanır
                kapsam.add(tam)
    modul_takmalari = {yerel: tam for yerel, tam in takma.items() if tam not in kapsam}
    nesne_sinifi = {degisken: takma[sinif] for degisken, sinif in NESNE_SINIFLARI.items() if sinif in takma}
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Attribute) and isinstance(dugum.value, ast.Name):
            if dugum.value.id in modul_takmalari:
                kapsam.add(f"{modul_takmalari[dugum.value.id]}.{dugum.attr}")
        if (isinstance(dugum, ast.Call) and isinstance(dugum.func, ast.Attribute)
                and isinstance(dugum.func.value, ast.Name) and dugum.func.value.id in nesne_sinifi):
            kapsam.add(f"{nesne_sinifi[dugum.func.value.id]}.{dugum.func.attr}")
    for sinif in zorunlu:
        assert sinif in takma, f"uygulama.py artık {sinif} içe aktarmıyor; testi güncelleyin"
        kapsam.add(takma[sinif])
    return kapsam


@pytest.fixture(scope="module")
def basliklar() -> list[Baslik]:
    return basliklari_ayristir(_dokuman_metni())


# --- testler ------------------------------------------------------------------------------


def test_sozlesme_dokumani_var_ve_baslik_icerir():
    metin = _dokuman_metni()
    assert basliklari_ayristir(metin), "docs/arayuz_sozlesmesi.md içinde hiç '### ' başlığı yok"


def test_her_baslik_tek_kod_parcasi_ve_gecerli_ad_icerir(basliklar):
    bozuk = [f"satır {b.satir}: {b.ham!r}" for b in basliklar if b.ad is None]
    assert not bozuk, "Başlıkta tek bir kod parçası içinde tam nitelikli ad olmalı:\n" + "\n".join(bozuk)


def test_her_baslik_ice_aktarilabilir(basliklar):
    hatalar = []
    for b in basliklar:
        if b.ad is None:
            continue
        try:
            ad_coz(b.ad)
        except (ImportError, AttributeError) as hata:
            hatalar.append(f"satır {b.satir} `{b.ad}`: {hata}")
    assert not hatalar, "İçe aktarılamayan başlıklar:\n" + "\n".join(hatalar)


def test_parametre_adlari_gercek_imzayla_ayni_sirada(basliklar):
    hatalar = []
    for b in basliklar:
        if b.ad is None or not b.parantezli:
            continue
        try:
            nesne, ust, son = ad_coz(b.ad)
        except (ImportError, AttributeError):
            continue  # içe aktarma testi raporlar
        if not callable(nesne):
            hatalar.append(f"satır {b.satir} `{b.ad}`: çağrılabilir değil, parantezsiz yazılmalı")
            continue
        try:
            gercek = gercek_parametreler(nesne, ust, son)
        except (TypeError, ValueError) as hata:
            hatalar.append(f"satır {b.satir} `{b.ad}`: imza okunamadı ({hata})")
            continue
        if b.parametreler != gercek:
            hatalar.append(f"satır {b.satir} `{b.ad}`: dokümanda ({', '.join(b.parametreler)}), "
                           f"kodda ({', '.join(gercek)})")
    assert not hatalar, "İmzası koddan sapan başlıklar:\n" + "\n".join(hatalar)


def test_fonksiyonlar_parantezli_yazilir(basliklar):
    hatalar = []
    for b in basliklar:
        if b.ad is None or b.parantezli:
            continue
        try:
            nesne, _, _ = ad_coz(b.ad)
        except (ImportError, AttributeError):
            continue
        if _fonksiyon_mu(nesne):
            hatalar.append(f"satır {b.satir} `{b.ad}`: fonksiyon/metot, parametreleriyle parantezli yazılmalı")
    assert not hatalar, "\n".join(hatalar)


def test_fonksiyon_bolumlerinde_girdiler_ve_cikti_var(basliklar):
    eksik = []
    for b in basliklar:
        if b.ad is None or not b.parantezli:
            continue
        yok = [e for e in ("**Girdiler**", "**Çıktı**") if e not in b.bolum]
        if yok:
            eksik.append(f"satır {b.satir} `{b.ad}`: {', '.join(yok)} yok")
    assert not eksik, "Girdi/çıktı tarifi eksik bölümler:\n" + "\n".join(eksik)


def test_uygulamanin_kullandigi_her_sey_belgelenir(basliklar):
    belgelenen = {b.ad for b in basliklar if b.ad}
    eksik = sorted(uygulama_kapsami() - belgelenen)
    assert not eksik, "uygulama.py'nin kullandığı ama dokümanda başlığı olmayanlar:\n" + "\n".join(eksik)


def test_zorunlu_siniflar_parantezsiz_basliktadir(basliklar):
    parantezsiz = {b.ad for b in basliklar if b.ad and not b.parantezli}
    beklenen = {ad for ad in uygulama_kapsami() if ad.rsplit(".", 1)[-1] in ZORUNLU_SINIFLAR}
    eksik = sorted(beklenen - parantezsiz)
    assert not eksik, "Parantezsiz başlıkla yer alması gereken sınıflar eksik:\n" + "\n".join(eksik)


def test_ayni_baslik_iki_kez_yazilmaz(basliklar):
    gorulen: dict[str, int] = {}
    tekrar = []
    for b in basliklar:
        if b.ad is None:
            continue
        if b.ad in gorulen:
            tekrar.append(f"`{b.ad}`: satır {gorulen[b.ad]} ve {b.satir}")
        else:
            gorulen[b.ad] = b.satir
    assert not tekrar, "Tekrarlanan başlıklar:\n" + "\n".join(tekrar)


# --- ayrıştırıcının kendisi (doküman olmadan da çalışır) -------------------------------------


def test_ayristirici_metot_parametrelerinden_self_dusurur():
    nesne, ust, son = ad_coz("malzeme_kabul.katalog.veritabani.Katalog.malzeme")
    assert gercek_parametreler(nesne, ust, son) == ["kod"]


def test_ayristirici_baslik_bicimini_ve_bolumu_okur():
    metin = (
        "## Bölüm\n"
        "### `a.b.f(x, *args, y, **kw)`\n**Girdiler**: x\n**Çıktı**: y\n"
        "### `a.b.SABIT`\nmetin\n"
        "### düz başlık\n"
    )
    b = basliklari_ayristir(metin)
    assert [x.ad for x in b] == ["a.b.f", "a.b.SABIT", None]
    assert b[0].parametreler == ["x", "*args", "y", "**kw"] and "**Çıktı**" in b[0].bolum
    assert "a.b.SABIT" not in b[0].bolum
    assert b[1].parametreler is None


def test_kapsam_uygulamadan_ast_ile_cikarilir():
    kapsam = uygulama_kapsami()
    assert "malzeme_kabul.arayuz.ekran_verisi.standart_yukle" in kapsam
    assert "malzeme_kabul.katalog.veritabani.Katalog.malzeme" in kapsam
    assert "malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.zinciri_dogrula" in kapsam
    assert "malzeme_kabul.arayuz.ekran_verisi" not in kapsam  # modülün kendisi değil


# --- Girdiler / Hatalar alt bölümleri ----------------------------------------------------------
#
# Dokümandaki yazım:
#   **Girdiler**
#   - `ad` (`tip`, zorunlu): açıklama
#   - `ad` (`tip`, isteğe bağlı, varsayılan `X`): açıklama (satır kayabilir)
#   - `a` (`tip`, zorunlu) ve `b` (`tip`, zorunlu): açıklama
#   **Çıktı** ...
#   **Hatalar**
#   - `KatalogHatasi`: ...

_ETIKET = re.compile(r"^\*\*[^*]+\*\*")
_PARAM_ACILIS = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`\s*\(")
_ISTISNA = re.compile(r"`([A-Z][A-Za-z0-9_]*(?:Hatasi|Error|Exception))`")


def alt_bolum(bolum: str, etiket: str) -> str:
    """`**etiket**` satırından bir sonraki `**...**` ile başlayan satıra kadarki metin (etiket satırı dahil)."""
    satirlar = bolum.splitlines()
    for i, satir in enumerate(satirlar):
        if satir.startswith(f"**{etiket}**"):
            son = next((j for j in range(i + 1, len(satirlar)) if _ETIKET.match(satirlar[j])), len(satirlar))
            return "\n".join(satirlar[i:son])
    return ""


def _maddeler(metin: str) -> list[str]:
    """Liste maddelerini, girintili devam satırlarıyla birleştirip döner."""
    maddeler: list[str] = []
    for satir in metin.splitlines():
        if satir.startswith("- "):
            maddeler.append(satir[2:].strip())
        elif maddeler and satir.startswith(" ") and satir.strip():
            maddeler[-1] += " " + satir.strip()
    return maddeler


def _parantez_ici(metin: str, bas: int) -> str | None:
    """metin[bas] '(' iken eşleşen ')' ye kadarki içerik; backtick içindeki parantezler sayılmaz."""
    derinlik, kod = 0, False
    for i in range(bas, len(metin)):
        c = metin[i]
        if c == "`":
            kod = not kod
        elif not kod and c == "(":
            derinlik += 1
        elif not kod and c == ")":
            derinlik -= 1
            if derinlik == 0:
                return metin[bas + 1:i]
    return None


def _ust_duzey_virgul(metin: str) -> list[str]:
    parcalar, kod, bas = [], False, 0
    for i, c in enumerate(metin):
        if c == "`":
            kod = not kod
        elif c == "," and not kod:
            parcalar.append(metin[bas:i].strip())
            bas = i + 1
    parcalar.append(metin[bas:].strip())
    return parcalar


@dataclass
class GirdiTarifi:
    ad: str
    zorunlu: bool
    istege_bagli: bool
    varsayilan: str | None  # backtick içindeki ham metin
    tip: str | None = None  # parantez içindeki ilk parça tek bir kod parçasıysa onun içi


def girdi_tarifleri(girdiler: str) -> list[GirdiTarifi]:
    """Girdiler alt bölümündeki `ad` (...) tariflerini okur."""
    sonuc = []
    for madde in _maddeler(girdiler):
        for m in _PARAM_ACILIS.finditer(madde):
            ic = _parantez_ici(madde, m.end() - 1)
            if ic is None:
                continue
            parcalar = _ust_duzey_virgul(ic)
            varsayilan = None
            for p in parcalar:
                v = re.match(r"^varsayılan\s+`([^`]*)`", p)
                if v:
                    varsayilan = v.group(1)
            tip = re.fullmatch(r"`([^`]+)`", parcalar[0]) if parcalar else None
            sonuc.append(GirdiTarifi(m.group(1), "zorunlu" in parcalar, "isteğe bağlı" in parcalar, varsayilan,
                                     tip.group(1) if tip else None))
    return sonuc


def varsayilan_tutar_mi(gercek, yazilan: str) -> bool:
    """Yazılan varsayılan, gerçeğin repr'i ya da str'i ile tutar mı.

    İki biçim farkı kabul edilir: str varsayılanlar çift tırnakla (`":memory:"`),
    depo içi Path varsayılanlar depo köküne göre (`data/cikti`) yazılabilir.
    """
    adaylar = {repr(gercek), str(gercek)}
    if isinstance(gercek, str):
        adaylar.add(f'"{gercek}"')
    if isinstance(gercek, Path):
        try:
            adaylar.add(gercek.resolve().relative_to(paket_koku()).as_posix())
        except ValueError:
            pass
    return yazilan in adaylar


def istisna_bul(ad: str):
    """Adı builtins'te ya da malzeme_kabul modüllerinin ad alanında istisna sınıfı olarak arar."""
    import builtins
    import pkgutil

    import malzeme_kabul

    aday = getattr(builtins, ad, None)
    if inspect.isclass(aday) and issubclass(aday, BaseException):
        return aday
    for bilgi in pkgutil.walk_packages(malzeme_kabul.__path__, "malzeme_kabul."):
        try:
            modul = importlib.import_module(bilgi.name)
        except ImportError:  # ör. streamlit kurulu değilse arayuz.uygulama
            continue
        aday = getattr(modul, ad, None)
        if inspect.isclass(aday) and issubclass(aday, BaseException):
            return aday
    return None


def _cozulmus_fonksiyon_basliklari(basliklar):
    for b in basliklar:
        if b.ad is None or not b.parantezli:
            continue
        try:
            nesne, ust, son = ad_coz(b.ad)
            imza = inspect.signature(nesne)
        except (ImportError, AttributeError, TypeError, ValueError):
            continue  # diğer testler raporlar
        parametreler = dict(imza.parameters)
        if inspect.isclass(ust) and inspect.isfunction(nesne) and not isinstance(
                inspect.getattr_static(ust, son), (staticmethod, classmethod)):
            parametreler.pop(next(iter(parametreler)), None)  # self
        yield b, parametreler


def test_girdilerde_her_parametre_adi_gecer(basliklar):
    eksik = []
    for b, parametreler in _cozulmus_fonksiyon_basliklari(basliklar):
        girdiler = alt_bolum(b.bolum, "Girdiler")
        yok = [ad for ad in parametreler if f"`{ad}`" not in girdiler]
        if yok:
            eksik.append(f"satır {b.satir} `{b.ad}`: Girdiler altında geçmeyen parametreler: {', '.join(yok)}")
    assert not eksik, "\n".join(eksik)


def test_her_parametrenin_girdilerde_tam_tarifi_var(basliklar):
    """Adın geçmesi yetmez: `ad` (`tip`, zorunlu | isteğe bağlı ...) biçiminde tarif edilmeli."""
    hatalar = []
    for b, parametreler in _cozulmus_fonksiyon_basliklari(basliklar):
        tarifler: dict[str, list[GirdiTarifi]] = {}
        for t in girdi_tarifleri(alt_bolum(b.bolum, "Girdiler")):
            tarifler.setdefault(t.ad, []).append(t)
        for ad in parametreler:
            yer = f"satır {b.satir} `{b.ad}` parametre `{ad}`"
            if ad not in tarifler:
                hatalar.append(f"{yer}: Girdiler'de `{ad}` (`tip`, zorunlu | isteğe bağlı ...) tarifi yok")
                continue
            if len(tarifler[ad]) > 1:
                hatalar.append(f"{yer}: Girdiler'de {len(tarifler[ad])} kez tarif edilmiş")
            t = tarifler[ad][0]
            if t.tip is None:
                hatalar.append(f"{yer}: parantezin ilk parçası tek bir kod parçası içinde tip değil")
            if t.zorunlu == t.istege_bagli:
                hatalar.append(f"{yer}: 'zorunlu' ve 'isteğe bağlı'dan tam biri yazılmalı "
                               f"({'ikisi de' if t.zorunlu else 'hiçbiri'} yazılmış)")
    assert not hatalar, "Girdiler'de tam tarifi olmayan parametreler:\n" + "\n".join(hatalar)


def test_girdilerdeki_zorunlu_ve_varsayilan_imzayla_tutarli(basliklar):
    bos = inspect.Parameter.empty
    hatalar = []
    for b, parametreler in _cozulmus_fonksiyon_basliklari(basliklar):
        for t in girdi_tarifleri(alt_bolum(b.bolum, "Girdiler")):
            p = parametreler.get(t.ad)
            if p is None:
                continue  # parametre olmayan adlar (ör. iç içe alanlar) denetlenmez
            yer = f"satır {b.satir} `{b.ad}` parametre `{t.ad}`"
            if t.zorunlu and t.istege_bagli:
                hatalar.append(f"{yer}: hem 'zorunlu' hem 'isteğe bağlı' yazılmış")
            if t.zorunlu and p.default is not bos:
                hatalar.append(f"{yer}: 'zorunlu' yazılmış ama kodda varsayılanı var ({p.default!r})")
            if t.istege_bagli and p.default is bos:
                hatalar.append(f"{yer}: 'isteğe bağlı' yazılmış ama kodda varsayılanı yok")
            if t.varsayilan is not None:
                if p.default is bos:
                    hatalar.append(f"{yer}: varsayılan `{t.varsayilan}` yazılmış ama kodda varsayılan yok")
                elif not varsayilan_tutar_mi(p.default, t.varsayilan):
                    hatalar.append(f"{yer}: dokümanda varsayılan `{t.varsayilan}`, kodda {p.default!r}")
    assert not hatalar, "Girdiler tarifi imzayla tutarsız:\n" + "\n".join(hatalar)


def test_hatalardaki_istisnalar_gercek_siniflardir(basliklar):
    hatalar = []
    for b in basliklar:
        if b.ad is None:
            continue
        for ad in sorted(set(_ISTISNA.findall(alt_bolum(b.bolum, "Hatalar")))):
            if istisna_bul(ad) is None:
                hatalar.append(f"satır {b.satir} `{b.ad}`: `{ad}` malzeme_kabul içinde ya da builtins'te "
                               f"bir istisna sınıfı değil")
    assert not hatalar, "Hatalar altında bulunamayan istisnalar:\n" + "\n".join(hatalar)


# --- yeni ayrıştırıcıların kendisi ----------------------------------------------------------


def test_ayristirici_girdi_tariflerini_okur():
    girdiler = (
        "**Girdiler**\n\n"
        "- `a` (`str`, zorunlu, boş olamaz): açıklama (`X` zorunlu, ayrıntı).\n"
        "- `b` (`str | Path`, isteğe bağlı, varsayılan\n"
        "  `\":memory:\"`): satır kayar.\n"
        "- `c` (`int`, isteğe bağlı, varsayılan `30`) ve `d` (`date | None`, isteğe bağlı,\n"
        "  varsayılan `None` → bugün).\n"
        "**Çıktı**: `e` (`bool`)\n"
    )
    tarifler = {t.ad: t for t in girdi_tarifleri(alt_bolum(girdiler, "Girdiler"))}
    assert set(tarifler) == {"a", "b", "c", "d"}  # Çıktı'daki `e` ve açıklamadaki `X` alınmaz
    assert tarifler["a"].zorunlu and tarifler["a"].varsayilan is None
    assert tarifler["b"].istege_bagli and tarifler["b"].varsayilan == '":memory:"'
    assert tarifler["c"].varsayilan == "30" and tarifler["d"].varsayilan == "None"
    assert tarifler["a"].tip == "str" and tarifler["d"].tip == "date | None"


def test_ayristirici_eksik_tarifi_ayirt_eder():
    girdiler = (
        "**Girdiler**\n"
        "- `a`: tipsiz ve zorunluluksuz; ad geçiyor ama tarif yok.\n"
        "- `b` (zorunlu): tip yok.\n"
        "- `c` (`int`): zorunluluk yok.\n"
    )
    tarifler = {t.ad: t for t in girdi_tarifleri(alt_bolum(girdiler, "Girdiler"))}
    assert "a" not in tarifler
    assert tarifler["b"].tip is None and tarifler["b"].zorunlu
    assert tarifler["c"].tip == "int" and not (tarifler["c"].zorunlu or tarifler["c"].istege_bagli)


def test_varsayilan_karsilastirmasi_repr_str_ve_kabul_edilen_bicimler():
    assert varsayilan_tutar_mi(None, "None")
    assert varsayilan_tutar_mi(30, "30")
    assert not varsayilan_tutar_mi(30, "31")
    assert varsayilan_tutar_mi(":memory:", '":memory:"')
    assert varsayilan_tutar_mi(":memory:", "':memory:'")
    assert varsayilan_tutar_mi(paket_koku() / "data" / "cikti", "data/cikti")
    assert not varsayilan_tutar_mi(paket_koku() / "data" / "cikti", "data/gold")
    assert not varsayilan_tutar_mi(Path("/baska/yer/data/cikti"), "data/cikti")  # paket kökü dışı


def test_paket_koku_kodun_kendi_kokuyle_ayni():
    from malzeme_kabul.arayuz import ekran_verisi

    assert paket_koku() == ekran_verisi.KOK.resolve()
    assert not varsayilan_tutar_mi(False, "None")


def test_istisna_arayici_gercek_ve_uydurma_adlari_ayirir():
    assert istisna_bul("ValueError") is ValueError
    assert istisna_bul("KatalogHatasi") is not None
    assert istisna_bul("DenetimHatasi") is not None
    assert istisna_bul("UydurmaHatasi") is None
    assert istisna_bul("TABLO_SUTUNLARI") is None  # var ama istisna değil


def test_kapsam_sentetik_kaynaktan_beklenen_kumeyi_cikarir():
    kaynak = (
        "import os\n"
        "import streamlit as st\n"
        "from malzeme_kabul.arayuz import ekran_verisi as ev\n"
        "from malzeme_kabul.arayuz.kimlik import giris\n"
        "from malzeme_kabul.katalog.veritabani import Katalog\n"
        "from malzeme_kabul.kayit.denetim_kaydi import DenetimKaydi\n"
        "def f(katalog, defter, baska):\n"
        "    st.write(ev.PARTI_ETIKETI)\n"
        "    ev.standart_yukle(katalog, 'a.pdf', 'u')\n"
        "    katalog.malzeme('K')\n"
        "    katalog.baglanti\n"            # öznitelik, çağrı değil: alınmaz
        "    defter.zinciri_dogrula()\n"
        "    baska.malzeme('K')\n"           # izlenmeyen değişken: alınmaz
        "    os.path.join('a')\n"
    )
    beklenen = {
        "malzeme_kabul.arayuz.kimlik.giris",
        "malzeme_kabul.katalog.veritabani.Katalog",
        "malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi",
        "malzeme_kabul.arayuz.ekran_verisi.PARTI_ETIKETI",
        "malzeme_kabul.arayuz.ekran_verisi.standart_yukle",
        "malzeme_kabul.katalog.veritabani.Katalog.malzeme",
        "malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.zinciri_dogrula",
    }
    assert uygulama_kapsami(kaynak, zorunlu=()) == beklenen


def test_kapsam_zorunlu_sinif_ice_aktarilmazsa_uyarir():
    kaynak = "from malzeme_kabul.katalog.veritabani import Katalog\n"
    with pytest.raises(AssertionError, match="HatHatasi"):
        uygulama_kapsami(kaynak, zorunlu=("Katalog", "HatHatasi"))
