"""İlk kurulum: Docker'da varsayılan parola yok; parola ortamdan gelir, yoksa uygulama başlamaz.

Tasarım (Nida'nın isteği: "Docker'da varsayılan parola olmasın ... parola yoksa
uygulama başlamasın. Bunun bir testi olsun."):

- `kimlik.ortamdan_kullanicilar(ortam, baglanti) -> list[Kullanici]`:
  veritabanında hiç kullanıcı yoksa `MALZEME_KABUL_MP_PAROLASI` ve
  `MALZEME_KABUL_GK_PAROLASI` (ya da Docker secrets için
  `MALZEME_KABUL_MP_PAROLASI_DOSYASI` / `MALZEME_KABUL_GK_PAROLASI_DOSYASI`)
  ile iki kullanıcı açar: M&P (`mp`) ve giriş kalite (`giris_kalite`).
  Kullanıcı adları `MALZEME_KABUL_MP_KULLANICI` / `MALZEME_KABUL_GK_KULLANICI`
  (varsayılan "mp" / "gk"). Parola yoksa ya da zayıfsa `KimlikHatasi`; hiçbir
  kullanıcı oluşmaz (ya ikisi ya hiçbiri). Veritabanında zaten kullanıcı varsa
  ortam değişkeni gerekmez ve mevcut kullanıcılar değiştirilmez; [] döner.
- Parola kuralları: en az 12 karakter; kullanıcı adıyla aynı olamaz (büyük/küçük
  harf farkı gözetilmez); bilinen deneme parolaları (`mp-ornek-parola`,
  `gk-ornek-parola`) reddedilir. Dosyadan okunan parolanın sonundaki satır sonu
  atılır.
- `scripts/ilk_kurulum.py --db YOL`: bu fonksiyonu süreç ortamıyla çağırır;
  başarıda 0, hata durumunda sıfırdan farklı döner ve hangi değişkenin
  ayarlanacağını söyler. Parolalar hiçbir çıktıya yazılmaz.
- `docker/baslat.sh`: betik yolları `${MALZEME_KABUL_KOK:-/uygulama}` altından
  çözülür; ilk kurulum denetimi Streamlit'ten önce çalışır, başarısızsa
  Streamlit başlamaz. Deneme kullanıcıları Docker yolunda hiç oluşturulmaz.
  Betik `sh` ile çalışır (Dockerfile ENTRYPOINT: `sh /uygulama/docker/baslat.sh`).

Gözden geçirme bulguları (eklenen davranışlar):

- Eski volume'larda deneme hesapları kalabilir. `ortamdan_kullanicilar` her
  çağrıda (her açılışta) mevcut hesapları bilinen deneme parolalarına
  (`kimlik.DENEME_PAROLALARI`) karşı dener; biri tutarsa `KimlikHatasi` verir
  (mesaj hesabın adını söyler, parolayı söylemez) ve hiçbir hesabı değiştirmez.
  Ortamda geçerli parola olsa da olmasa da böyledir. Böylece ilk_kurulum.py
  sıfırdan farklı çıkar ve baslat.sh Streamlit'i başlatmaz.
- Yalnız boşluktan oluşan parola (ör. 12 boşluk) reddedilir.
- Aynı rol için hem `*_PAROLASI` hem `*_PAROLASI_DOSYASI` verilirse hata.
- İki rol için aynı kullanıcı adı hata.
- Docker'da deneme kullanıcıları açılamaz: `scripts/katalog_kur.py
  --ornek-kullanicilar`, ortamda `MALZEME_KABUL_DOCKER=1` varsa reddedilir
  (sıfırdan farklı çıkış, kullanıcı oluşmaz, parola yazılmaz). Seçim: açık bir
  `MALZEME_KABUL_DOCKER=1` işareti (Dockerfile ENV'de ayarlanır;
  tests/test_docker.py bunu denetler). `MALZEME_KABUL_KOK` değerine bakılmaz,
  çünkü testler ve yerel kullanım da bu değişkeni ayarlar. İşaret yokken
  `--ornek-kullanicilar` yerelde çalışmaya devam eder (tests/test_arayuz.py).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from malzeme_kabul.arayuz import kimlik
from tests.conftest import KOK

MP_PAROLA = "Mp-Gercek-Parola-2026"
GK_PAROLA = "Gk-Gercek-Parola-2026"


def gecerli_ortam(**ek) -> dict[str, str]:
    ortam = {"MALZEME_KABUL_MP_PAROLASI": MP_PAROLA, "MALZEME_KABUL_GK_PAROLASI": GK_PAROLA}
    ortam.update(ek)
    return ortam


@pytest.fixture
def baglanti(tmp_path):
    b = sqlite3.connect(tmp_path / "katalog.sqlite")
    yield b
    b.close()


def kullanici_sayisi(b: sqlite3.Connection) -> int:
    return len(kimlik.kullanicilar(b))


# --- (a) parola yoksa uygulama başlamaz -------------------------------------------------


def test_parola_yokken_ve_kullanici_yokken_kimlik_hatasi_verir(baglanti):
    with pytest.raises(kimlik.KimlikHatasi, match="MALZEME_KABUL_MP_PAROLASI"):
        kimlik.ortamdan_kullanicilar({}, baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_bos_parola_belirlenmemis_sayilir(baglanti):
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_MP_PAROLASI=""), baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_yalniz_mp_parolasi_varsa_hic_kullanici_olusmaz(baglanti):
    ortam = {"MALZEME_KABUL_MP_PAROLASI": MP_PAROLA}
    with pytest.raises(kimlik.KimlikHatasi, match="MALZEME_KABUL_GK_PAROLASI"):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_yalniz_gk_parolasi_varsa_hic_kullanici_olusmaz(baglanti):
    ortam = {"MALZEME_KABUL_GK_PAROLASI": GK_PAROLA}
    with pytest.raises(kimlik.KimlikHatasi, match="MALZEME_KABUL_MP_PAROLASI"):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


# --- (b) zayıf parolalar reddedilir ------------------------------------------------------


@pytest.mark.parametrize("uzunluk", [0, 1, 11])
def test_on_ikiden_kisa_parola_reddedilir(baglanti, uzunluk):
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_MP_PAROLASI="x" * uzunluk), baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_tam_on_iki_karakterlik_parola_kabul_edilir(baglanti):
    ortam = gecerli_ortam(MALZEME_KABUL_MP_PAROLASI="a1b2c3d4e5f6")  # tam sınır
    assert len(ortam["MALZEME_KABUL_MP_PAROLASI"]) == 12
    kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kimlik.giris(baglanti, "mp", "a1b2c3d4e5f6") is not None


def test_on_uc_karakterlik_parola_kabul_edilir(baglanti):
    kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_GK_PAROLASI="a1b2c3d4e5f6g"), baglanti)
    assert kimlik.giris(baglanti, "gk", "a1b2c3d4e5f6g") is not None


def test_kullanici_adiyla_ayni_parola_reddedilir(baglanti):
    ortam = gecerli_ortam(MALZEME_KABUL_MP_KULLANICI="nida.yilmaz.mp", MALZEME_KABUL_MP_PAROLASI="nida.yilmaz.mp")
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_kullanici_adiyla_buyuk_kucuk_harf_farkiyla_ayni_parola_reddedilir(baglanti):
    ortam = gecerli_ortam(MALZEME_KABUL_GK_KULLANICI="giriskalite01", MALZEME_KABUL_GK_PAROLASI="GirisKalite01")
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


@pytest.mark.parametrize("deneme", ["mp-ornek-parola", "gk-ornek-parola"])
@pytest.mark.parametrize("degisken", ["MALZEME_KABUL_MP_PAROLASI", "MALZEME_KABUL_GK_PAROLASI"])
def test_bilinen_deneme_parolalari_reddedilir(baglanti, deneme, degisken):
    assert len(deneme) >= 12  # uzunluk kuralına takılmıyor; ayrıca reddedilmeli
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(gecerli_ortam(**{degisken: deneme}), baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_hata_mesajinda_parola_gecmez(baglanti):
    zayif = "mp-ornek-parola"
    with pytest.raises(kimlik.KimlikHatasi) as hata:
        kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_MP_PAROLASI=zayif), baglanti)
    assert zayif not in str(hata.value)


@pytest.mark.parametrize("bosluk", [" " * 12, " " * 13, "\t" * 12, " \t " * 4])
def test_yalniz_bosluktan_olusan_parola_reddedilir(baglanti, bosluk):
    assert len(bosluk) >= 12  # uzunluk kuralına takılmıyor; yine de reddedilmeli
    with pytest.raises(kimlik.KimlikHatasi, match="MALZEME_KABUL_MP_PAROLASI"):
        kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_MP_PAROLASI=bosluk), baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_dosyadan_okunan_yalniz_bosluk_parola_reddedilir(baglanti, tmp_path):
    (tmp_path / "gk_parola").write_text(" " * 12 + "\n", encoding="utf-8")
    ortam = {"MALZEME_KABUL_MP_PAROLASI": MP_PAROLA, "MALZEME_KABUL_GK_PAROLASI_DOSYASI": str(tmp_path / "gk_parola")}
    with pytest.raises(kimlik.KimlikHatasi, match="MALZEME_KABUL_GK_PAROLASI"):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


# --- (c) geçerli parolalarla iki kullanıcı ------------------------------------------------


def test_gecerli_parolalarla_mp_ve_giris_kalite_kullanicilari_olusur(baglanti):
    olusan = kimlik.ortamdan_kullanicilar(gecerli_ortam(), baglanti)
    beklenen = {kimlik.Kullanici("mp", "mp"), kimlik.Kullanici("gk", "giris_kalite")}
    assert set(olusan) == beklenen
    assert set(kimlik.kullanicilar(baglanti)) == beklenen


def test_ortamdan_kurulan_kullanicilar_giris_yapabilir(baglanti):
    kimlik.ortamdan_kullanicilar(gecerli_ortam(), baglanti)
    assert kimlik.giris(baglanti, "mp", MP_PAROLA) == kimlik.Kullanici("mp", "mp")
    assert kimlik.giris(baglanti, "gk", GK_PAROLA) == kimlik.Kullanici("gk", "giris_kalite")
    assert kimlik.giris(baglanti, "mp", GK_PAROLA) is None  # parolalar karışmaz


def test_deneme_parolalariyla_giris_yapilamaz(baglanti):
    kimlik.ortamdan_kullanicilar(gecerli_ortam(), baglanti)
    assert kimlik.giris(baglanti, "mp", "mp-ornek-parola") is None
    assert kimlik.giris(baglanti, "gk", "gk-ornek-parola") is None


def test_kullanici_adlari_ortamdan_okunur(baglanti):
    ortam = gecerli_ortam(MALZEME_KABUL_MP_KULLANICI="nida", MALZEME_KABUL_GK_KULLANICI="kalite1")
    kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert set(kimlik.kullanicilar(baglanti)) == {kimlik.Kullanici("nida", "mp"), kimlik.Kullanici("kalite1", "giris_kalite")}
    assert kimlik.giris(baglanti, "nida", MP_PAROLA) is not None
    assert kimlik.giris(baglanti, "mp", MP_PAROLA) is None


@pytest.mark.parametrize("gk_adi", ["ortak", "mp"])
def test_iki_rol_icin_ayni_kullanici_adi_hata_verir(baglanti, gk_adi):
    ortam = gecerli_ortam(MALZEME_KABUL_MP_KULLANICI="ortak" if gk_adi == "ortak" else "", MALZEME_KABUL_GK_KULLANICI=gk_adi)
    with pytest.raises(kimlik.KimlikHatasi, match="KULLANICI"):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_bosluklu_ayni_kullanici_adi_da_hata_verir(baglanti):
    ortam = gecerli_ortam(MALZEME_KABUL_MP_KULLANICI="nida", MALZEME_KABUL_GK_KULLANICI="  nida  ")
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


# Demo onayı planı adım 7: "ornek-veri" örnek verinin demo onaylayanıdır (veritabani.ORNEK_ONAYLAYAN);
# gerçek bir hesap bu adı alırsa onun onayları örnek veriyle karışırdı.


@pytest.mark.parametrize("degisken", ["MALZEME_KABUL_MP_KULLANICI", "MALZEME_KABUL_GK_KULLANICI"])
@pytest.mark.parametrize("ad", ["ornek-veri", "ORNEK-VERI", "  Ornek-Veri  "])
def test_ilk_kurulum_ayrilmis_adi_reddeder(baglanti, degisken, ad):
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(gecerli_ortam(**{degisken: ad}), baglanti)
    assert kullanici_sayisi(baglanti) == 0  # ya ikisi ya hiçbiri


def test_ilk_kurulum_ayrilmis_ada_benzeyen_adi_kabul_eder(baglanti):
    olusan = kimlik.ortamdan_kullanicilar(gecerli_ortam(MALZEME_KABUL_MP_KULLANICI="ornek-veri2"), baglanti)
    assert kimlik.Kullanici("ornek-veri2", "mp") in olusan


# --- (d) Docker secrets: *_DOSYASI --------------------------------------------------------


def test_parolalar_dosyadan_okunabilir(baglanti, tmp_path):
    (tmp_path / "mp_parola").write_text(MP_PAROLA + "\n", encoding="utf-8")  # sonda satır sonu atılır
    (tmp_path / "gk_parola").write_text(GK_PAROLA, encoding="utf-8")
    ortam = {
        "MALZEME_KABUL_MP_PAROLASI_DOSYASI": str(tmp_path / "mp_parola"),
        "MALZEME_KABUL_GK_PAROLASI_DOSYASI": str(tmp_path / "gk_parola"),
    }
    kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kimlik.giris(baglanti, "mp", MP_PAROLA) == kimlik.Kullanici("mp", "mp")
    assert kimlik.giris(baglanti, "gk", GK_PAROLA) == kimlik.Kullanici("gk", "giris_kalite")


def test_dosya_ve_degisken_karisik_kullanilabilir(baglanti, tmp_path):
    (tmp_path / "gk_parola").write_text(GK_PAROLA + "\n", encoding="utf-8")
    ortam = {"MALZEME_KABUL_MP_PAROLASI": MP_PAROLA, "MALZEME_KABUL_GK_PAROLASI_DOSYASI": str(tmp_path / "gk_parola")}
    kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kimlik.giris(baglanti, "gk", GK_PAROLA) is not None


def test_olmayan_parola_dosyasi_hata_verir_ve_kullanici_olusmaz(baglanti, tmp_path):
    ortam = {"MALZEME_KABUL_MP_PAROLASI": MP_PAROLA, "MALZEME_KABUL_GK_PAROLASI_DOSYASI": str(tmp_path / "yok")}
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


def test_dosyadan_okunan_zayif_parola_da_reddedilir(baglanti, tmp_path):
    (tmp_path / "mp_parola").write_text("mp-ornek-parola\n", encoding="utf-8")
    ortam = gecerli_ortam(MALZEME_KABUL_MP_PAROLASI_DOSYASI=str(tmp_path / "mp_parola"))
    del ortam["MALZEME_KABUL_MP_PAROLASI"]
    with pytest.raises(kimlik.KimlikHatasi):
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert kullanici_sayisi(baglanti) == 0


@pytest.mark.parametrize("onek", ["MALZEME_KABUL_MP", "MALZEME_KABUL_GK"])
def test_ayni_rol_icin_hem_degisken_hem_dosya_verilirse_hata(baglanti, tmp_path, onek):
    dosya = tmp_path / "parola"
    dosya.write_text("Dosyadaki-Parola-2026\n", encoding="utf-8")
    ortam = gecerli_ortam(**{f"{onek}_PAROLASI_DOSYASI": str(dosya)})  # {onek}_PAROLASI da ayarlı
    with pytest.raises(kimlik.KimlikHatasi, match=f"{onek}_PAROLASI_DOSYASI") as hata:
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert "Dosyadaki-Parola-2026" not in str(hata.value)
    assert kullanici_sayisi(baglanti) == 0


# --- (e) yeniden başlatma: kullanıcı zaten varsa ortam gerekmez -----------------------------


def test_kullanici_varsa_ortam_degiskeni_gerekmez(baglanti):
    kimlik.kullanici_ekle(baglanti, "nida", MP_PAROLA, "mp")
    assert kimlik.ortamdan_kullanicilar({}, baglanti) == []
    assert kimlik.kullanicilar(baglanti) == [kimlik.Kullanici("nida", "mp")]


def test_kullanici_varsa_ortamdaki_parolalar_mevcut_hesaplari_degistirmez(baglanti):
    kimlik.ortamdan_kullanicilar(gecerli_ortam(), baglanti)
    yeni = gecerli_ortam(MALZEME_KABUL_MP_PAROLASI="Baska-Bir-Parola-99")
    assert kimlik.ortamdan_kullanicilar(yeni, baglanti) == []
    assert kimlik.giris(baglanti, "mp", MP_PAROLA) is not None
    assert kimlik.giris(baglanti, "mp", "Baska-Bir-Parola-99") is None


# --- (e2) eski volume: deneme parolalı hesaplar her açılışta yakalanır ---------------------


def test_deneme_parolalari_kimlik_modulunde_tanimli():
    assert {"mp-ornek-parola", "gk-ornek-parola"} <= set(kimlik.DENEME_PAROLALARI)


@pytest.mark.parametrize("ad, deneme, rol", [
    ("mp", "mp-ornek-parola", "mp"),
    ("gk", "gk-ornek-parola", "giris_kalite"),
    ("mp", "gk-ornek-parola", "mp"),          # çapraz: başka rolün deneme parolası da yakalanır
    ("nida.eski", "mp-ornek-parola", "mp"),   # adı değişmiş hesap da yakalanır
])
@pytest.mark.parametrize("ortam_turu", ["bos", "gecerli"])
def test_mevcut_hesapta_deneme_parolasi_varsa_kimlik_hatasi_verir(baglanti, ad, deneme, rol, ortam_turu):
    kimlik.kullanici_ekle(baglanti, ad, deneme, rol)
    ortam = {} if ortam_turu == "bos" else gecerli_ortam()
    with pytest.raises(kimlik.KimlikHatasi) as hata:
        kimlik.ortamdan_kullanicilar(ortam, baglanti)
    assert ad in str(hata.value)  # hangi hesabın sorunlu olduğu söylenir
    assert deneme not in str(hata.value)  # parola söylenmez
    # hesap sessizce değiştirilmez ya da silinmez; yeni hesap da açılmaz
    assert kimlik.kullanicilar(baglanti) == [kimlik.Kullanici(ad, rol)]


def test_deneme_parolali_eski_volume_ornek_kurulumu_her_acilista_reddedilir(baglanti):
    """katalog_kur.py --ornek-kullanicilar ile kurulmuş eski volume: mp ve gk deneme parolalı."""
    kimlik.kullanici_ekle(baglanti, "mp", "mp-ornek-parola", "mp")
    kimlik.kullanici_ekle(baglanti, "gk", "gk-ornek-parola", "giris_kalite")
    for _ in range(2):  # yalnız ilk açılışta değil, her açılışta
        with pytest.raises(kimlik.KimlikHatasi):
            kimlik.ortamdan_kullanicilar(gecerli_ortam(), baglanti)


def test_guclu_parolali_hesaplarin_yanindaki_tek_deneme_hesabi_da_yakalanir(baglanti):
    kimlik.kullanici_ekle(baglanti, "nida", MP_PAROLA, "mp")
    kimlik.kullanici_ekle(baglanti, "gk", "gk-ornek-parola", "giris_kalite")
    with pytest.raises(kimlik.KimlikHatasi, match="gk"):
        kimlik.ortamdan_kullanicilar({}, baglanti)


def test_guclu_parolali_mevcut_hesaplar_deneme_denetiminden_gecer(baglanti):
    kimlik.kullanici_ekle(baglanti, "mp", MP_PAROLA, "mp")
    kimlik.kullanici_ekle(baglanti, "gk", GK_PAROLA, "giris_kalite")
    assert kimlik.ortamdan_kullanicilar({}, baglanti) == []


# --- scripts/ilk_kurulum.py: çıkış kodu ve çıktı ------------------------------------------


def ilk_kurulum(db: Path, ortam_ek: dict[str, str]) -> subprocess.CompletedProcess:
    ortam = {k: v for k, v in os.environ.items() if not k.startswith("MALZEME_KABUL_")}
    ortam.update(ortam_ek)
    assert (KOK / "scripts/ilk_kurulum.py").is_file(), "scripts/ilk_kurulum.py yok"
    return subprocess.run([sys.executable, str(KOK / "scripts/ilk_kurulum.py"), "--db", str(db)],
                          capture_output=True, text=True, env=ortam, cwd=db.parent, timeout=120)


def db_kullanicilari(db: Path) -> list[kimlik.Kullanici]:
    with sqlite3.connect(db) as b:
        return kimlik.kullanicilar(b)


def test_betik_parola_yokken_sifirdan_farkli_doner_ve_degiskeni_soyler(tmp_path):
    db = tmp_path / "katalog.sqlite"
    s = ilk_kurulum(db, {})
    assert s.returncode != 0
    assert "MALZEME_KABUL_MP_PAROLASI" in s.stdout + s.stderr
    assert not db.exists() or db_kullanicilari(db) == []


def test_betik_zayif_parolada_sifirdan_farkli_doner(tmp_path):
    db = tmp_path / "katalog.sqlite"
    s = ilk_kurulum(db, gecerli_ortam(MALZEME_KABUL_GK_PAROLASI="gk-ornek-parola"))
    assert s.returncode != 0
    assert "MALZEME_KABUL_GK_PAROLASI" in s.stdout + s.stderr  # hangi parolanın reddedildiği söylenir
    assert not db.exists() or db_kullanicilari(db) == []


def test_betik_gecerli_parolalarla_sifir_doner_ve_kullanicilari_kurar(tmp_path):
    db = tmp_path / "katalog.sqlite"
    s = ilk_kurulum(db, gecerli_ortam())
    assert s.returncode == 0, s.stderr
    assert set(db_kullanicilari(db)) == {kimlik.Kullanici("mp", "mp"), kimlik.Kullanici("gk", "giris_kalite")}


def test_betik_kullanici_varsa_parolasiz_sifir_doner(tmp_path):
    db = tmp_path / "katalog.sqlite"
    with sqlite3.connect(db) as b:
        kimlik.kullanici_ekle(b, "nida", MP_PAROLA, "mp")
    s = ilk_kurulum(db, {})
    assert s.returncode == 0, s.stderr


def test_betik_eski_volumede_deneme_parolasi_varsa_sifirdan_farkli_doner_ve_parolayi_yazmaz(tmp_path):
    db = tmp_path / "katalog.sqlite"
    with sqlite3.connect(db) as b:
        kimlik.kullanici_ekle(b, "mp", "mp-ornek-parola", "mp")
        kimlik.kullanici_ekle(b, "gk", "gk-ornek-parola", "giris_kalite")
    for ortam_ek in ({}, gecerli_ortam()):
        s = ilk_kurulum(db, ortam_ek)
        assert s.returncode != 0, s.stdout
        cikti = s.stdout + s.stderr
        assert "ornek-parola" not in cikti
        assert MP_PAROLA not in cikti and GK_PAROLA not in cikti
    assert set(db_kullanicilari(db)) == {kimlik.Kullanici("mp", "mp"), kimlik.Kullanici("gk", "giris_kalite")}


def test_betik_deneme_parolali_hesabin_adini_soyler(tmp_path):
    db = tmp_path / "katalog.sqlite"
    with sqlite3.connect(db) as b:
        kimlik.kullanici_ekle(b, "nida.eski", "gk-ornek-parola", "mp")
    s = ilk_kurulum(db, {})
    assert s.returncode != 0
    assert "nida.eski" in s.stdout + s.stderr
    assert "gk-ornek-parola" not in s.stdout + s.stderr


def test_betik_ayni_rol_icin_degisken_ve_dosya_birlikte_verilince_sifirdan_farkli_doner(tmp_path):
    (tmp_path / "mp").write_text(MP_PAROLA + "\n", encoding="utf-8")
    s = ilk_kurulum(tmp_path / "katalog.sqlite", gecerli_ortam(MALZEME_KABUL_MP_PAROLASI_DOSYASI=str(tmp_path / "mp")))
    assert s.returncode != 0
    assert "MALZEME_KABUL_MP_PAROLASI_DOSYASI" in s.stdout + s.stderr
    assert MP_PAROLA not in s.stdout + s.stderr


def test_betik_yalniz_bosluk_parolada_sifirdan_farkli_doner(tmp_path):
    db = tmp_path / "katalog.sqlite"
    s = ilk_kurulum(db, gecerli_ortam(MALZEME_KABUL_GK_PAROLASI=" " * 12))
    assert s.returncode != 0
    assert "MALZEME_KABUL_GK_PAROLASI" in s.stdout + s.stderr
    assert not db.exists() or db_kullanicilari(db) == []


# --- (f) parolalar çıktıya yazılmaz -----------------------------------------------------


def test_basarili_kurulumda_parolalar_ciktida_gecmez(tmp_path):
    s = ilk_kurulum(tmp_path / "katalog.sqlite", gecerli_ortam())
    assert s.returncode == 0, s.stderr
    assert MP_PAROLA not in s.stdout + s.stderr
    assert GK_PAROLA not in s.stdout + s.stderr


def test_reddedilen_parola_ciktida_gecmez(tmp_path):
    kisa = "Kisa-Par0la"  # 11 karakter
    s = ilk_kurulum(tmp_path / "katalog.sqlite", gecerli_ortam(MALZEME_KABUL_MP_PAROLASI=kisa))
    assert s.returncode != 0
    assert "MALZEME_KABUL_MP_PAROLASI" in s.stdout + s.stderr
    assert kisa not in s.stdout + s.stderr
    assert GK_PAROLA not in s.stdout + s.stderr


def test_dosyadan_okunan_parola_ciktida_gecmez(tmp_path):
    (tmp_path / "mp").write_text(MP_PAROLA + "\n", encoding="utf-8")
    s = ilk_kurulum(tmp_path / "katalog.sqlite",
                    {"MALZEME_KABUL_MP_PAROLASI_DOSYASI": str(tmp_path / "mp"), "MALZEME_KABUL_GK_PAROLASI": GK_PAROLA})
    assert s.returncode == 0, s.stderr
    assert MP_PAROLA not in s.stdout + s.stderr


# --- (g) docker/baslat.sh: parola yoksa Streamlit başlamaz -------------------------------


@pytest.fixture
def sahte_streamlit(tmp_path):
    """PATH'e konan sahte `streamlit`: çağrıldığını ve argümanlarını bir dosyaya yazar."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    iz = tmp_path / "streamlit_cagrildi"
    betik = bin_ / "streamlit"
    betik.write_text(f'#!/bin/sh\necho "$@" > "{iz}"\nexit 0\n', encoding="utf-8")
    betik.chmod(0o755)
    return bin_, iz


def baslat(tmp_path: Path, bin_: Path, ortam_ek: dict[str, str], kabuk: str = "sh") -> subprocess.CompletedProcess:
    ortam = {k: v for k, v in os.environ.items() if not k.startswith("MALZEME_KABUL_")}
    ortam.update({
        "PATH": f"{bin_}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{ortam.get('PATH', '')}",
        "MALZEME_KABUL_KOK": str(KOK),
        "MALZEME_KABUL_DB": str(tmp_path / "veri" / "katalog.sqlite"),
        "MALZEME_KABUL_YUKLEME": str(tmp_path / "veri" / "yuklenen"),
    })
    (tmp_path / "veri").mkdir(exist_ok=True)
    ortam.update(ortam_ek)
    return subprocess.run([kabuk, str(KOK / "docker/baslat.sh")], capture_output=True, text=True,
                          env=ortam, cwd=tmp_path, timeout=300)


def test_baslat_parola_yoksa_streamliti_cagirmaz_ve_sifirdan_farkli_cikar(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    s = baslat(tmp_path, bin_, {})
    assert s.returncode != 0
    assert not iz.exists(), "parola yokken Streamlit başlatıldı"
    assert "MALZEME_KABUL_MP_PAROLASI" in s.stdout + s.stderr


def test_baslat_deneme_kullanicilari_istense_bile_streamliti_cagirmaz(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    s = baslat(tmp_path, bin_, {"MALZEME_KABUL_ORNEK_KULLANICILAR": "1"})
    assert s.returncode != 0
    assert "MALZEME_KABUL_MP_PAROLASI" in s.stdout + s.stderr
    assert not iz.exists()
    db = tmp_path / "veri" / "katalog.sqlite"
    assert not db.exists() or db_kullanicilari(db) == []  # deneme kullanıcıları Docker yolunda açılmaz


def test_baslat_zayif_parolada_streamliti_cagirmaz(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    s = baslat(tmp_path, bin_, gecerli_ortam(MALZEME_KABUL_MP_PAROLASI="mp-ornek-parola"))
    assert s.returncode != 0
    assert "MALZEME_KABUL_MP_PAROLASI" in s.stdout + s.stderr
    assert "mp-ornek-parola" not in s.stdout + s.stderr
    assert not iz.exists()


def test_baslat_parola_varsa_streamliti_cagirir_ve_kullanicilari_kurar(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    s = baslat(tmp_path, bin_, gecerli_ortam())
    assert s.returncode == 0, s.stdout + s.stderr
    assert iz.exists(), "geçerli parolayla Streamlit başlatılmadı"
    assert "run" in iz.read_text(encoding="utf-8") and "uygulama.py" in iz.read_text(encoding="utf-8")
    assert MP_PAROLA not in s.stdout + s.stderr and GK_PAROLA not in s.stdout + s.stderr
    db = tmp_path / "veri" / "katalog.sqlite"
    assert set(db_kullanicilari(db)) == {kimlik.Kullanici("mp", "mp"), kimlik.Kullanici("gk", "giris_kalite")}


def test_baslat_yeniden_baslatmada_parola_gerekmez(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    assert baslat(tmp_path, bin_, gecerli_ortam()).returncode == 0
    iz.unlink()
    s = baslat(tmp_path, bin_, {})
    assert s.returncode == 0, s.stdout + s.stderr
    assert iz.exists()


def test_baslat_eski_volumede_deneme_parolasi_varsa_streamliti_cagirmaz(tmp_path, sahte_streamlit):
    bin_, iz = sahte_streamlit
    db = tmp_path / "veri" / "katalog.sqlite"
    db.parent.mkdir()
    with sqlite3.connect(db) as b:
        kimlik.kullanici_ekle(b, "mp", "mp-ornek-parola", "mp")
        kimlik.kullanici_ekle(b, "gk", "gk-ornek-parola", "giris_kalite")
    for ortam_ek in ({}, gecerli_ortam()):  # parolasız yeniden başlatma da, parolalı da
        s = baslat(tmp_path, bin_, ortam_ek)
        assert s.returncode != 0, s.stdout + s.stderr
        assert not iz.exists(), "deneme parolalı hesap varken Streamlit başlatıldı"
        assert "ornek-parola" not in s.stdout + s.stderr


def test_baslat_sh_ile_bash_olmadan_calisir(tmp_path, sahte_streamlit):
    """ENTRYPOINT `sh` kullanır; betik bash'e özgü sözdizimine dayanmamalı."""
    sh = shutil.which("dash") or shutil.which("sh")
    bin_, iz = sahte_streamlit
    s = baslat(tmp_path, bin_, gecerli_ortam(), kabuk=sh)
    assert s.returncode == 0, s.stdout + s.stderr
    assert iz.exists()


# --- katalog_kur.py --ornek-kullanicilar Docker'da reddedilir -------------------------------
#
# Seçilen işaret: MALZEME_KABUL_DOCKER=1 (Dockerfile ENV'de ayarlanır). MALZEME_KABUL_KOK'a
# bakılmaz; o değişken yerelde ve testlerde de ayarlanır.


def katalog_kur(db: Path, argumanlar: list[str], ortam_ek: dict[str, str]) -> subprocess.CompletedProcess:
    ortam = {k: v for k, v in os.environ.items() if not k.startswith("MALZEME_KABUL_")}
    ortam.update(ortam_ek)
    return subprocess.run([sys.executable, str(KOK / "scripts/katalog_kur.py"), "--db", str(db), *argumanlar],
                          capture_output=True, text=True, env=ortam, cwd=db.parent, timeout=120)


@pytest.mark.parametrize("ek", [{}, {"MALZEME_KABUL_KOK": "/uygulama"}])
def test_katalog_kur_dockerda_ornek_kullanicilari_reddeder(tmp_path, ek):
    db = tmp_path / "katalog.sqlite"
    s = katalog_kur(db, ["--ornek-kullanicilar"], {"MALZEME_KABUL_DOCKER": "1", **ek})
    assert s.returncode != 0, s.stdout
    assert "ornek-parola" not in s.stdout + s.stderr
    assert not db.exists() or db_kullanicilari(db) == []


def test_katalog_kur_dockerda_ornek_veri_ve_kullanici_birlikte_istenince_de_kullanici_acmaz(tmp_path):
    db = tmp_path / "katalog.sqlite"
    s = katalog_kur(db, ["--ornek", "--ornek-kullanicilar"], {"MALZEME_KABUL_DOCKER": "1"})
    assert s.returncode != 0, s.stdout
    assert not db.exists() or db_kullanicilari(db) == []


def test_katalog_kur_dockerda_ornek_veriyi_kullanicisiz_kurar(tmp_path):
    """baslat.sh `--ornek` ile çağırır; Docker işareti bunu engellememeli."""
    db = tmp_path / "katalog.sqlite"
    s = katalog_kur(db, ["--ornek"], {"MALZEME_KABUL_DOCKER": "1"})
    assert s.returncode == 0, s.stderr
    assert db_kullanicilari(db) == []


def test_katalog_kur_yerelde_ornek_kullanicilari_acar(tmp_path):
    """Docker işareti yokken yerel deneme akışı (tests/test_arayuz.py) çalışmaya devam eder."""
    db = tmp_path / "katalog.sqlite"
    s = katalog_kur(db, ["--ornek-kullanicilar"], {})
    assert s.returncode == 0, s.stderr
    with sqlite3.connect(db) as b:
        assert kimlik.giris(b, "mp", "mp-ornek-parola") == kimlik.Kullanici("mp", "mp")
