# Arayüz sözleşmesi

Durum: 25 Kasım 2026. Okuyanlar: Nida (proje sahibi) ve Codex (Streamlit
ekranları ve bağımsız inceleme).

Bu doküman, Streamlit arayüzünün (`src/malzeme_kabul/arayuz/uygulama.py`)
çağırdığı fonksiyonları, girdilerini, çıktılarını, hatalarını ve yan
etkilerini bir sözleşme olarak tarif eder. Anlatılan davranış `main`
dalındaki koddur. Bilgiler koddan çıkarıldı. Testin bu dokümanın hangi
kısımlarını koda karşı denetlediği, hangilerini denetlemediği en sondaki
"Sözleşmenin korunması" bölümünde yazar.

## Kapsam ve katman sınırı

- **Arayüz iş kuralı içermez.** Kabul/red kararını kural katmanı verir:
  satır kararları ve `parti_karari` `kural/karar_motoru`'ndadır. Görevler
  şöyle dağılır:
  - katalogla bağlama: `hat/katalog_karari`
  - belge → okuma → kanıt → karar akışı: `hat/hibrit_hat`
  - revizyon işaretleme: `hat/revizyon_etkisi`
  - saklama: `katalog/veritabani`
  - zincirli kayıt: `kayit/denetim_kaydi`
  - mühendis düzeltme olayları, etiket adayı ve düzeltme panosu:
    `kayit/duzeltme_kaydi`

  Katman adları docs/mimari.md "Klasör yapısı" bölümüyle aynıdır.
- **Arayüz yalnız bu dokümandaki adları çağırır.** Ekranın arkasındaki işler
  `arayuz/ekran_verisi.py`'de durur ve Streamlit olmadan test edilir. Kimlik
  işleri `arayuz/kimlik.py`'dedir. Streamlit'e yalnız `uygulama.py` bağımlıdır.
- **Bağlantı.** Her Streamlit çalıştırması (`main`) kendi `Katalog`'unu
  `with Katalog(DB) as katalog:` ile açar ve çalıştırma bitince kapatır;
  `st.rerun` istisnasında ve defter kurulamadığında da kapanır. Bağlantı
  oturumlar (iplikler) arasında paylaşılmaz. Çalıştırma içinde aynı SQLite
  bağlantısını (`katalog.baglanti`, bir `sqlite3.Connection` özniteliği) hem
  `sema_eksikleri`'ne ve `DenetimKaydi`'ya (uygulama içi `baglan` yardımcısı)
  hem `kimlik.giris`'e verir. Durum değişikliği ile denetim kaydının tek
  işlem olması bu ortak bağlantıya dayanır. Katalog, denetim kaydı ve
  kullanıcılar aynı dosyada durur (bkz. "Ortam değişkenleri").
- **Birim ve sınır.** Birim dönüşümünü ve sınır karşılaştırmasını arayüz de
  dil modeli de hiçbir zaman yapmaz. Bu işler `kural/` katmanındaki Python
  kodunundur.
- **Dış servis yok.** Hibrit modda dil modeli istemcisi yalnız localhost'a
  bağlanır.
- **Hata gösterimi.** Arayüz her istisnayı yakalamaz. Ne yakalandığı çağrıya
  göre değişir; tam liste "Hatalar" bölümündeki tablodadır. Yakalanmayan bir
  istisna Streamlit'in kendi hata sayfasına düşer. Her fonksiyonun
  "Hatalar" kısmında, arayüzün o istisnayı yakalayıp yakalamadığı ayrıca
  yazar.

## Ekran → fonksiyon eşlemesi

| Ekran (kimlik.EKRANLAR anahtarı) | Rol | Çağrılanlar |
|---|---|---|
| giriş (oturum yok) | herkes | `kimlik.giris` |
| `standart`: Standart yükle | `mp` | `ekran_verisi.standart_yukle`, `Katalog.taslaklar` |
| `taslak`: Taslağı düzelt ve onayla | `mp` | `Katalog.taslaklar(yalniz_acik=True)`, `ekran_verisi.test_tablosu`, `TABLO_SUTUNLARI`, `tablodan_dokuman`, `taslak_duzelt`, `taslak_onayla`, `uygulama.etiket_adayi_kaydet` (içinde `duzeltme_kaydi.etiket_adayi_yaz`) |
| `revizyon`: Revizyon farkı ve M&P incelemesi | `mp` | `ekran_verisi.hazir_revizyon_raporlari`, `revizyon_izinli_mi`, `revizyon_raporu`, `revizyon_etkisi.yeni_revizyon_yukle`, `mp_bekleyenler`, `Katalog.malzeme`, `mp_incelemesini_kapat` |
| `giris`: Giriş kalite: CoC kontrolü | `giris_kalite` | `Katalog.malzemeler`, `gecerli_dokuman`, `partiler`, `onayli_tedarikciler`, `ekran_verisi.parti_hazirla`, `json_sertifika_karari`, `hibrit_hat.sertifika_hatti`, `karar_tablosu`, `PARTI_ETIKETI`, `surum_etiketi`, `karar_basligi`, `DEMO_ETIKETI`; düzeltme formu: `PARTI_DURUMLARI`, `katalog_karari.karari_duzelt` |
| `depo`: Depo: partiler ve raf ömrü | `mp`, `giris_kalite` | `ekran_verisi.depo_tablosu`, `RAF_ETIKETI`, `DEMO_ETIKETI` |
| `pano`: Düzeltme panosu | `mp` | `duzeltme_kaydi.duzeltme_panosu` |
| kenar çubuğu (her ekran) | herkes | `kimlik.yetkili_mi`, `kimlik.EKRANLAR`, `denetim_kaydi.sema_eksikleri` (defter kurulmadan önce), `DenetimKaydi.zinciri_dogrula` |

## Bağlantı ve kimlik

### `malzeme_kabul.katalog.veritabani.Katalog`

SQLite malzeme kataloğu. Şunları tutar:

- standartlar ve malzemeler
- onaylı kabul dokümanı sürümleri (değiştirilemez; tetikleyici yalnız
  uygulamanın kendi UPDATE/DELETE'ine karşı korur, bkz. "Bilinen açıklar"
  madde 7)
- taslaklar
- onaylı tedarikçiler
- partiler

Karar vermez; yalnız saklar ve getirir. `baglanti` özniteliği açıktır
(`sqlite3.Connection`, `row_factory = sqlite3.Row`). Arayüz bu özniteliği
yalnız `DenetimKaydi`'ya, `sema_eksikleri`'ne ve `kimlik.giris`'e vermek
için okur; bu bağlantıyla
doğrudan SQL çalıştırmaz.

### `malzeme_kabul.katalog.veritabani.Katalog.__init__(yol)`

**Girdiler**

- `yol` (`str | Path`, isteğe bağlı, varsayılan `":memory:"`): SQLite dosya
  yolu. Arayüz buraya `MALZEME_KABUL_DB` değerini verir.

**Çıktı**: `Katalog` nesnesi; `yol` (str) ve `baglanti` öznitelikleri dolu
gelir.

**Hatalar**: `sqlite3` hataları (ör. dosya açılamıyor). Arayüz bunları
yakalamaz.

**Yan etkiler**:

- dosya yolunun üst klasörünü oluşturur
- şemayı kurar (`CREATE TABLE IF NOT EXISTS`)
- eski veritabanlarına eksik sütunları veri kaybetmeden ekler:
  `partiler.kap_turu`, `partiler.mp_inceleme`, `malzemeler.mp_inceleme`
- demo onayı göçü: `dokuman_surumleri.demo_onayi` sütunu yoksa tek bir
  işlemde (`BEGIN IMMEDIATE` ... COMMIT; yazma kilidi baştan alınır) sütunu ekler (`INTEGER NOT NULL DEFAULT 0
  CHECK (demo_onayi IN (0, 1))`), değiştirilemezlik tetikleyicisini
  (`dokuman_surumu_degistirilemez`) düşürür, `onaylayan = 'ornek-veri'`
  satırlarını `demo_onayi = 1` yapar ve tetikleyiciyi şemadaki tanımla
  yeniden kurar. Sütun işlem içinde yeniden denetlenir: aynı anda açan
  başka bir bağlantı göçü bitirdiyse işlem hiçbir şey yapmadan biter
  ("duplicate column" hatası olmaz). Bir adım düşerse işlem hâlâ açıksa
  ROLLBACK yapılır: sütun eklenmemiş, tetikleyici yerinde kalır; özgün hata
  yukarı iletilir (arayüz yakalamaz) ve sonraki açılış göçü yeniden dener.
  Kilit alınamazsa `sqlite3.OperationalError` ("database is locked") olduğu
  gibi iletilir. Göç açık bir işlemin içinde çağrılırsa o işlemi bitirmez,
  `KatalogHatasi` verir. Sütun varsa göç çalışmaz.

Arayüz her Streamlit yeniden çalıştırmasında yeni bir `Katalog`'u
`with katalog:` bloğuyla açar; blok bitince `kapat()` bağlantıyı kapatır
(bkz. "Kapsam ve katman sınırı", **Bağlantı**).

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi`

Zincirli (SHA-256) denetim kaydı. Kayıt türleri `karar`, `onay` ve
`duzeltme`'dir. Kayıtlara yalnız ekleme yapılır. Şemadaki üç tetikleyici
(`denetim_kaydi.TETIKLEYICILER`) UPDATE'i, DELETE'i ve var olan bir sıra ya
da özetle INSERT'i reddeder; sonuncusu (BEFORE INSERT) `INSERT OR REPLACE` /
`REPLACE INTO` ile kayıt silinmesini de engeller. Dosyaya yazabilen biri
tetikleyicileri `DROP TRIGGER` ile kaldırarak ya da dosyayı doğrudan
düzenleyerek bunu aşabilir (bkz. "Bilinen açıklar" madde 7). Her kaydın
özeti bir önceki kaydın özetini içerir. Arayüz bu sınıfa doğrudan kayıt
yazmaz; kayıtları aşağıdaki hat ve ekran verisi fonksiyonları yazar.

Kayıt ekleme (`ekle`) şunları denetler ve aykırılıkta `DenetimHatasi` verir:
kayıt türü, boş olmayan kullanıcı, metin alanlarının tipi ve `zaman`.
`zaman` verilirse saat dilimli ISO 8601 olmalıdır; bir önceki kaydın
zamanından eski olamaz (monoton) ve şimdiden en çok `ILERI_ZAMAN_PAYI`
(5 dakika) ileride olabilir. Verilmezse UTC şimdi yazılır. İçerik katı
JSON'dur (NaN/Infinity `ValueError`). Bağlantıda açık bir işlem varsa kayıt
o işleme SAVEPOINT ile katılır; böylece durum değişikliği ile kaydı tek
işlemde yazılır.

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.__init__(baglanti)`

**Girdiler**

- `baglanti` (`sqlite3.Connection | str | Path`, isteğe bağlı, varsayılan
  `":memory:"`): var olan bir bağlantı ya da dosya yolu. Arayüz
  `katalog.baglanti` verir; bu durumda `kapat()` bağlantıyı kapatmaz.

**Çıktı**: `DenetimKaydi` nesnesi.

**Hatalar**

- `DenetimHatasi`: verilen bağlantıda açık bir işlem var
  (`baglanti.in_transaction`). Şema betiği (`executescript`) o işlemi
  sessizce bitireceği için defter işlem dışında kurulmalıdır. Arayüz
  yakalamaz; `main` defteri işlem açılmadan kurduğu için olağan akışta
  oluşmaz.
- `sqlite3` hataları (ör. dosya açılamıyor, veritabanı okunamıyor). Arayüz
  yakalamaz.

**Yan etkiler**:

- bağlantının `row_factory`'sini `sqlite3.Row` yapar
- `denetim_kaydi` tablosunu ve üç tetikleyicisini kurar
  (`CREATE ... IF NOT EXISTS`). Eksik bir tetikleyici sessizce yeniden
  yaratılır; bu yüzden arayüz eksikleri defteri kurmadan önce
  `sema_eksikleri` ile okur.

### `malzeme_kabul.kayit.denetim_kaydi.sema_eksikleri(baglanti)`

Denetim kaydı şemasında eksik olan nesneleri bulur. Arayüz bunu her
çalıştırmada, `DenetimKaydi` kurulmadan önce `katalog.baglanti` ile çağırır
(uygulama içi `baglan` yardımcısı). Sonuç kenar çubuğundaki zincir yazısına
(uygulama içi `zincir_durumu`) geçer: liste boş değilse kenar çubuğu zinciri
doğrulamadan "Denetim zinciri: BOZUK (şema: eksik ...)" yazar.
`scripts/denetim_dogrula.py` aynı denetimi salt okunur bağlantıyla yapar.

**Girdiler**

- `baglanti` (`sqlite3.Connection`, zorunlu): denetim kaydının durduğu
  bağlantı. Arayüzde `katalog.baglanti`. Salt okunur bir bağlantı da
  olabilir.

**Çıktı**: `list[str]`: eksik nesneler, şu sırayla:
`"tablo denetim_kaydi"` (tablo yoksa), ardından `TETIKLEYICILER`
sırasıyla her eksik tetikleyici için `"tetikleyici <ad>"`
(`denetim_kaydi_degistirilemez`, `denetim_kaydi_silinemez`,
`denetim_kaydi_uzerine_yazilamaz`). Boş liste şemanın tam olduğunu gösterir.

**Hatalar**: `sqlite3.DatabaseError`: veritabanı okunamıyor (ör. dosya
SQLite değil). Arayüz yakalamaz; `denetim_dogrula.py` yakalar ve zinciri
bozuk sayar.

**Yan etkiler**: yok; yalnız `sqlite_master`'ı okur. Şemayı kurmaz ya da
onarmaz.

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.zinciri_dogrula(beklenen_son_ozet)`

Zinciri baştan sona doğrular. Arayüz bunu kenar çubuğunda (uygulama içi
`zincir_durumu`) yalnız `sema_eksikleri` boş döndüyse ve argümansız çağırır;
`gecerli` alanına göre "sağlam" ya da "BOZUK" yazar. Şemada eksik varsa
zinciri doğrulamadan "BOZUK" yazar (bkz. `sema_eksikleri`).

**Girdiler**

- `beklenen_son_ozet` (`str | None`, isteğe bağlı, varsayılan `None`):
  dışarıda saklanmış son özet. Verilirse zincirin bu özetle bittiği de
  denetlenir; sondan silme ya da zincirin baştan yazılması böyle yakalanır.

**Çıktı**: `DogrulamaSonucu` (dondurulmuş dataclass):

- `gecerli` (`bool`)
- `kayit_sayisi` (`int`): bozukluğa kadar doğrulanan kayıt sayısı
- `bozuk_sira` (`int | None`): ilk bozuk kaydın sırası. Bütün kayıtlar
  tutar ama son özet `beklenen_son_ozet` ile tutmazsa `gecerli=False` ve
  `bozuk_sira=None` döner.
- `neden` (`str | None`): şunlardan biri:
  - sıra atlıyor
  - önceki özet tutmuyor
  - kaydın özeti tutmuyor
  - son özet dışarıdakiyle tutmuyor
- `son_ozet` (`str`): doğrulanan son özet (boş zincirde 64 sıfır)

**Hatalar**: yok. Bozukluk istisna olarak değil, `gecerli=False` olarak
döner.

**Yan etkiler**: yok; yalnız okur.

Sınır: arayüz argümansız çağırdığı için dışarıda saklanan bir özetle
karşılaştırma yapılmaz. Veritabanının tamamını yeniden yazabilen biri
zinciri yeniden hesaplayabilir; bu durumda kenar çubuğu yine "sağlam" der.
"Sağlam" yalnız zincirin kendi içinde tutarlı olduğu anlamına gelir.

### `malzeme_kabul.arayuz.kimlik.Kullanici`

Dondurulmuş dataclass. Alanlar: `ad` (`str`) ve `rol` (`"mp"` ya da
`"giris_kalite"`). Özellikler:

- `rol_adi`: ekranda gösterilen ad ("M&P mühendisi" ya da "Giriş kalite")
- `ekranlar`: rolün yetkili olduğu ekran anahtarları, sıralı bir demet

Arayüz bu nesneyi `st.session_state["kullanici"]` içinde tutar. Alt
fonksiyonlara `kullanici.ad` olarak geçirir.

### `malzeme_kabul.arayuz.kimlik.EKRANLAR`

`dict[str, str]`: ekran anahtarı → ekranda gösterilen ad. Anahtarlar:
`standart`, `taslak`, `revizyon`, `giris`, `depo`, `pano` ("Düzeltme
panosu"). Rol yetkileri `kimlik.YETKILER` içindedir:

- `mp` → standart, taslak, revizyon, depo, pano
- `giris_kalite` → giris, depo

### `malzeme_kabul.arayuz.kimlik.giris(baglanti, ad, parola)`

**Girdiler**

- `baglanti` (`sqlite3.Connection`, zorunlu): kullanıcı tablosunun olduğu
  bağlantı. Arayüzde `katalog.baglanti`.
- `ad` (`str`, zorunlu): kullanıcı adı.
- `parola` (`str`, zorunlu): düz parola. Saklanmaz; PBKDF2-HMAC-SHA256
  özetiyle (200 000 tur, kullanıcı başına 16 bayt tuz) sabit zamanlı
  karşılaştırılır.

**Çıktı**: `Kullanici | None`. Ad ve parola doğruysa `Kullanici`, değilse
`None`. Kullanıcı yoksa da aynı süre harcanır; hangi alanın yanlış olduğu
belli edilmez.

**Hatalar**: yok; yanlış giriş `None` döner.

**Yan etkiler**: `kullanicilar` tablosu yoksa kurar. Denetim kaydına
yazmaz. Deneme sınırı ya da kilitleme yoktur.

### `malzeme_kabul.arayuz.kimlik.yetkili_mi(kullanici, ekran)`

**Girdiler**

- `kullanici` (`Kullanici | None`, zorunlu): oturumdaki kullanıcı.
- `ekran` (`str`, zorunlu): `EKRANLAR` anahtarı.

**Çıktı**: `bool`. Kullanıcı varsa ve rolü ekranı içeriyorsa `True`.
Radyo düğmesi zaten yalnız yetkili ekranları gösterir; arayüz yine de her
ekranı açmadan önce bunu çağırır. Rol denetimi yalnız arayüzde yapılır; alt
katman fonksiyonları rol denetlemez.

**Yan etkiler**: yok.

## M&P ekranı

### `malzeme_kabul.arayuz.ekran_verisi.standart_yukle(katalog, pdf_yolu, kullanici, bolunme_yolu, belge_no, revizyon)`

Standart PDF'inden kural çıkarıcıyla (`cikarim.kural_cikarici.cikar`, dil
modeli kullanılmaz) kabul dokümanı taslağı üretir ve kaydeder. Bunu yapmadan
önce test kümesi kilidini (`standart_izinli_mi`, `data/bolunme.yaml`)
denetler.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `pdf_yolu` (`str | Path`, zorunlu): kaydedilmiş PDF. Dosya adı
  `MIL-PRF-23377K.pdf` biçiminde olmalıdır; belge no ve revizyon buradan
  çıkarılır.
- `kullanici` (`str`, zorunlu): taslağı oluşturan kullanıcının adı.
- `bolunme_yolu` (`Path`, isteğe bağlı, varsayılan `data/bolunme.yaml`):
  test kümesi kilidi için bölünme dosyası. Varsayılan yol
  `ekran_verisi.KOK` üzerinden kurulur: `MALZEME_KABUL_KOK` ayarlıysa o
  klasör (Docker: `/uygulama`), değilse depo kökü
  (`Path(__file__).parents[3]`). Dosya bulunamazsa `standart_yukle`
  "bölünme dosyası yok" der (bkz. "Bilinen açıklar" madde 18).
- `belge_no` (`str | None`, isteğe bağlı, varsayılan `None`) ve `revizyon`
  (`str | None`, isteğe bağlı, varsayılan `None`): ikisi birlikte verilirse
  dosya adı yerine bunlar kullanılır. Arayüz bunları vermez.

**Çıktı**: `Taslak` (dondurulmuş dataclass):

- `id` (`int`)
- `dokuman` (`KabulDokumani`, `durum="taslak"`)
- `olusturan`
- `guncelleme` (UTC ISO zamanı)
- `durum` (`"taslak"`)
- `surum` (`None`)
- `etiket` özelliği, ör. `"taslak 3: MIL-PRF-23377K"`

**Hatalar**

- `KatalogHatasi`: standart bölünmede geliştirme kümesinde değil. Bu üç
  durumda olur: standart test kümesinde ve kilit kapalı, standart bölünmede
  yok, ya da bölünme dosyası yok. Arayüz yakalar.
- `ValueError`: dosya adından belge no ve revizyon çıkarılamadı, PDF
  okunamadı ya da PDF sınırı aşıldı (`PdfSiniriAsildi` bir `ValueError`
  alt sınıfıdır). Arayüz yakalar.
- `FileNotFoundError`: PDF yok. Arayüz yakalamaz. Dosya önce kaydedildiği
  için olağan akışta oluşmaz.

**Yan etkiler**: tek işlemde (`Katalog.islem`) `taslaklar` tablosuna bir
satır ve `duzeltme_tabanlari` tablosuna taslağın tabanını (sistem çıktısı;
üreten `URETEN_KURAL` = `{"yaklasim": "kural", "model": None,
"istem_surumu": None}`) ekler. Biri düşerse ikisi de geri alınır. Denetim
kaydına yazmaz, çünkü taslak henüz karar dayanağı değildir.

### `malzeme_kabul.katalog.veritabani.Katalog.taslaklar(yalniz_acik)`

**Girdiler**

- `yalniz_acik` (`bool`, isteğe bağlı, varsayılan `False`): `True` ise
  yalnız `durum="taslak"` olanlar, yani onaylanmamışlar gelir.

**Çıktı**: `list[Taslak]`, `id` sırasıyla. Alanlar `standart_yukle`
altındadır.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.TABLO_SUTUNLARI`

`list[str]`: düzeltme tablosunun sütun sırası. Sütunlar: `id`, `test_adi`,
`kabul`, `omur_uzatma`, `yeterlilik`, `kriter_turu`, `alt`, `ust`, `birim`,
`orijinal_metin`, `madde`, `sayfa`, `sonuc_kaynagi`. Arayüz `id` sütununu
düzenlemeye kapatır.

### `malzeme_kabul.arayuz.ekran_verisi.test_tablosu(dokuman)`

**Girdiler**

- `dokuman` (`KabulDokumani`, zorunlu): taslağın dokümanı.

**Çıktı**: `list[dict]`; her test bir satırdır ve anahtarlar
`TABLO_SUTUNLARI`'dır. Değerlerin kaynağı:

- `kabul`, `omur_uzatma`, `yeterlilik`: test türlerinin `bool` karşılığı
- `alt`, `ust`, `birim`, `kriter_turu`, `orijinal_metin`: sınır
- `madde`, `sayfa`: kaynak

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.tablodan_dokuman(dokuman, satirlar)`

Düzeltilmiş tabloyu dokümana uygular ve sonucu şemaya göre baştan doğrular
(madde biçimi, birim, sınır yönü).

**Girdiler**

- `dokuman` (`KabulDokumani`, zorunlu): düzeltmeden önceki taslak dokümanı.
- `satirlar` (`list[dict]`, zorunlu): tablodaki satırlar, `test_tablosu`
  biçiminde. Kurallar:
  - Boş hücre (`None`, NaN ya da boş metin) "değer yok" sayılır.
  - `test_adi`, `orijinal_metin`, `madde`, `kriter_turu` ve `sonuc_kaynagi`
    boşsa eski değer korunur.
  - `alt`, `ust`, `birim`, `sayfa` boşsa değer silinir.
  - Yönü `belirsiz` olmayan sınırların yönü yeniden hesaplanır.

**Çıktı**: yeni `KabulDokumani`. Veritabanına yazılmaz.

**Hatalar**

- `ValueError`: şu durumlarda verilir:
  - satır eklenmiş, silinmiş, ya da satırın sırası veya `id`'si değişmiş
  - bir testte hiç test türü seçilmemiş
  - sayı alanına sayı olmayan bir değer girilmiş
  - şema doğrulaması başarısız (`pydantic.ValidationError`, bir
    `ValueError` alt sınıfı)

  Arayüz yakalar.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.taslak_duzelt(katalog, defter, taslak_id, yeni, kullanici, gerekce)`

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `taslak_id` (`int`, zorunlu).
- `yeni` (`KabulDokumani`, zorunlu): `tablodan_dokuman` çıktısı.
- `kullanici` (`str`, zorunlu): düzelten kullanıcının adı.
- `gerekce` (`str | None`, isteğe bağlı, varsayılan `None`): düzeltmenin
  gerekçesi. Düzeltme olaylarına ve denetim kaydı içeriğine yazılır. Arayüz
  "Düzeltme gerekçesi (isteğe bağlı)" kutusundan verir; boşsa `None`.

**Çıktı**: `list[str]`: test düzeyindeki farklar, biçimi
`"<test_id>.<alan>: <eski JSON> → <yeni JSON>"`. Fark yoksa boş liste
döner. Taslak onaylanmış olsa bile, fark yoksa önce farklar karşılaştırıldığı
için hata verilmez, `[]` döner.

**Hatalar**

- `KatalogHatasi`: defter katalogla aynı bağlantıyı paylaşmıyor (hiçbir şey
  yazılmaz), taslak bilinmiyor, fark var ama taslak onaylanmış, ya da
  standart veya revizyon değiştirilmiş. Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): kullanıcı boş ya da kayıt
  zamanı geçersiz. Arayüz yakalar (`ValueError` olarak).
- `sqlite3.OperationalError`: yazma kilidi alınamadı ("database is locked").
  Arayüz yakalar ve "meşgul" iletisini (`MESGUL`) gösterir; hiçbir şey
  yazılmamıştır.

**Yan etkiler**: eski taslak `Katalog.islem` (BEGIN IMMEDIATE) içinde,
yazma kilidi alındıktan sonra okunur; araya başka bir kaydetme girip
farkları bozamaz. Fark yoksa hiçbir şey yazmaz. Fark varsa aynı işlemde
şunları yapar:

1. Taslağın içeriğini ve `guncelleme` zamanını günceller.
2. Denetim kaydına `duzeltme` türünde bir kayıt ekler. İçerik: `taslak`,
   `farklar`, `gerekce`. `dokuman_surumu`: `"<belge><rev> taslak <id>"`.
3. Alan düzeyindeki farkları (`duzeltme_kaydi.alan_farklari`; alanlar
   `duzeltme_alanlari`: F1 ölçümünün alanları ve tablodan düzenlenen ek test
   alanları `EK_ALANLAR` = `test.kaynak.sayfa`, `test.sinir.orijinal_metin`,
   `test.sonuc_kaynagi`) `duzeltme_olaylari` tablosuna `degistir` / `ekle` /
   `sil` olayları olarak yazar. Taslağın tabanı yoksa (eski taslak) o anki
   içerik taban olur, üreten `{"yaklasim": "bilinmiyor"}`.

Herhangi bir adım hata verirse hepsi geri alınır: taslak değişmez, kayıt ve
olay yazılmaz.

### `malzeme_kabul.arayuz.ekran_verisi.taslak_onayla(katalog, defter, taslak_id, kullanici, not_)`

Taslağı yeni ve değiştirilemez bir onaylı kabul dokümanı sürümü yapar.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `taslak_id` (`int`, zorunlu).
- `kullanici` (`str`, zorunlu): onaylayan.
- `not_` (`str | None`, isteğe bağlı, varsayılan `None`): onay notu.

**Çıktı**: `DokumanSurumu` (dondurulmuş dataclass):

- `belge_no`, `revizyon`
- `surum` (`int`, 1'den başlar)
- `dokuman` (`KabulDokumani`, `durum="onaylandi"`)
- `ozet` (içeriğin SHA-256 özeti)
- `onaylayan`, `onay_zamani`, `not_`
- `demo_onayi` (`bool`, varsayılan `False`, son alan): sürüm örnek verinin
  demo onayıyla mı yazıldı (M&P onayı değil). `dokuman_surumleri.demo_onayi`
  sütunundan gelir; sürümün parçasıdır, değiştirilemez. Bu fonksiyonun
  yazdığı sürümde her zaman `False`'tur: taslak onayı demo parametresi
  almaz ve onaylayan `ornek-veri` olamaz.
- `etiket` özelliği, ör. `"MIL-PRF-23377K v2"`

**Hatalar**

- `KatalogHatasi`: defter katalogla aynı bağlantıyı paylaşmıyor (hiçbir şey
  yazılmaz), taslak bilinmiyor, taslak zaten onaylanmış, onaylayan boş ya
  da onaylayan ayrılmış ad `ornek-veri` (`ORNEK_ONAYLAYAN`; yalnız demo
  onayı verebilir). Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): denetim kaydı adımı
  reddetti (ör. kayıt zamanı geçersiz). Arayüz yakalar (`ValueError`
  olarak). Onaylayan boşsa önce `KatalogHatasi` verilir.
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir; hiçbir şey yazılmamıştır.

**Yan etkiler**: tek işlemde (`Katalog.islem`, BEGIN IMMEDIATE) şunları
yapar:

1. Standart yoksa `standartlar`'a ekler; `dokuman_surumleri`'ne yeni sürümü
   ekler.
2. Taslağı `onaylandi` yapar ve sürüm numarasını yazar.
3. Tabanla son doküman arasında net değişmemiş her alan için (ek alanlar
   dahil; boş sayfa alan sayılmaz) `duzeltme_olaylari` tablosuna bir
   `onayla` olayı yazar (taban yoksa son
   doküman taban olur, üreten `bilinmiyor`).
4. Denetim kaydına bir `onay` kaydı ekler. İçerik: `taslak`,
   `dokuman_surumu`, `ozet`, `not`.

Herhangi bir adım hata verirse hepsi geri alınır: sürüm onaylanmaz, taslak
açık kalır, kayıt ve olay yazılmaz.

Etiket adayı bu fonksiyonda yazılmaz. Arayüz onay başarılı olduktan sonra
uygulama içi `etiket_adayi_kaydet` yardımcısını çağırır; o adım düşerse onay
geri alınmaz, uyarı gösterilir.

**Uygulama içi yardımcı `uygulama.etiket_adayi_kaydet`.** İmza:
`etiket_adayi_kaydet(katalog: Katalog, taslak_id: int, klasor: Path) -> tuple[list[Path], str | None]`.
`etiket_adayi_yaz(katalog, taslak_id, klasor)` çağırır. Başarıda
`(yazılan yollar, None)`, hatada `([], uyarı metni)` döner. `OSError`,
`ValueError` (gold klasörü, onaylanmamış taslak ve `KatalogHatasi` dahil) ve
`sqlite3.Error` (kilit ya da bozuk veritabanı) yakalanır. Uyarı metni
istisnanın metnini içerir ve onayın kayıtlı olduğunu söyler. Hiçbir zaman
"kaydedilmedi" demez, çünkü onay kaydedilmiştir. Taslak ekranı etiket
adayını yalnız bu yardımcıyla yazar. Uyarıyı `st.warning`, yolları
`st.caption` ile gösterir. Streamlit'e bağlı olduğu için ayrı başlığı
yoktur. Davranışı tests/test_duzeltme_ekrani.py denetler.

### `malzeme_kabul.kayit.duzeltme_kaydi.etiket_adayi_yaz(katalog, taslak_id, klasor, uzerine_yaz)`

Onaylı taslağın son dokümanını ve düzeltme olaylarını yeni etiketli veri
adayı olarak yazar. Gold'a proje sahibi elle taşır.

**Girdiler**

- `katalog` (`Katalog`, zorunlu): `taslak(id)` ve `baglanti` sağlayan katalog.
- `taslak_id` (`int`, zorunlu): onaylı taslak.
- `klasor` (`str | Path`, zorunlu): hedef klasör. Arayüzde
  `uygulama.ETIKET_ADAYI` (`MALZEME_KABUL_ETIKET_ADAYI`, varsayılan
  `data/calisma/etiket_adaylari`).

- `uzerine_yaz` (`bool`, isteğe bağlı, varsayılan `True`): `False` iken iki
  dosyadan biri varsa hiçbir şey yazılmaz, `FileExistsError` verilir
  (`scripts/etiket_adaylari.py` bunu "atlandı" diye basar). Arayüz vermez.

**Çıktı**: `list[Path]`: yazılan iki dosya (`klasor` altında),
`<belge>_taslak<id>.json` (`KabulDokumani`) ve
`<belge>_taslak<id>.olaylar.jsonl` (her satır bir olay). Dosya adında
`[A-Za-z0-9._-]` dışındaki her karakter `_` olur. Belge numarasındaki `/`,
`\` ya da `..` yol kaçışı yapamaz.

**Hatalar**

- `ValueError`: klasör `gold_yolu_mu` (data/gold/ korunur), taslak
  onaylanmamış, son dosya yolu klasör dışına düşüyor ya da gold'daki bir
  dosyaya işaret eden bağlantı. Hiçbir şey yazılmaz. Arayüz yakalar
  (`etiket_adayi_kaydet`) ve uyarı gösterir.
- `KatalogHatasi`: taslak bilinmiyor. Arayüz yakalar ve uyarı gösterir.
- `FileExistsError`: yalnız `uzerine_yaz=False` iken ve aday zaten varsa.
- `OSError`: dosya yazılamadı. Arayüz yakalar ve uyarı gösterir.

`gold_yolu_mu(yol)` (aynı modülde, public), verilen (mutlak) yolu ve
bağlantıları çözülmüş yolu denetler. Her parça büyük/küçük harfe duyarsız
ve sondaki nokta ile boşluklar atılarak `gold` ile karşılaştırılır.
`GOLD`, `Gold`, `gold.` ve `gold ` gold sayılır. `goldsmith` gold sayılmaz.

**Yan etkiler**: klasörü gerekirse oluşturur ve klasörü oluşturduktan sonra
yeniden denetler. Her dosyayı aynı klasörde geçici bir dosyaya yazar ve
`os.replace` ile yerine taşır. Hedefteki dosya bağlantısı izlenmez,
bağlantının kendisi değiştirilir. `uzerine_yaz=True` iken var olan adayın
üzerine yazar. Veritabanına yazmaz.

### `malzeme_kabul.arayuz.ekran_verisi.hazir_revizyon_raporlari(klasor)`

**Girdiler**

- `klasor` (`Path`, isteğe bağlı, varsayılan `data/cikti`): önceden
  üretilmiş raporların klasörü. Varsayılan yol `ekran_verisi.KOK`
  üzerinden kurulur (`ekran_verisi.HAZIR_RAPORLAR`; bkz.
  `MALZEME_KABUL_KOK`).

**Çıktı**: `dict[str, Path]`: rapor adı → `*_revizyon_farklari.md` yolu.
Rapor adı, dosya adından `_revizyon_farklari` atılarak elde edilir. Ada göre
sıralıdır. Klasör yoksa boş döner.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.revizyon_izinli_mi(eski_ad, yeni_ad, bolunme_yolu)`

İki revizyonun ikisinin de test kümesi kilidinden geçip geçmediğini
denetler. Her iki dosya adı `belge.adlandirma.belge_no_ve_revizyon` ile
ayrıştırılır ve `{belge_no}{revizyon}` (ör. `MIL-PRF-23377K`) önce eski, sonra
yeni için `standart_izinli_mi` ile denetlenir. Arayüz bunu yüklenen dosya
adlarıyla, dosyalar kaydedilmeden önce çağırır.

**Girdiler**

- `eski_ad` (`str | Path`, zorunlu) ve `yeni_ad` (`str | Path`, zorunlu):
  dosya adları ya da yolları (yalnız ad kısmı okunur), ör.
  `MIL-PRF-23377J.pdf`.
- `bolunme_yolu` (`Path`, isteğe bağlı, varsayılan `data/bolunme.yaml`):
  test kümesi kilidi için bölünme dosyası (bkz. `standart_yukle`).

**Çıktı**: `tuple[bool, str]`. İkisi de izinliyse `(True, "")`; değilse
`(False, neden)`; `neden`, ilk reddedilen revizyon için `standart_izinli_mi`
iletisidir (test kümesinde, bölünmede yok ya da bölünme dosyası yok).

**Hatalar**

- `ValueError`: dosya adından belge no veya revizyon çıkarılamadı. Arayüz
  yakalar ve izin verilmemiş gibi gösterir.

**Yan etkiler**: yok; yalnız bölünme dosyasını okur.

### `malzeme_kabul.arayuz.ekran_verisi.revizyon_raporu(eski_pdf, yeni_pdf, dokuman, bolunme_yolu)`

**Girdiler**

- `eski_pdf` (`str | Path`, zorunlu) ve `yeni_pdf` (`str | Path`, zorunlu):
  aynı standardın iki revizyonu. Dosya adları `MIL-PRF-23377J.pdf`
  biçiminde olmalıdır.
- `dokuman` (`KabulDokumani | None`, isteğe bağlı, varsayılan `None`):
  verilirse rapora bu doküman için güncelleme önerileri eklenir. Arayüz bunu
  vermez.
- `bolunme_yolu` (`Path`, isteğe bağlı, varsayılan `data/bolunme.yaml`):
  test kümesi kilidi için bölünme dosyası (bkz. `standart_yukle`).

**Çıktı**: `tuple[str, dict]`: Markdown rapor ve özet sözlüğü
(`RevizyonFarki.ozet()`). Arayüz özeti oturumda tutar ve
`yeni_revizyon_yukle`'ye `fark_ozeti` olarak geçirir.

**Test kümesi kilidi.** Önce iki dosyanın aynı standardın revizyonu olduğu
denetlenir (`ValueError`). Sonra iki revizyon da `revizyon_izinli_mi` ile
denetlenir; biri reddedilirse karşılaştırma yapılmadan `KatalogHatasi`
verilir. Komut satırı betiği (`scripts/revizyon_karsilastir.py`) kilidi
`deney.bolunme.betik_korumasi` ile denetler. Kilit dosya adını okur (bkz.
docs/mimari.md madde 7).

**Hatalar**

- `ValueError`: iki dosya aynı standardın revizyonu değil, dosya adından
  belge no veya revizyon çıkarılamadı, PDF okunamadı ya da PDF sınırı
  aşıldı. Arayüz yakalar.
- `KatalogHatasi`: revizyonlardan biri test kümesinde ve kilit kapalı,
  bölünmede yok, ya da bölünme dosyası yok. Arayüz yakalar.
- `FileNotFoundError`: PDF yok. Arayüz yakalamaz; olağan akışta oluşmaz.

**Yan etkiler**: yok. Veritabanına da denetim kaydına da yazmaz.

### `malzeme_kabul.hat.revizyon_etkisi.yeni_revizyon_yukle(katalog, belge_no, yeni_revizyon, kullanici, baslik, tarih, fark_ozeti)`

Yeni revizyonu kataloğa ekler. Aynı standardın daha eski bir revizyonuna
bağlı malzemeleri ve onların partilerini "M&P incelemesi bekliyor" olarak
işaretler. İşaret kilit değildir: parti durumu değişmez.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `belge_no` (`str`, zorunlu): ör. `MIL-PRF-23377`.
- `yeni_revizyon` (`str`, zorunlu): revizyon harfi; arayüz büyük harfe
  çevirir. Kod tek harf olmasını zorlamaz ve boş metni de reddetmez; her
  metni kabul eder. Boş ya da yalnız boşluktan oluşan girişi yalnız arayüz
  eler (`uygulama.py`, `rev.strip()` koşulu). Sıralama önce uzunluğa, sonra alfabeye göredir (`Z < AA`).
- `kullanici` (`str`, zorunlu).
- `baslik` (`str | None`, isteğe bağlı, varsayılan `None`) ve `tarih`
  (`str | None`, isteğe bağlı, varsayılan `None`): standart bilgisi.
- `fark_ozeti` (`dict | None`, isteğe bağlı, varsayılan `None`):
  `revizyon_raporu`'nun ürettiği özet.

**Çıktı**: `RevizyonEtkisi` (dataclass):

- `belge_no`, `yeni_revizyon`
- `etkilenen_malzemeler` (`list[str]`)
- `etkilenen_partiler` (`list[str]`, `"KOD/LOT"` biçiminde)
- `yeni_etiket` özelliği, ör. `"MIL-PRF-23377L"`

**Hatalar**

- `KatalogHatasi`: kullanıcı boş. Arayüz yakalar (revizyon yükleme formu
  `KatalogHatasi` ve `ValueError` yakalar, `DenetimHatasi` dahil).
  Oturumdaki kullanıcı adı boş olamadığı için bu hata olağan akışta oluşmaz.
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir.

**Yan etkiler**:

- `standartlar`'a ekler; standart varsa dokunmaz.
- Etkilenen malzemelerin ve partilerin `mp_inceleme` alanını doldurur. Her
  malzeme için ayrı işlem yapılır.
- `revizyon_olaylari` tablosuna (yoksa kurar) bir olay satırı ekler.

Denetim kaydına **yazmaz**. Kapatma `mp_incelemesini_kapat` ile kaydedilir.

### `malzeme_kabul.hat.revizyon_etkisi.mp_bekleyenler(katalog)`

**Girdiler**

- `katalog` (`Katalog`, zorunlu).

**Çıktı**: `list[str]`: `mp_inceleme` alanı dolu olan malzeme kodları, koda
göre sıralı.

**Yan etkiler**: yok.

### `malzeme_kabul.katalog.veritabani.Katalog.malzeme(kod)`

**Girdiler**

- `kod` (`str`, zorunlu): malzeme kodu.

**Çıktı**: `Malzeme` (dondurulmuş dataclass):

- `kod`, `belge_no`, `revizyon`, `tip`, `sinif`, `aciklama`
- `mp_inceleme` (`str | None`): doluysa işaret ve nedeni
- `standart_etiketi` özelliği, ör. `"MIL-PRF-23377K"`

**Hatalar**: `KatalogHatasi`: malzeme kodu bilinmiyor. Revizyon ekranında bu
çağrı `try` içinde değildir; kod `mp_bekleyenler` listesinden seçildiği için
olağan akışta oluşmaz. Giriş kalite ekranında `malzeme` çağrısı doğrudan
yapılmaz; `malzemeler()` kullanılır.

**Yan etkiler**: yok.

### `malzeme_kabul.hat.revizyon_etkisi.mp_incelemesini_kapat(katalog, defter, malzeme_kodu, kullanici, karar, not_, yeni_revizyon)`

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `malzeme_kodu` (`str`, zorunlu).
- `kullanici` (`str`, zorunlu).
- `karar` (`"gerek_yok" | "yeni_revizyona_gec"`, zorunlu):
  - `gerek_yok`: malzeme eski revizyonda kalır.
  - `yeni_revizyona_gec`: malzeme yeni revizyona bağlanır.
- `not_` (`str | None`, isteğe bağlı, varsayılan `None`).
- `yeni_revizyon` (`str | None`, isteğe bağlı, varsayılan `None`):
  `yeni_revizyona_gec` için zorunludur.

**Çıktı**: `Kayit`: eklenen denetim kaydı. Alanlar `karari_duzelt`
altındadır.

**Hatalar**

- `KatalogHatasi`: şu durumlarda verilir. Arayüz yakalar.
  - defter katalogla aynı bağlantıyı paylaşmıyor (hiçbir şey yazılmaz)
  - malzeme bilinmiyor
  - bekleyen inceleme yok
  - `yeni_revizyona_gec` için revizyon harfi verilmemiş ya da o revizyonun
    onaylı kabul dokümanı yok
  - karar bilinmiyor
- `DenetimHatasi` (bir `ValueError` alt sınıfı): kullanıcı boş ya da kayıt
  zamanı geçersiz. Arayüz yakalar (`ValueError` olarak). Oturumdaki
  kullanıcı adı boş olamadığı için kullanıcı durumu olağan akışta oluşmaz.
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir; hiçbir şey yazılmamıştır.

**Yan etkiler**: tek işlemde (`Katalog.islem`, BEGIN IMMEDIATE) şunları
yapar:

1. Yalnız `yeni_revizyona_gec`'te: malzemenin revizyonunu günceller.
2. Malzemenin ve partilerinin `mp_inceleme` işaretini kaldırır.
3. Denetim kaydına bir `onay` kaydı ekler. İçerik:
   - `gerek_yok`: `karar`, `malzeme` (standart etiketi), `isaret`, `not`
   - `yeni_revizyona_gec`: `karar`, `eski`, `yeni`, `not`

   `dokuman_surumu` olarak malzemenin (geçişten sonraki) geçerli doküman
   sürümü yazılır; `gerek_yok`'ta onaylı doküman yoksa `None`.

Herhangi bir adım hata verirse hepsi geri alınır: revizyon da işaret de eski
kalır, kayıt yazılmaz.

## Düzeltme panosu

### `malzeme_kabul.kayit.duzeltme_kaydi.duzeltme_panosu(baglanti)`

**Girdiler**

- `baglanti` (`sqlite3.Connection`, zorunlu): katalog bağlantısı
  (`katalog.baglanti`).

**Çıktı**: `PanoOzeti` (dataclass):

- `toplam_alan`, `duzeltilen_alan` (`int`), `oran` (`float`, 0-1): yalnız
  onaylı ve tabanı bilinen (yaklaşımı `bilinmiyor` olmayan) taslaklar
  üzerinden hesaplanır. Bir taslağın alanları, tabanla son dokümanın
  `duzeltme_alanlari` birleşimidir: F1 alanları ve dolu ek alanlar
  (`EK_ALANLAR`). Düzeltilen alan, ikisi arasında net değişen alandır. Aynı
  alanın birden çok düzeltmesi tek sayılır, geri alınan sayılmaz. Aynı
  belgenin her taslağı ayrı sayılır.
- `onay_bekleyen_duzeltme` (`int`): onaylanmamış taslaklardaki net düzeltilmiş
  alan sayısı; orana girmez.
- `tabani_bilinmeyen_taslak` (`int`): tabanı sonradan oluşmuş (üreten
  `bilinmiyor`) onaylı taslak sayısı. Bu taslaklar ana orana ve belge, alan,
  kayıt türü, mühendis ve gün kırılımlarına girmez. Yalnız
  `yaklasim_bazinda` içinde `bilinmiyor` satırında görünür.
- `belge_bazinda`, `alan_bazinda`, `kayit_turu_bazinda`, `yaklasim_bazinda`,
  `muhendis_bazinda` (`list[dict]`): her satırda kırılım adı (`belge`,
  `alan`, ...), `toplam`, `duzeltilen`, `oran`. Mühendis atfı şöyledir: net
  düzeltilen alan o alanı son düzelten mühendise, düzeltilmeyen alan
  onaylayana sayılır. Onaylayan, katalogdaki onaylı sürümden
  (`dokuman_surumleri`) okunur.
- `gun_bazinda` (`dict[str, float]`): taslağın onay günü (UTC,
  `YYYY-MM-DD`, `dokuman_surumleri.onay_zamani`) → oran. Bütün alanları
  düzeltilmiş bir taslak da düzeltme gününde değil, onay gününde sayılır.

Tablolar yoksa (hiç düzeltme kaydı kurulmamış veritabanı) sıfırlı özet döner.

**Hatalar**: yok (sqlite3 hataları dışında). Arayüz yakalamaz.

**Yan etkiler**: yok; yalnız okur.

## Giriş kalite ekranı

### `malzeme_kabul.katalog.veritabani.Katalog.malzemeler()`

**Girdiler**: yok.

**Çıktı**: `list[Malzeme]`, koda göre sıralı. Alanlar `Katalog.malzeme`
altındadır.

**Yan etkiler**: yok.

### `malzeme_kabul.katalog.veritabani.Katalog.gecerli_dokuman(malzeme_kodu)`

Malzemenin standart + revizyonu için **en son onaylı** kabul dokümanı
sürümünü döner. Karar her zaman bu sürümle verilir; doküman dosyadan
okunmaz.

**Girdiler**

- `malzeme_kodu` (`str`, zorunlu).

**Çıktı**: `DokumanSurumu`. Alanlar `taslak_onayla` altındadır.

**Hatalar**: `KatalogHatasi`: malzeme bilinmiyor, o revizyon için onaylı
doküman yok, ya da bir sürümün içerik özeti tutmuyor (kurcalanmış). Giriş
kalite ekranı yakalar.

**Yan etkiler**: yok.

### `malzeme_kabul.katalog.veritabani.Katalog.partiler(malzeme_kodu)`

**Girdiler**

- `malzeme_kodu` (`str | None`, isteğe bağlı, varsayılan `None`): verilirse
  yalnız o malzemenin partileri lot sırasıyla gelir. `None` ise bütün
  partiler malzeme ve lot sırasıyla gelir.

**Çıktı**: `list[Parti]`. `Parti` dondurulmuş bir dataclass'tır:

- `lot_no`, `malzeme_kodu`, `tedarikci`, `siparis_revizyonu`
- `uretim_tarihi` (`date`)
- `durum` (`PARTI_DURUMLARI`'ndan biri)
- `kap_turu` (`str | None`)
- `mp_inceleme` (`str | None`)
- `durum_kaynagi` (`str | None`): `None` hiç karar verilmedi; `"makine"`,
  `"insan"` ya da `"bilinmiyor"`
- `karar_verildi` özelliği: `durum_kaynagi` doluysa `True`

**Yan etkiler**: yok.

### `malzeme_kabul.katalog.veritabani.Katalog.onayli_tedarikciler(malzeme_kodu)`

**Girdiler**

- `malzeme_kodu` (`str`, zorunlu).

**Çıktı**: `list[str]`: o malzeme için onaylı tedarikçi adları, alfabetik.
Kod bilinmiyorsa hata vermez, boş liste döner.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.parti_hazirla(katalog, malzeme_kodu, lot_no, tedarikci, siparis_revizyonu, uretim_tarihi, kap_turu)`

Lot katalogda yoksa `bekliyor` durumuyla ekler; varsa olduğu gibi döner.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `malzeme_kodu` (`str`, zorunlu).
- `lot_no` (`str`, zorunlu).
- `tedarikci` (`str`, zorunlu): o malzeme için onaylı tedarikçi olmalıdır.
  Burada ad tam eşleşmeyle karşılaştırılır.
- `siparis_revizyonu` (`str`, zorunlu, boş olamaz): siparişte yazan
  revizyon harfi.
- `uretim_tarihi` (`date | str`, zorunlu): `str` ise `YYYY-AA-GG`
  biçiminde.
- `kap_turu` (`str | None`, isteğe bağlı, varsayılan `None`): raf ömrü
  hesabı için kap türü. Bilinmiyorsa `None`. Raf ömrü seçimi `depo_tablosu`
  altında anlatılır.

**Çıktı**: `Parti`. Alanlar `Katalog.partiler` altındadır.

**Hatalar**: `KatalogHatasi`: malzeme bilinmiyor, tedarikçi onaylı değil,
sipariş revizyonu boş ya da tarih biçimi yanlış. Arayüz yakalar.

**Yan etkiler**: lot yeniyse `partiler`'e bir satır ekler. Lot zaten varsa
diğer girdiler sessizce yok sayılır; var olan parti güncellenmez. Denetim
kaydına yazmaz.

### `malzeme_kabul.arayuz.ekran_verisi.json_sertifika_karari(katalog, defter, malzeme_kodu, json_metni, kullanici, lot_no)`

Ham hücreli JSON sertifikayla, PDF olmadan karar verir. Dil modeli
kullanılmaz.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `malzeme_kodu` (`str`, zorunlu).
- `json_metni` (`str`, zorunlu): `Sertifika` şemasına uyan JSON metni.
- `kullanici` (`str`, zorunlu, boş olamaz).
- `lot_no` (`str | None`, isteğe bağlı, varsayılan `None`): verilirse parti
  katalogda olmalıdır; sipariş revizyonu denetlenir ve parti durumu yazılır.

**Çıktı**: `KatalogKarari` (pydantic modeli). Alanlar:

- `malzeme_kodu`, `lot_no`
- `dokuman_surumu` (`str`, ör. `"MIL-PRF-23377K v2"`) ve `dokuman_ozeti`
  (SHA-256)
- `kontrol` (`KontrolSonucu`): `sertifika_no`, `belge_karari`, `revizyon`
  (`KararSatiri`), `satirlar` (`list[KararSatiri]`), `tip_sinif`
  (`KararSatiri | None`), `eslesmeyen_satirlar` (`list[str]`)
- `ek_denetimler` (`list[KararSatiri]`):
  - `tedarikci`: her zaman üretilir. Ad, onaylı listeyle büyük/küçük harf
    ve boşluk farkı gözetilmeden karşılaştırılır. Listede yoksa ya da
    sertifikada tedarikçi boşsa ("sertifikada tedarikçi yok") "insan
    incelemeli" olur.
  - `siparis_revizyonu`: yalnız lot verildiyse üretilir. Partinin sipariş
    revizyonu malzemenin revizyonundan farklıysa "insan incelemeli" olur.
  - `parti_no`: yalnız lot verildiyse üretilir. Sertifikadaki parti
    numarası yoksa ya da lotla (büyük/küçük harf ve boşluk farkı
    gözetilmeden) tutmuyorsa "insan incelemeli" olur.
  - `parti_tedarikcisi`: yalnız lot verildiyse üretilir. Sertifikadaki
    tedarikçi yoksa ya da partinin katalogdaki tedarikçisi değilse (başka
    bir onaylı firma olsa bile) "insan incelemeli" olur.
  - `parti_durumu`: yalnız makine kararı partiyi daha serbest bir duruma
    geçiremediğinde üretilir (bkz. `parti_durumu` alanı); her zaman "insan
    incelemeli"dir ve gerekçesinde partinin neden o durumda kaldığı yazar.
  - `kanit`: yalnız hibrit hatta üretilir.
- `parti_karari` (`"kabul" | "red" | "inceleme"`): parti kuralının
  (`kural.karar_motoru.parti_karari`) sonucu:
  - bir satır "uygun değil" ise red
  - yoksa bir satır "insan incelemeli" ise inceleme
  - hepsi uygunsa kabul
- `parti_durumu` (`"serbest" | "karantina" | "bekliyor"`): kabul → serbest,
  red → karantina, inceleme → bekliyor. Makine partiyi yalnız aynı ya da
  daha kısıtlayıcı bir duruma geçirebilir (serbest < bekliyor < karantina).
  Tek istisna hiç karar verilmemiş (`Parti.durum_kaynagi` `None`) bekleyen
  yeni partidir. Karantinadaki ya da daha önce karar verilmiş bekleyen bir
  partiyi makine serbest bırakmaz: `parti_durumu` partinin mevcut durumu
  olarak kalır, `parti_durumu` ek denetimi eklenir ve `parti_karari` yeniden
  hesaplanır (en az inceleme). Serbest bırakmak `karari_duzelt` ile insanın
  işidir.
- `hat` (`dict | None`): bu fonksiyonda `{"mod": "json"}`
- `demo_onayi` (`bool`, varsayılan `False`): kararın kullandığı kabul
  dokümanı sürümünün `DokumanSurumu.demo_onayi` değeri. Karar mantığını
  değiştirmez; yalnız işarettir. `karar` kaydının içeriğine de yazılır.

`KararSatiri` alanları: `test_id`, `test_adi`, `karar` (`"uygun" |
"uygun_degil" | "insan_incelemeli"`), `gerekce`, `madde`, `sayfa`,
`sertifikadaki_ad`, `okunan_sonuc`, `okunan_birim`, `cevrilmis_deger`,
`hedef_birim`.

Lot verildiğinde sertifikadaki `parti_no` katalogdaki lotla, sertifikadaki
tedarikçi de partinin kayıtlı tedarikçisiyle karşılaştırılır (`parti_no` ve
`parti_tedarikcisi` ek denetimleri; bkz. "Bilinen açıklar" madde 3).

**Hatalar**

- `ValueError`: JSON bozuk ya da şemaya uymuyor (`pydantic.ValidationError`,
  bir `ValueError` alt sınıfı). Arayüz yakalar.
- `KatalogHatasi`: kullanıcı boş, defter katalogla aynı bağlantıyı
  paylaşmıyor, malzeme bilinmiyor, onaylı doküman yok ya da parti
  bilinmiyor. Altta çağrılan `hat.katalog_karari.malzeme_koduyla_kontrol`
  ayrıca lot verilip `durumu_yaz` açıkken defter yoksa da `KatalogHatasi`
  verir; bu fonksiyon defteri her zaman verdiği için burada oluşmaz. Hiçbir
  durumda bir şey yazılmaz. Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): denetim kaydı adımı
  reddetti (ör. kayıt zamanı geçersiz). Arayüz bunu `ValueError` olarak
  yakalar.
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir; hiçbir şey yazılmamıştır.

**Yan etkiler**: malzeme ve geçerli doküman sürümü işlemden önce okunur.
Ardından tek işlemde (`Katalog.islem`, BEGIN IMMEDIATE; lot verilmese de)
şunları yapar:

1. Lot verildiyse partiyi kilit altında okur ve makine geçişine izin
   veriliyorsa parti durumunu karara göre günceller (`kaynak="makine"`).
   İzin yoksa (karantinadaki ya da daha önce karar verilmiş bekleyen
   partiyi serbest bırakmak) durum değişmez ve `parti_durumu` ek denetimi
   eklenir (bkz. Çıktı, `parti_durumu`).
2. Denetim kaydına bir `karar` kaydı ekler. İçerik `KatalogKarari`'nin
   tamamıdır; ayrıca `malzeme_kodu`, `lot_no` ve kararın kullandığı
   `dokuman_surumu` yazılır.

Herhangi bir adım hata verirse ikisi de geri alınır: parti durumu değişmez,
kayıt yazılmaz.

### `malzeme_kabul.hat.hibrit_hat.sertifika_hatti(katalog, malzeme_kodu, pdf_yolu, mod, istemci, lot_no, defter, kullanici, ayar)`

Sertifika PDF'inden parti kararına kadar bütün hat. Adımlar:

1. PDF'i okur.
2. Sertifikayı seçilen modda okur.
3. Hibritte her satırı kanıt doğrulayıcıdan geçirir.
4. `malzeme_koduyla_kontrol` ile kural kararını verir.
5. Kaydı yazar.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `malzeme_kodu` (`str`, zorunlu).
- `pdf_yolu` (`str | Path`, zorunlu): kaydedilmiş sertifika PDF'i.
- `mod` (`str | None`, isteğe bağlı, varsayılan `None`): `"kural"` ya da
  `"hibrit"`. `None` ise `MALZEME_KABUL_MODU` kullanılır; o da yoksa
  `"kural"`. Boş dizgi (`""`) `HatHatasi` verir. Arayüz modu her zaman
  açıkça verir.
- `istemci` (`SohbetIstemcisi | None`, isteğe bağlı, varsayılan `None`):
  hibritte yerel model istemcisi. `None` ise ortam değişkenlerinden kurulur
  (bkz. "Ortam değişkenleri"). Arayüz bunu vermez.
- `lot_no` (`str | None`, isteğe bağlı, varsayılan `None`): katalogdaki lot.
- `defter` (`DenetimKaydi | None`, isteğe bağlı, varsayılan `None`):
  verilirse karar denetim kaydına yazılır.
- `kullanici` (`str | None`, isteğe bağlı, varsayılan `None`): `defter`
  verildiyse zorunludur.
- `ayar` (`KararAyarlari | None`, isteğe bağlı, varsayılan `None`): eksik
  test ve yanlış revizyon durumlarında verilecek karar. Varsayılanda ikisi de
  "insan incelemeli"dir. Arayüz bunu vermez.

**Çıktı**: `tuple[KatalogKarari, SertifikaOkumasi]`.

- `KatalogKarari`: alanlar `json_sertifika_karari` altındadır. `hat`
  sözlüğünde şunlar bulunur: `mod`, `model`, `istem_surumu`, `kanitsiz`
  (`list[str]`, `"test adı: neden"` biçiminde), `yedek` (`str | None`).
- `SertifikaOkumasi` (dataclass): `sertifika`, `mod`, `model`,
  `istem_surumu`, `sayfalar`, `kanitsiz`, `yedek`. Arayüz bunu kullanmaz.

Hibrit mod şöyle çalışır:

- Kanıtsız satırlar karara girmez ve `kanit` ek denetimi "insan
  incelemeli" olur.
- Dil modelinin okuduğu standart atfı belgede tam atıf olarak yoksa atıf
  silinir (`standart_atfi=None`) ve `kanitsiz` listesine eklenir. Tedarikçi,
  parti no, sertifika no ve üretim tarihi de belgede aranır; bulunamayan
  alan boşaltılır ve `kanitsiz`'e yazılır. Kural ve model bu alanları farklı
  okursa anlaşmazlık yazılır ve ilgili ek denetim insan incelemeli olur.
- Dil modeli yanıt vermezse (`OSError`), şemaya uymayan bir yanıt dönerse
  (`ValueError`) ya da sunucu yanıtı beklenmedik ya da yarımsa
  (`ModelYanitHatasi`), hat kural okumasına düşer ve nedeni
  `hat["yedek"]`'e yazar. Arayüz bu durumda uyarı gösterir. Yedekte `kanit`
  denetimi **"uygun"** olur, çünkü karar kural okumasıyla verilir. Karar
  her durumda kurallarla verilir.

**Hatalar**

- `HatHatasi` (bir `ValueError` alt sınıfı): mod bilinmiyor ya da boş
  (`mod=""`), hibritte istemci yok ve `MALZEME_KABUL_MODELI` tanımsız, ya da
  ortamdan kurulan istemcinin adresi localhost değil / arka ucu bilinmiyor.
  Arayüz yakalar.
- `ValueError`: PDF okunamadı ya da PDF sınırı aşıldı. Arayüz yakalar.
- `KatalogHatasi`: şu durumlarda verilir; hiçbir şey yazılmaz. Arayüz
  yakalar.
  - `defter` verilmiş ama kullanıcı boş
  - `defter` katalogla aynı bağlantıyı paylaşmıyor
  - `lot_no` verilmiş ama `defter` yok: parti durumu yazan karar defter
    olmadan verilmez (`malzeme_koduyla_kontrol`, `durumu_yaz` varsayılanı
    açık)
  - malzeme bilinmiyor, onaylı doküman yok ya da parti bilinmiyor
- `DenetimHatasi` (bir `ValueError` alt sınıfı): denetim kaydı adımı
  reddetti. Arayüz `ValueError` olarak yakalar.
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir; hiçbir şey yazılmamıştır.
- `FileNotFoundError` ve diğer `OSError`'lar: PDF yok ya da okunamıyor.
  Arayüz yakalamaz. Dil modeli bağlantısındaki `OSError`'ı arayüz yakalamaz,
  çünkü hat onu kendisi yakalar ve yedeğe düşer; arayüze ulaşmaz.

**Yan etkiler**: `json_sertifika_karari` ile aynıdır. PDF okuma, dil modeli
çağrısı, malzeme ve doküman sürümünün okunması işlemin dışındadır; yazma
kilidi yalnız parti durumu ve `karar` kaydı için tek işlemde (BEGIN
IMMEDIATE) alınır. Kayda ayrıca şunlar yazılır:

- `pdf_sayfasi`: sayfa numaraları, virgülle ayrılmış.
  - Kural modunda ve hibrit yedekte belgenin bütün sayfaları yazılır.
  - Hibritte (yedek yokken) yalnız kanıtlı satırların sayfaları yazılır.
    Kanıtlı satır yoksa `None` yazılır.
- `model` ve `istem_surumu`: yalnız hibritte ve yedeğe düşülmediyse.

### `malzeme_kabul.arayuz.ekran_verisi.PARTI_ETIKETI`

`dict[str, str]`: `parti_karari` → ekran etiketi. Etiketler simgelidir:

- `kabul` → "KABUL (serbest)"
- `red` → "RED (karantina)"
- `inceleme` → "İNCELEME (bekliyor)"

### `malzeme_kabul.arayuz.ekran_verisi.DEMO_ETIKETI`

`str`: `"DEMO ONAYI (M&P onayı değil)"`. Demo onaylı kabul dokümanı
sürümünün ekrandaki işareti. Asıl tanımı `katalog.veritabani.DEMO_ETIKETI`'dir;
`ekran_verisi` aynı nesneyi yeniden dışa verir. Komut satırı betikleri
(`scripts/karar_ver.py`, `scripts/sertifika_kontrol.py`) arayüzü içe
aktarmadan bunu `veritabani`'ndan alır; karar demo onaylı dokümanla
verildiyse "... ile karar: ..." satırının sonuna `", DEMO ONAYI (M&P onayı
değil)"` eklenir. Giriş kalite ekranı geçerli sürüm demo
onaylıysa bu metinle `st.warning` gösterir; demo onaylı dokümanla verilen
karardan sonra da bir `st.warning` gösterilir. Depo ekranı kabul dokümanı
demo onaylı partileri sayıp `st.info` gösterir.

### `malzeme_kabul.arayuz.ekran_verisi.surum_etiketi(surum)`

**Girdiler**

- `surum` (`DokumanSurumu`, zorunlu).

**Çıktı**: `str`. `surum.etiket`; `surum.demo_onayi` ise sonuna
`" (DEMO ONAYI (M&P onayı değil))"` eklenir. Giriş kalite ekranı bunu
"Kabul dokümanı: <etiket> (onaylayan ...)" başlığında kullanır.

**Hatalar**: yok.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.karar_basligi(karar)`

**Girdiler**

- `karar` (`KatalogKarari`, zorunlu).

**Çıktı**: `str`. `"Parti kararı: " + PARTI_ETIKETI[karar.parti_karari]`;
`karar.demo_onayi` ise sonuna `" (DEMO ONAYI (M&P onayı değil))"` eklenir.

**Hatalar**: yok.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.karar_tablosu(karar)`

**Girdiler**

- `karar` (`KatalogKarari`, zorunlu).

**Çıktı**: `list[dict]`. Satır sırası: revizyon denetimi, (varsa) tip/sınıf
denetimi, ek denetimler, test satırları. Anahtarlar:

- `karar`: simgeli etiket (uygun / uygun değil / insan incelemeli)
- `test`, `madde`, `sayfa`, `sertifikadaki_ad`, `okunan`, `gerekce`

**Yan etkiler**: yok.

### `malzeme_kabul.katalog.veritabani.PARTI_DURUMLARI`

`tuple[str, ...]`: `("serbest", "karantina", "bekliyor")`. Düzeltme
formunun seçenekleridir.

### `malzeme_kabul.hat.katalog_karari.karari_duzelt(katalog, defter, kullanici, malzeme_kodu, lot_no, yeni_durum, neden)`

İnsanın parti kararını düzeltmesi.

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `kullanici` (`str`, zorunlu).
- `malzeme_kodu` (`str`, zorunlu).
- `lot_no` (`str`, zorunlu): katalogdaki lot.
- `yeni_durum` (`"serbest" | "karantina" | "bekliyor"`, zorunlu).
- `neden` (`str`, zorunlu, boş olamaz): gerekçe.

**Çıktı**: `Kayit` (dondurulmuş dataclass). Alanlar:

- `sira`, `zaman`, `tur`, `kullanici`
- `malzeme_kodu`, `lot_no`, `dokuman_surumu`, `pdf_sayfasi`
- `model`, `istem_surumu`
- `icerik` (JSON metni)
- `onceki_ozet`, `ozet`
- `veri` özelliği: `icerik`'in çözülmüş hali

**Hatalar**

- `KatalogHatasi`: kullanıcı boş, gerekçe boş (ikisi de hiçbir şey
  yazılmadan denetlenir), defter katalogla aynı bağlantıyı paylaşmıyor,
  parti bilinmiyor, durum geçersiz ya da onaylı doküman yok. Hiçbir
  durumda parti durumu değişmez. Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): denetim kaydı adımı
  reddetti (ör. kayıt zamanı geçersiz). Arayüz yakalar (`ValueError`
  olarak).
- `sqlite3.OperationalError`: yazma kilidi alınamadı. Arayüz yakalar ve
  "meşgul" iletisini gösterir; hiçbir şey yazılmamıştır.

**Yan etkiler**: tek işlemde (`Katalog.islem`, BEGIN IMMEDIATE) sırayla
şunları yapar:

1. Partinin önceki durumunu okur (kilit altında; başka bir bağlantı araya
   giremez).
2. Geçerli doküman sürümünü okur.
3. Parti durumunu günceller (`kaynak="insan"`).
4. Denetim kaydına bir `duzeltme` kaydı ekler. İçerik: `onceki_durum`,
   `yeni_durum`, `neden`; `dokuman_surumu` 2. adımda okunan sürümdür.

Herhangi bir adım hata verirse hepsi geri alınır: durum değişmez, kayıt
yazılmaz.

## Depo ekranı

### `malzeme_kabul.arayuz.ekran_verisi.depo_tablosu(katalog, bugun, uyari_esigi_gun)`

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `bugun` (`date | None`, isteğe bağlı, varsayılan `None`): `None` ise
  bugünün tarihi kullanılır.
- `uyari_esigi_gun` (`int`, isteğe bağlı, varsayılan `30`): son kullanma
  tarihine bu kadar gün kala `yaklasiyor` uyarısı verilir. Arayüz 1 ile 365
  arasında bir değer alır.

**Çıktı**: `list[dict]`; her parti bir satırdır. En yakın son kullanma
tarihi önce gelir, bilinmeyenler sondadır. Anahtarlar:

- `malzeme`, `lot`, `tedarikçi`, `durum`
- `M&P`: işaret ya da boş
- `kabul dokümanı`: raf ömrünün alındığı geçerli sürümün etiketi (ör.
  `"MIL-PRF-23377K v1"`); sürüm demo onaylıysa sonuna
  `" (DEMO ONAYI (M&P onayı değil))"` eklenir. Onaylı doküman yoksa boş.
- `üretim`: ISO tarih
- `son kullanma`: ISO tarih ya da boş
- `kalan gün`: `int | None`
- `raf`: `RAF_ETIKETI` değeri
- `ömür uzatma testleri`: uyarılı partide test adları ya da "tanımlı değil"
- `not`

**Raf ömrü seçimi** kural katmanında yapılır (`kural/raf_omru.raf_omru_sec`).
Önce tip/sınıfa uygulanan kayıtlar alınır; hiç yoksa satır `bilinmiyor`
olur ("kabul dokümanında raf ömrü yok"). Partinin kap türü `None`, boş ya da
yalnız boşluksa **bilinmiyor** sayılır. Sonra:

1. Kap türü verilmiş ve bir kaydın kap türüyle eşleşiyorsa (harf büyüklüğü
   gözetilmez), o kayıt alınır; not yazılmaz.
2. Kap türü verilmiş ama eşleşmiyorsa:
   - uygulanan **tek kayıt** varsa o alınır;
   - değilse kap türü boş olan **tek bir genel kayıt** varsa genel kayıt
     alınır (daha kısa bir kap kaydı olsa da);
   - değilse **en kısa** raf ömrü alınır.
   Üç durumda da verilen kap türünü anan bir not yazılır.
3. Kap türü bilinmiyorsa:
   - uygulanan **tek kayıt** varsa o alınır; genel kayıtsa not yazılmaz,
     kap türüne özgüyse not yazılır;
   - birden çok kayıt varsa genel kayıt olsa bile **en kısa** raf ömrü
     alınır ve not yazılır ("kap türü bilinmiyor; en kısa raf ömrü alındı").

En kısa, süreler partinin üretim tarihine eklenince (`sure_ekle`) en erken
biten kayıttır; ör. 1 ay ile 30 gün, ya da artık yılda 1 yıl ile 366 gün,
üretim tarihine göre farklı sonuç verir. Eşitlikte belge sırasındaki ilk
kayıt alınır. Kap türü `""` olan kayıt `None` gibi genel sayılır. Bu, Nida'nın
onayladığı "kap türü bilinmiyorsa en kısa raf ömrü alınır" kararıdır.

**Hatalar**: `KatalogHatasi`: bir partinin malzemesi katalogda yok.
Onaylı dokümanın eksik olması hata değildir; satır `bilinmiyor` olur ve
nedeni `not` alanına yazılır. Arayüzdeki çağrı (`uygulama.py`, depo
ekranı) `try` içinde değildir; hiçbir istisna yakalanmaz.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.RAF_ETIKETI`

`dict[str, str]`: raf durumu → ekran etiketi. Durumlar: `gecerli`,
`yaklasiyor`, `doldu`, `bilinmiyor`. Arayüz `yaklasiyor` ve `doldu`
etiketli satırları sayıp uyarı gösterir.

## Hatalar

### `malzeme_kabul.katalog.veritabani.KatalogHatasi`

`ValueError` alt sınıfı. Katalog kuralına aykırı bir işlemi bildirir:

- bilinmeyen malzeme, parti ya da taslak
- onaysız tedarikçi
- onaylı doküman yok
- kurcalanmış sürüm
- test kümesi kilidi
- boş kullanıcı ya da gerekçe

### `malzeme_kabul.hat.hibrit_hat.HatHatasi`

`ValueError` alt sınıfı. Hat ayarı hatasını bildirir: mod bilinmiyor ya da
hibritte model istemcisi kurulamadı (`MALZEME_KABUL_MODELI` yok).

Ayrıca iki istisna daha `ValueError` alt sınıfıdır:
`kayit.denetim_kaydi.DenetimHatasi` ve `belge.pdf_okuyucu.PdfSiniriAsildi`.
Arayüz bunları doğrudan içe aktarmaz. `ValueError` yakalayan çağrılarda
yakalanırlar.

`DenetimHatasi` şu durumlarda verilir:

- `DenetimKaydi` açık işlemi olan bir bağlantıyla kurulmak istendi
- kayıt türü bilinmiyor ya da kullanıcı boş
- metin alanı metin değil, `pdf_sayfasi` metin ya da tam sayı değil
- `zaman` saat dilimli ISO 8601 değil, bir önceki kayıttan eski (zaman
  monotondur) ya da şimdiden `ILERI_ZAMAN_PAYI` (5 dakika) fazla ileride

Yazma yapan her çağrı `Katalog.islem` ile BEGIN IMMEDIATE alır. Kilit
alınamazsa `sqlite3.OperationalError` ("database is locked") yükselir ve
hiçbir şey yazılmaz. Yazan formlar bunu yakalar ve `uygulama.MESGUL`
iletisini ("Veritabanı şu an başka bir işlemle meşgul; kaydedilmedi,
yeniden deneyin") gösterir.

Arayüzdeki yakalama tablosu (`main`, `uygulama.py`):

| Çağrı | Yakalananlar | Yakalanmayanlar (örnek) |
|---|---|---|
| `standart_yukle` | KatalogHatasi, ValueError | sqlite3.OperationalError, FileNotFoundError ve diğer OSError'lar |
| `tablodan_dokuman`, `taslak_duzelt` | KatalogHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | diğer sqlite3 hataları |
| `taslak_onayla` | KatalogHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | diğer sqlite3 hataları |
| `etiket_adayi_kaydet` → `etiket_adayi_yaz` (onaydan sonra) | OSError, ValueError (KatalogHatasi dahil), sqlite3.Error (uyarı; onay geri alınmaz) | |
| `duzeltme_panosu` | hiçbiri | sqlite3 hataları |
| `revizyon_izinli_mi` (dosyalar kaydedilmeden önce) | ValueError (izin yok gibi gösterilir) | |
| `revizyon_raporu` | KatalogHatasi, ValueError | FileNotFoundError ve diğer OSError'lar |
| `yeni_revizyon_yukle` | KatalogHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | diğer sqlite3 hataları |
| `mp_bekleyenler`, `Katalog.malzeme` (revizyon ekranı) | hiçbiri | KatalogHatasi |
| `mp_incelemesini_kapat` | KatalogHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | diğer sqlite3 hataları |
| `Katalog.gecerli_dokuman` (giriş kalite) | KatalogHatasi | |
| `parti_hazirla`, `json_sertifika_karari`, `sertifika_hatti` | KatalogHatasi, HatHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | FileNotFoundError ve diğer OSError'lar |
| `karari_duzelt` | KatalogHatasi, ValueError (DenetimHatasi dahil); sqlite3.OperationalError ("meşgul") | diğer sqlite3 hataları |
| `depo_tablosu` | **hiçbiri** (try yok) | KatalogHatasi |
| `test_tablosu` (taslak ekranı) | hiçbiri (try dışında) | şema/öznitelik hataları |
| `karar_tablosu`, `PARTI_ETIKETI[...]` (giriş kalite, karardan sonra) | hiçbiri (try dışında) | KeyError (beklenmeyen karar değeri) |
| `Katalog(...)`, `sema_eksikleri`, `DenetimKaydi(...)`, `giris`, `taslaklar`, `malzemeler`, `partiler`, `onayli_tedarikciler`, `zinciri_dogrula` | hiçbiri | sqlite3 ve şema hataları, DenetimHatasi (açık işlem) |

## Sabitler

Sabitlerin başlıkları ilgili ekran bölümlerindedir:

- `EKRANLAR`: Bağlantı ve kimlik
- `TABLO_SUTUNLARI`: M&P ekranı
- `PARTI_ETIKETI`, `DEMO_ETIKETI` ve `PARTI_DURUMLARI`: Giriş kalite ekranı
- `RAF_ETIKETI`: Depo ekranı

Etiket sözlükleri yalnız gösterim içindir. Karar ve durum değerleri her
zaman sözlüklerin anahtarlarıdır.

## Ortam değişkenleri

Bu liste kodda okunan değişkenlerden çıkarıldı.

| Değişken | Okuyan | Varsayılan | Anlamı |
|---|---|---|---|
| `MALZEME_KABUL_DB` | `arayuz/uygulama.py`, `docker/baslat.sh` | `data/calisma/katalog.sqlite` (Docker: `/veri/katalog.sqlite`) | Katalog, denetim kaydı ve kullanıcıların SQLite dosyası |
| `MALZEME_KABUL_YUKLEME` | `arayuz/uygulama.py` | `data/calisma/yuklenen` (Docker: `/veri/yuklenen`) | Yüklenen PDF ve JSON'ların yazıldığı klasör |
| `MALZEME_KABUL_ETIKET_ADAYI` | `arayuz/uygulama.py` | `data/calisma/etiket_adaylari` | Onaylanan taslakların etiket adaylarının yazıldığı klasör; bir parçası `gold` olan klasör reddedilir |
| `MALZEME_KABUL_MODU` | `hat/hibrit_hat.mod_sec` | `kural` | `mod` verilmezse hat modu. Arayüz modu her zaman açıkça verdiği için ekranda etkisi yoktur. |
| `MALZEME_KABUL_MODELI` | `hat/hibrit_hat.ortamdan_istemci` | yok | Hibrit modda yerel model adı. Tanımsızsa hibrit mod `HatHatasi` verir. |
| `MALZEME_KABUL_ARKA_UCU` | `hat/hibrit_hat.ortamdan_istemci` | `ollama` | `ollama` ya da `llamacpp` |
| `MALZEME_KABUL_MODEL_ADRESI` | `hat/hibrit_hat.ortamdan_istemci` | arka ucun localhost adresi | Yalnız localhost kabul edilir; başka bir adres `ValueError` verir. |
| `MALZEME_KABUL_KOK` | `arayuz/ekran_verisi` (modül yüklenirken), `docker/baslat.sh` | depo kökü; betikte `/uygulama` (Docker: `Dockerfile` ile `/uygulama`) | Veri kökü: `data/bolunme.yaml` ve `data/cikti` buradan bulunur; `baslat.sh` betik yollarını buradan çözer |
| `MALZEME_KABUL_MP_PAROLASI`, `MALZEME_KABUL_GK_PAROLASI` | `arayuz/kimlik.ortamdan_kullanicilar` (`scripts/ilk_kurulum.py`) | **yok** (zorunlu; varsayılan parola yoktur) | Veritabanında hiç kullanıcı yokken açılacak M&P ve giriş kalite hesaplarının parolaları. En az 12 karakter, yalnız boşluktan oluşamaz, kullanıcı adıyla aynı olamaz (harf duyarsız), bilinen deneme parolaları reddedilir. Docker'da konteynere doğrudan verilmez: `docker-compose.yml` bunları host'tan okuyup secrets olarak aktarır; host'ta ayarlı değilse compose başlamaz. |
| `MALZEME_KABUL_MP_PAROLASI_DOSYASI`, `MALZEME_KABUL_GK_PAROLASI_DOSYASI` | `arayuz/kimlik.ortamdan_kullanicilar` | yok (Docker: `/run/secrets/mp_parolasi`, `/run/secrets/gk_parolasi`) | Parolayı dosyadan okur (sondaki satır sonu atılır). Aynı rol için doğrudan değişkenle birlikte verilemez. |
| `MALZEME_KABUL_DOCKER` | `scripts/katalog_kur.py` | yok (Docker: `Dockerfile` ile `1`) | `1` ise `--ornek-kullanicilar` reddedilir (sıfırdan farklı çıkış); `--ornek` çalışır |
| `MALZEME_KABUL_MP_KULLANICI`, `MALZEME_KABUL_GK_KULLANICI` | `arayuz/kimlik.ortamdan_kullanicilar` | `mp`, `gk` | İlk kurulumda açılan hesapların adları; ikisi aynı olamaz |
| `MALZEME_KABUL_PAROLA` | `scripts/kullanici_ekle.py` | yok (parola sorulur) | Eklenecek kullanıcının parolası |
| `KAPI_PORTU`, `KAPI_HEDEFI`, `KAPI_HEDEF_PORTU` | `docker/yerel_kapi.py` (yalnız Docker) | `8501`, `uygulama`, `8501` | Ana makineden uygulamaya TCP iletici ("kapı") |
| `STREAMLIT_*` | Streamlit (yalnız Docker'da `Dockerfile` ile ayarlanır) | `Dockerfile`'a bakın | Başsız çalışma, kullanım istatistiği kapalı, adres `0.0.0.0`, port `8501` |

Arayüzün kendisi (`uygulama.py`) parolayla ilgili hiçbir ortam değişkeni
okumaz; parola değişkenlerini yalnız Streamlit'ten önce çalışan ilk kurulum
okur. `KAPI_*`
ve `STREAMLIT_*` yalnız Docker'a özgüdür; ürün kodu (`src/`) bunları okumaz.

## Kullanıcı oluşturma

- Gerçek hesap için `python scripts/kullanici_ekle.py --ad <ad> --rol
  mp|giris_kalite [--db yol]` çalıştırılır. Parola sorulur ya da
  `MALZEME_KABUL_PAROLA`'dan okunur. Parola en az 8 karakter olmalıdır;
  kullanıcı adı boş olamaz; aynı ad ikinci kez eklenemez (`KimlikHatasi`).
- **Ayrılmış ad:** `ornek-veri` (`katalog.veritabani.ORNEK_ONAYLAYAN`)
  örnek verinin demo onaylayanıdır. Bu adla hesap açılmaz: `kimlik.kullanici_ekle`
  ve ilk kurulum (`ortamdan_kullanicilar`, `MALZEME_KABUL_MP_KULLANICI` /
  `MALZEME_KABUL_GK_KULLANICI`) adı baştaki/sondaki boşluk atılıp harf
  farkı gözetilmeden (`strip` + `casefold`) karşılaştırır ve `KimlikHatasi`
  verir; ilk kurulumda hiçbir hesap açılmaz. `ornek-veri2`, `ornek` gibi
  benzer adlar kabul edilir.
- Deneme için `python scripts/katalog_kur.py --ornek --ornek-kullanicilar`
  çalıştırılır. Bu, örnek kataloğu ve iki deneme kullanıcısını kurar:
  - `mp` / `mp-ornek-parola` (M&P)
  - `gk` / `gk-ornek-parola` (giriş kalite)

  Parolalar betikte sabit yazılıdır ve ekrana basılır. Kullanıcılar zaten
  varsa atlanır. Örnek doküman sürümleri `ornek-veri` kullanıcısıyla
  **demo onayıyla** (`dokuman_surumleri.demo_onayi = 1`) onaylanır ve
  denetim kaydına `"örnek veri, M&P onayı değil"` notu ve
  `"demo_onayi": true` ile yazılır. Özet satırında sürüm
  `(v1, demo onayı)` olarak görünür. Örnek veri dosyasındaki `onaylayan`
  tam `ornek-veri` değilse yükleme `KatalogHatasi` verir, hiçbir şey
  yazılmaz. Bir standart + revizyonun gerçek (demo olmayan) onaylı sürümü
  zaten varsa o örnek doküman yazılmaz: `ornek_yukle` etiketini
  `YuklemeOzeti.atlanan_dokumanlar`'a ekler, `katalog_kur.py` onun için
  `onay` kaydı yazmaz ve "atlanan örnek dokümanlar" satırında gösterir.
  Yalnız demo sürümü olan standarda yeni örnek içerik yeni demo sürüm olur.
  Bu deneme yolu yalnız yerel geliştirme içindir. Docker imajında
  `MALZEME_KABUL_DOCKER=1` ayarlıdır ve `--ornek-kullanicilar` sıfırdan
  farklı kodla reddedilir.
- Docker'da `docker/baslat.sh`, katalog dosyası yoksa `katalog_kur.py
  --ornek` çalıştırır (deneme kullanıcısı açmaz), ardından Streamlit'ten
  önce `scripts/ilk_kurulum.py --db "$MALZEME_KABUL_DB"` çalıştırır. Bu
  betik `malzeme_kabul.arayuz.kimlik.ortamdan_kullanicilar(ortam,
  baglanti)` çağırır:
  - Her çağrıda önce mevcut hesaplar `kimlik.DENEME_PAROLALARI`'na karşı
    denetlenir (erken dönüşten önce). Bir hesap deneme parolasıyla
    kurulmuşsa hesabın adını söyleyen (parolayı söylemeyen) `KimlikHatasi`
    verilir; hiçbir hesap değiştirilmez, silinmez ya da açılmaz. Bu yüzden
    eski bir deneme birimiyle Streamlit her açılışta başlamaz.
  - Veritabanında hiç kullanıcı yoksa M&P (`mp` rolü) ve giriş kalite
    (`giris_kalite` rolü) hesaplarını yukarıdaki parola değişkenleriyle
    açar ve oluşan `list[Kullanici]`'yı döner. Ya ikisi ya hiçbiri açılır.
  - Parola eksik, boş, yalnız boşluk (dosyadan okunan dahil), dosyası okunamaz, 12 karakterden kısa, kullanıcı
    adıyla aynı ya da bilinen deneme parolası ise `KimlikHatasi` verir.
    Mesaj ilgili değişkenin adını söyler, parolayı asla içermez. Betik
    sıfırdan farklı kodla çıkar ve `set -e` yüzünden Streamlit başlamaz.
  - Kullanıcı zaten varsa (ve hiçbiri deneme parolalı değilse) ortam
    değişkeni gerekmez, hiçbir hesap değişmez ve `[]` döner (yeniden
    başlatma). Ortamdaki parolayı değiştirmek mevcut hesabı değiştirmez;
    parola değiştirme yolu README'de ("Parola değiştirme").

## Bilinen açıklar ve bekleyen işler

Geriye dönük incelemede bulunan konular aşağıda. Her biri ayrı bir PR'la
düzeltilecek. Bu doküman bugünkü (`main`) davranışı anlatır; düzeltmeler
gelince ilgili bölümler de güncellenecek.

1. **Olumsuz sonuç metinleri (somut yanlış kabul yolu).**
   `kural/karar_motoru.sonucu_ayristir` önce "kaldı" kelimelerini arar.
   Ama "did not pass", "not pass", "does not comply", "not satisfactory",
   "not ok" ve "kabul edilmedi" o listede yok. İçlerindeki "pass", "comply",
   "satisfactory", "ok" ve "kabul" kelimeleri "geçti" listesinde olduğu için
   bu metinler **geçti** sayılır. Sayısal olmayan bir şartta satır "uygun"
   olur. Ayrı bir PR'la düzeltilecek.
2. **Karantinadan makineyle serbest bırakma (düzeltildi).**
   `malzeme_koduyla_kontrol` partinin önceki durumunu kilit altında okur.
   Makine partiyi yalnız aynı ya da daha kısıtlayıcı bir duruma geçirebilir
   (serbest < bekliyor < karantina); tek istisna hiç karar verilmemiş
   bekleyen yeni partidir. Karantinadaki ya da daha önce karar verilmiş
   bekleyen partiyi makine serbest bırakmaz; durum korunur ve `parti_durumu`
   ek denetimi "insan incelemeli" olur. Serbest bırakma `karari_duzelt` ile
   insanın işidir.
3. **Lot ve tedarikçi karşılaştırması (düzeltildi).** Lot verildiğinde
   sertifikadaki `parti_no` katalogdaki lotla (`parti_no` ek denetimi),
   sertifikadaki tedarikçi de partinin tedarikçisiyle (`parti_tedarikcisi`
   ek denetimi) karşılaştırılır. Eksik ya da tutmayan değer "insan
   incelemeli" olur.
4. **Tedarikçi yoksa denetim yok (düzeltildi).** `tedarikci` ek denetimi
   artık her zaman üretilir; sertifikada tedarikçi boşsa "insan incelemeli"
   olur ("sertifikada tedarikçi yok").
5. **Tip/sınıf tanımsız.** Katalogda tip ve sınıfın **ikisi de** boşsa
   `kontrol_et` katalog dalına girmez (`tip is not None or sinif is not
   None` koşulu). Bu durumda tip ve sınıf sertifikadaki atıftan alınır;
   hibritte bu atıf dil modelinin okumasıdır. `tip_sinif` denetimi de hiç
   üretilmez. Bu, docs/mimari.md §2'deki "tip/sınıf sertifikadan tahmin
   edilmez" kuralına aykırıdır. Yalnız **biri** boşsa katalog dalına girilir
   ve davranış ihtiyatlıdır: boş kalan alana bağlı testler de aranır;
   sertifikada yoksa "insan incelemeli" eksik test olur. Ayrı bir PR'la düzeltilecek.
6. **Boş test listesi.** `KabulDokumani.testler` boş olabilir; şemada
   varsayılanı boş listedir (`sozlesme/sema.py`). `Katalog.dokuman_onayla`
   ve `taslagi_onayla` bunu denetlemez. Boş bir doküman onaylanırsa
   revizyon, tedarikçi ve sipariş revizyonu denetimleri uygun olduğunda
   parti **kabul** edilir ve **serbest** bırakılır. Taranmış (metni
   okunamayan) bir standarttan çıkan boş taslak onaylanırsa bu yola
   çıkılır. Ayrı bir PR'la düzeltilecek.
7. **Denetim kaydı ve sürümlerin değiştirilemezliği.**
   - Atomiklik (düzeltildi): durum değişikliği ile kaydı artık tek işlemde
     (`Katalog.islem`, BEGIN IMMEDIATE; `DenetimKaydi.ekle` açık işleme
     SAVEPOINT ile katılır) yazılıyor: `taslak_duzelt`, `taslak_onayla`,
     `json_sertifika_karari`, `sertifika_hatti`, `karari_duzelt`,
     `mp_incelemesini_kapat`. Kayıt yazılamazsa durum da değişmez. Defter
     katalogla aynı bağlantıyı paylaşmazsa `KatalogHatasi` verilir; parti
     durumu yazan karar defter olmadan verilmez.
   - REPLACE açığı (denetim kaydında kapandı): `denetim_kaydi` üzerindeki
     BEFORE INSERT tetikleyicisi (`denetim_kaydi_uzerine_yazilamaz`) var
     olan bir sıra ya da özetle eklemeyi çakışma çözümünden önce reddeder.
     Böylece `INSERT OR REPLACE` / `REPLACE INTO` hiçbir kaydı silemez;
     bu `recursive_triggers` ayarına bağlı değildir.
     `dokuman_surumleri` tablosunda böyle bir tetikleyici yoktur; orada
     REPLACE yolu açıktır (kodda REPLACE kullanılmaz).
   - Açık kalan: SQLite dosyasına yazabilen biri `DROP TRIGGER` ile
     tetikleyicileri kaldırabilir ya da dosyayı doğrudan düzenleyebilir.
     Kaldırılmış bir denetim tetikleyicisini `sema_eksikleri` yakalar
     (kenar çubuğu ve `scripts/denetim_dogrula.py` zinciri bozuk sayar);
     ama tetikleyiciyi kaldırıp satırı değiştiren ve sonra tetikleyiciyi
     geri kuran biri bununla yakalanmaz, yalnız zincir (aşağıda) yakalar.
     Ayrıca uygulamanın bir sonraki açılışı (giriş ekranı dahil) eksik
     tetikleyiciyi kayıtsız onarır; o andan sonra ne kenar çubuğu ne
     `denetim_dogrula.py` bunu görür. Onarımın zincire kayıt düşmesi ve
     `dokuman_surumleri` için REPLACE koruması ayrı bir PR'la ele alınacak.
   - Sürüm özeti: `dokuman_surumleri.ozet` içerikle aynı satırda durur.
     Biri içeriği değiştirip özeti de yeniden hesaplarsa bu fark edilmez.
     Sürüm, denetim kaydındaki onay kaydının özetiyle çapraz
     karşılaştırılmaz. Ayrıca `scripts/katalog_kur.py` örnek onay
     kayıtlarına özet yazmaz (yalnız `dokuman_surumu`, `not` ve
     `demo_onayi`).
   - Zincir: bir kayıt değiştirilip sonraki bütün kayıtlar yeniden
     hesaplanırsa bunu yalnız dışarıda saklanan son özet yakalar.
     Arayüz bu özeti kullanmaz (bkz. madde 17).

   Açık kalanlar (`DROP TRIGGER` / dosyayı doğrudan düzenleme, sürüm
   özeti, zincirin dışarıdaki özetle karşılaştırılmaması) ayrı bir PR'la ele
   alınacak.
8. **Hibrit kanıt gevşekliği.** Kanıt doğrulayıcı retro H1-H14 ile
   sıkılaştırıldı (docs/mimari.md madde 6, hibrit hat). Yedekte `kanit`
   denetiminin "uygun" olması hâlâ gözden geçirilecek.
9. **Kural ve model anlaşmazlığı.** Kural okuması ile dil modeli okuması
   anlaşmazsa uygulanacak kural ayrı bir PR'da ekleniyor; bu doküman onu
   henüz anlatmıyor.
10. **Demo onayı işareti (düzeltildi).** Nida'nın kararı: örnek kabul
    dokümanları onaylı sayılır, ama ekranda ve veritabanında "demo onayı"
    olarak işaretlenir.
    - Veritabanı: `dokuman_surumleri.demo_onayi` (`INTEGER NOT NULL DEFAULT
      0 CHECK (demo_onayi IN (0, 1))`). Sürümün parçasıdır;
      değiştirilemezlik tetikleyicisi onu da korur. Eski veritabanlarında
      `Katalog.__init__` göçü sütunu ekler ve `ornek-veri` satırlarını
      işaretler (tek işlem; düşerse tetikleyici yerinde kalır).
    - Yalnız `Katalog.dokuman_onayla(..., demo_onayi=True)` ve yalnız tam
      `ORNEK_ONAYLAYAN` (`"ornek-veri"`) ile verilir; `ornek-veri` de demo
      işaretsiz onay veremez. Taslak onayı (`taslak_onayla`,
      `Katalog.taslagi_onayla`) ve `katalog_karari.dokuman_onayla` demo
      parametresi almaz. `ornek-veri` ayrılmış kullanıcı adıdır (bkz.
      "Kullanıcı oluşturma").
    - Karar ve rapor: `KatalogKarari.demo_onayi`, `RafSatiri.demo_onayi`;
      karar mantığı değişmez. M&P'nin gerçek onaylı yeni sürümü demo
      sürümün yerine geçer (en son sürüm).
    - Ekran: `DEMO_ETIKETI`, `surum_etiketi`, `karar_basligi`, depo
      tablosunun `kabul dokümanı` sütunu; giriş kalite ve depo ekranlarında
      uyarı/bilgi kutusu.
    - Açık kalan: `mp_incelemesini_kapat` ile demo sürümlü bir revizyona
      geçişin kabul edilip edilmeyeceği sorulacak.
11. **Docker varsayılan parolası (düzeltildi).** Compose artık deneme
    kullanıcısı açmıyor. Parolalar ortam değişkeninden (Docker'da secrets
    dosyası) okunuyor; parola yoksa ya da zayıfsa uygulama başlamıyor (bkz.
    "Kullanıcı oluşturma"). Önceden kurulmuş birimlerdeki deneme hesapları
    kendiliğinden kaldırılmaz ama artık her açılışta yakalanır ve uygulama
    başlamaz; hesap README'deki yolla silinip yeniden açılmalıdır.
12. **Revizyon ekranı kilidi (düzeltildi).** `revizyon_raporu` iki
    revizyonu da `revizyon_izinli_mi` ile test kümesi kilidinden geçirir;
    ekran bunu dosyalar kaydedilmeden önce de çağırır. Kilit dosya adını
    okur; yeniden adlandırılan bir dosya kilidi aşar (`standart_yukle` ile
    aynı sınır, bkz. docs/mimari.md madde 7).
13. **Raf ömrü seçimi (düzeltildi).** Kap türü bilinmiyorsa ve birden çok
    kayıt varsa genel kayıt olsa bile en kısa alınır; kap türü verilip
    eşleşmediğinde tek aday ve tek genel kayıt durumları da not yazar (bkz.
    `depo_tablosu`).
14. **Yüklenen dosyanın üzerine yazma.** `dosyayi_kaydet` dosyayı yalnız
    temizlenmiş adıyla yazıyor. Aynı adlı bir yükleme önceki dosyanın
    üzerine yazılır.
15. **Bağlantı sızıntısı (düzeltildi).** Her Streamlit çalıştırması kendi
    `Katalog`'unu `with` bloğuyla açar ve kapatır (`st.rerun` istisnasında
    ve defter kurulamadığında da). Bağlantı oturumlar arasında paylaşılmaz.
16. **Rol denetimi yalnız arayüzde.** `ekran_verisi` ve `hat`
    fonksiyonları kullanıcının rolünü denetlemiyor.
17. **Kenar çubuğundaki "sağlam".** Bu ifade yalnız zincirin kendi içinde
    tutarlı olduğunu gösterir; dışarıda saklanan bir özetle
    karşılaştırılmaz (bkz. `zinciri_dogrula`).

18. **Docker'da veri yolları (düzeltildi).** `Dockerfile` paketi editable
    olmadan kurar (`pip install --no-deps .`); bu yüzden
    `Path(__file__).parents[3]` site-packages altını gösteriyordu ve
    `BOLUNME` ile `data/cikti` bulunamıyordu. Artık `ekran_verisi.KOK` önce
    `MALZEME_KABUL_KOK`'a bakar; `Dockerfile` bunu `/uygulama` yapar.
    `BOLUNME` ve `HAZIR_RAPORLAR` KOK'tan türer. İmajda doğrulandı:
    `standart_izinli_mi("MIL-PRF-23377K")` "geliştirme kümesinde" döner ve
    hazır revizyon raporları listelenir.

## Sözleşmenin korunması

`tests/test_arayuz_sozlesmesi.py` bu dokümanın **yalnız şu kısımlarını**
koda karşı denetler:

- Her `### ` başlığı tek bir kod parçası içinde tam nitelikli bir ad taşır
  ve bu ad içe aktarılabilir. Aynı başlık iki kez yazılmaz.
- Fonksiyon ve metot başlıklarındaki parametre adları gerçek imzayla aynı
  ve aynı sıradadır (`self` yazılmaz). Fonksiyonlar parantezli, sabitler ve
  sınıflar parantezsiz yazılır.
- Her fonksiyon bölümünde `**Girdiler**` ve `**Çıktı**` bulunur ve her
  parametre adı `**Girdiler**` altında geçer.
- `**Girdiler**` altında "zorunlu", "isteğe bağlı" ve "varsayılan" diye
  yazılanlar imzadaki varsayılanlarla tutarlıdır.
- `**Hatalar**` altında backtick içinde yazılan istisna adları (`...Hatasi`,
  `...Error`, `...Exception`) gerçek istisna sınıflarıdır. Testin
  istisnanın ne zaman verildiğini denetlemediğine dikkat edin.
- Şunların her biri burada başlıklı olmalıdır: `uygulama.py`'nin
  `malzeme_kabul`'dan içe aktardığı her ad, modül takmalarıyla eriştiği her
  öznitelik (`ev.xxx`), ve `katalog.` ile `defter.` üzerinden çağırdığı her
  metot. `Katalog`, `DenetimKaydi`, `KatalogHatasi` ve `HatHatasi`
  parantezsiz başlıkla yer alır.

**Denetlenmeyenler** şunlardır:

- tipler
- dönen alanlar
- yan etkiler
- hataların hangi koşulda verildiği
- arayüzün hangi istisnayı yakaladığı
- açıklama metinleri

Bu kısımlar kod incelemesiyle güncel tutulur. `uygulama.py` yeni bir
fonksiyon, metot ya da sabit çağırırsa, ya da bir imza değişirse test kırılır
ve bu doküman aynı değişiklikle güncellenir. Uygulama ast ile okunur; test
Streamlit kurulu olmadan da çalışır.
