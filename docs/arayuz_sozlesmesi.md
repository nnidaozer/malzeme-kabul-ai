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

  Katman adları docs/mimari.md "Klasör yapısı" bölümüyle aynıdır.
- **Arayüz yalnız bu dokümandaki adları çağırır.** Ekranın arkasındaki işler
  `arayuz/ekran_verisi.py`'de durur ve Streamlit olmadan test edilir. Kimlik
  işleri `arayuz/kimlik.py`'dedir. Streamlit'e yalnız `uygulama.py` bağımlıdır.
- **Bağlantı.** `uygulama.py` bir `Katalog` açar. Aynı SQLite bağlantısını
  (`katalog.baglanti`, bir `sqlite3.Connection` özniteliği) hem
  `DenetimKaydi`'ya hem `kimlik.giris`'e verir. Katalog, denetim kaydı ve
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
| `taslak`: Taslağı düzelt ve onayla | `mp` | `Katalog.taslaklar(yalniz_acik=True)`, `ekran_verisi.test_tablosu`, `TABLO_SUTUNLARI`, `tablodan_dokuman`, `taslak_duzelt`, `taslak_onayla` |
| `revizyon`: Revizyon farkı ve M&P incelemesi | `mp` | `ekran_verisi.hazir_revizyon_raporlari`, `revizyon_raporu`, `revizyon_etkisi.yeni_revizyon_yukle`, `mp_bekleyenler`, `Katalog.malzeme`, `mp_incelemesini_kapat` |
| `giris`: Giriş kalite: CoC kontrolü | `giris_kalite` | `Katalog.malzemeler`, `gecerli_dokuman`, `partiler`, `onayli_tedarikciler`, `ekran_verisi.parti_hazirla`, `json_sertifika_karari`, `hibrit_hat.sertifika_hatti`, `karar_tablosu`, `PARTI_ETIKETI`; düzeltme formu: `PARTI_DURUMLARI`, `katalog_karari.karari_duzelt` |
| `depo`: Depo: partiler ve raf ömrü | `mp`, `giris_kalite` | `ekran_verisi.depo_tablosu`, `RAF_ETIKETI` |
| kenar çubuğu (her ekran) | herkes | `kimlik.yetkili_mi`, `kimlik.EKRANLAR`, `DenetimKaydi.zinciri_dogrula` |

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
yalnız `DenetimKaydi`'ya ve `kimlik.giris`'e vermek için okur; bu bağlantıyla
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

Arayüz her Streamlit yeniden çalıştırmasında yeni bir `Katalog` açar ve
kapatmaz (bkz. "Bilinen açıklar").

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi`

Zincirli (SHA-256) denetim kaydı. Kayıt türleri `karar`, `onay` ve
`duzeltme`'dir. Kayıtlara yalnız ekleme yapılır; UPDATE ve DELETE
tetikleyiciyle reddedilir. Tetikleyici yalnız uygulamanın kendi
UPDATE/DELETE'ine karşı korur. Dosyaya yazabilen biri onu aşabilir (bkz.
"Bilinen açıklar" madde 7). Her kaydın özeti bir önceki kaydın özetini
içerir. Arayüz bu sınıfa doğrudan kayıt yazmaz; kayıtları aşağıdaki hat ve
ekran verisi fonksiyonları yazar.

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.__init__(baglanti)`

**Girdiler**

- `baglanti` (`sqlite3.Connection | str | Path`, isteğe bağlı, varsayılan
  `":memory:"`): var olan bir bağlantı ya da dosya yolu. Arayüz
  `katalog.baglanti` verir; bu durumda `kapat()` bağlantıyı kapatmaz.

**Çıktı**: `DenetimKaydi` nesnesi.

**Yan etkiler**:

- bağlantının `row_factory`'sini `sqlite3.Row` yapar
- `denetim_kaydi` tablosunu ve tetikleyicilerini kurar

### `malzeme_kabul.kayit.denetim_kaydi.DenetimKaydi.zinciri_dogrula(beklenen_son_ozet)`

Zinciri baştan sona doğrular. Arayüz bunu kenar çubuğunda argümansız
çağırır ve `gecerli` alanına göre "sağlam" ya da "BOZUK" yazar.

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
`standart`, `taslak`, `revizyon`, `giris`, `depo`. Rol yetkileri
`kimlik.YETKILER` içindedir:

- `mp` → standart, taslak, revizyon, depo
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
  `ekran_verisi.KOK` üzerinden kurulur (`Path(__file__).parents[3]`).
  Docker riski: paket editable olmadan kurulursa bu yol site-packages'ın
  üstünü gösterir. Dosya bulunamaz ve `standart_yukle` "bölünme dosyası
  yok" der (bkz. "Bilinen açıklar" madde 18).
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

**Yan etkiler**: `taslaklar` tablosuna bir satır ekler. Denetim kaydına
yazmaz, çünkü taslak henüz karar dayanağı değildir.

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

### `malzeme_kabul.arayuz.ekran_verisi.taslak_duzelt(katalog, defter, taslak_id, yeni, kullanici)`

**Girdiler**

- `katalog` (`Katalog`, zorunlu).
- `defter` (`DenetimKaydi`, zorunlu).
- `taslak_id` (`int`, zorunlu).
- `yeni` (`KabulDokumani`, zorunlu): `tablodan_dokuman` çıktısı.
- `kullanici` (`str`, zorunlu): düzelten kullanıcının adı.

**Çıktı**: `list[str]`: test düzeyindeki farklar, biçimi
`"<test_id>.<alan>: <eski JSON> → <yeni JSON>"`. Fark yoksa boş liste
döner. Taslak onaylanmış olsa bile, fark yoksa önce farklar karşılaştırıldığı
için hata verilmez, `[]` döner.

**Hatalar**

- `KatalogHatasi`: taslak bilinmiyor, fark var ama taslak onaylanmış, ya da
  standart veya revizyon değiştirilmiş. Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): kullanıcı boş. Arayüz bunu
  `ValueError` olarak yakalar.

**Yan etkiler**: fark yoksa hiçbir şey yazmaz. Fark varsa iki ayrı işlem
yapar:

1. Taslağın içeriğini ve `guncelleme` zamanını günceller ve commit eder.
2. Denetim kaydına `duzeltme` türünde bir kayıt ekler. İçerik: `taslak`,
   `farklar`. `dokuman_surumu`: `"<belge><rev> taslak <id>"`.

İkinci adım hata verirse taslak değişmiş ama kaydı yazılmamış kalır. Bu açık
denetim kaydı PR'ında düzeltilecek.

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
- `etiket` özelliği, ör. `"MIL-PRF-23377K v2"`

**Hatalar**

- `KatalogHatasi`: taslak bilinmiyor, taslak zaten onaylanmış ya da
  onaylayan boş. Arayüz yakalar.
- `DenetimHatasi`: kullanıcı boş, denetim kaydı adımında. Arayüz yakalamaz
  (yalnız `KatalogHatasi` yakalar). Onaylayan boşsa önce `KatalogHatasi`
  verildiği için bu olağan akışta oluşmaz.

**Yan etkiler**: üç ayrı işlem yapar:

1. Standart yoksa `standartlar`'a ekler; `dokuman_surumleri`'ne yeni sürümü
   ekler.
2. Taslağı `onaylandi` yapar ve sürüm numarasını yazar.
3. Denetim kaydına bir `onay` kaydı ekler. İçerik: `taslak`,
   `dokuman_surumu`, `ozet`, `not`.

Üçüncü adım hata verirse sürüm onaylanmış ama kaydı yazılmamış kalır. Bu açık
denetim kaydı PR'ında düzeltilecek.

### `malzeme_kabul.arayuz.ekran_verisi.hazir_revizyon_raporlari(klasor)`

**Girdiler**

- `klasor` (`Path`, isteğe bağlı, varsayılan `data/cikti`): önceden
  üretilmiş raporların klasörü. Varsayılan yol `ekran_verisi.KOK`
  üzerinden kurulur. Docker'da aynı yol riski vardır: liste boş gelebilir
  (bkz. "Bilinen açıklar" madde 18).

**Çıktı**: `dict[str, Path]`: rapor adı → `*_revizyon_farklari.md` yolu.
Rapor adı, dosya adından `_revizyon_farklari` atılarak elde edilir. Ada göre
sıralıdır. Klasör yoksa boş döner.

**Yan etkiler**: yok.

### `malzeme_kabul.arayuz.ekran_verisi.revizyon_raporu(eski_pdf, yeni_pdf, dokuman)`

**Girdiler**

- `eski_pdf` (`str | Path`, zorunlu) ve `yeni_pdf` (`str | Path`, zorunlu):
  aynı standardın iki revizyonu. Dosya adları `MIL-PRF-23377J.pdf`
  biçiminde olmalıdır.
- `dokuman` (`KabulDokumani | None`, isteğe bağlı, varsayılan `None`):
  verilirse rapora bu doküman için güncelleme önerileri eklenir. Arayüz bunu
  vermez.

**Çıktı**: `tuple[str, dict]`: Markdown rapor ve özet sözlüğü
(`RevizyonFarki.ozet()`). Arayüz özeti oturumda tutar ve
`yeni_revizyon_yukle`'ye `fark_ozeti` olarak geçirir.

**Test kümesi kilidi yok.** Bu fonksiyon `data/bolunme.yaml`'a bakmaz.
Test kümesindeki bir standardın PDF'leri de ekrandan karşılaştırılabilir.
Komut satırı betiği (`scripts/revizyon_karsilastir.py`) ise kilidi
`deney.bolunme.betik_korumasi` ile denetler. Ekranın da kilidi denetlemesi
ayrı bir PR'la gelecek.

**Hatalar**

- `ValueError`: iki dosya aynı standardın revizyonu değil, dosya adından
  belge no veya revizyon çıkarılamadı, PDF okunamadı ya da PDF sınırı
  aşıldı. Arayüz yakalar.
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

- `KatalogHatasi`: kullanıcı boş. Arayüzdeki çağrı (`uygulama.py`,
  revizyon ekranı) `try` içinde değildir, yani hiçbir istisna yakalanmaz.
  Oturumdaki kullanıcı adı boş olamadığı için bu hata olağan akışta oluşmaz.
  SQLite hataları da yakalanmaz.

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
  - malzeme bilinmiyor
  - bekleyen inceleme yok
  - `yeni_revizyona_gec` için revizyon harfi verilmemiş ya da o revizyonun
    onaylı kabul dokümanı yok
  - karar bilinmiyor
- `DenetimHatasi`: kullanıcı boş. Arayüz yakalamaz (yalnız `KatalogHatasi`
  yakalar). Oturumdaki kullanıcı adı boş olamadığı için olağan akışta
  oluşmaz.

**Yan etkiler**: sırayla ayrı işlemler yapar:

1. Yalnız `yeni_revizyona_gec`'te: malzemenin revizyonunu günceller ve
   commit eder.
2. Malzemenin ve partilerinin `mp_inceleme` işaretini kaldırır ve commit
   eder.
3. Denetim kaydına bir `onay` kaydı ekler. İçerik:
   - `gerek_yok`: `karar`, `malzeme` (standart etiketi), `isaret`, `not`
   - `yeni_revizyona_gec`: `karar`, `eski`, `yeni`, `not`

Üçüncü adım hata verirse revizyon değişmiş ve işaret kalkmış ama kaydı
yazılmamış kalır. Bu açık denetim kaydı PR'ında düzeltilecek.

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
  - `tedarikci`: yalnız sertifikada tedarikçi yazılıysa üretilir.
    Sertifikada tedarikçi boşsa bu denetim hiç eklenmez. Ad, onaylı listeyle
    büyük/küçük harf ve boşluk farkı gözetilmeden karşılaştırılır. Listede
    yoksa "insan incelemeli" olur.
  - `siparis_revizyonu`: yalnız lot verildiyse üretilir. Partinin sipariş
    revizyonu malzemenin revizyonundan farklıysa "insan incelemeli" olur.
  - `kanit`: yalnız hibrit hatta üretilir.
- `parti_karari` (`"kabul" | "red" | "inceleme"`): parti kuralının
  (`kural.karar_motoru.parti_karari`) sonucu:
  - bir satır "uygun değil" ise red
  - yoksa bir satır "insan incelemeli" ise inceleme
  - hepsi uygunsa kabul
- `parti_durumu` (`"serbest" | "karantina" | "bekliyor"`): kabul → serbest,
  red → karantina, inceleme → bekliyor
- `hat` (`dict | None`): bu fonksiyonda `{"mod": "json"}`

`KararSatiri` alanları: `test_id`, `test_adi`, `karar` (`"uygun" |
"uygun_degil" | "insan_incelemeli"`), `gerekce`, `madde`, `sayfa`,
`sertifikadaki_ad`, `okunan_sonuc`, `okunan_birim`, `cevrilmis_deger`,
`hedef_birim`.

Sertifikadaki `parti_no`, katalogdaki lotla karşılaştırılmaz. Sertifikadaki
tedarikçi de partinin kayıtlı tedarikçisiyle karşılaştırılmaz (bkz.
"Bilinen açıklar").

**Hatalar**

- `ValueError`: JSON bozuk ya da şemaya uymuyor (`pydantic.ValidationError`,
  bir `ValueError` alt sınıfı). Arayüz yakalar.
- `KatalogHatasi`: kullanıcı boş, malzeme bilinmiyor, onaylı doküman yok ya
  da parti bilinmiyor. Arayüz yakalar.
- `DenetimHatasi` (bir `ValueError` alt sınıfı): denetim kaydı adımı
  reddetti. Arayüz bunu `ValueError` olarak yakalar.

**Yan etkiler**: iki ayrı işlem yapar:

1. Lot verildiyse parti durumunu karara göre günceller ve commit eder.
   Partinin önceki durumu dikkate alınmaz; karantinadaki bir parti de
   kabul kararıyla `serbest` olur.
2. Denetim kaydına bir `karar` kaydı ekler. İçerik `KatalogKarari`'nin
   tamamıdır; ayrıca `malzeme_kodu`, `lot_no`, `dokuman_surumu` yazılır.

İkinci adım hata verirse parti durumu değişmiş ama kaydı yazılmamış kalır.
Bu açık denetim kaydı PR'ında düzeltilecek.

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
  `"kural"`. Arayüz modu her zaman açıkça verir.
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
- Dil modelinin okuduğu standart atfı belgede yoksa atıf silinir
  (`standart_atfi=None`) ve `kanitsiz` listesine eklenir.
- Dil modeli yanıt vermezse (`OSError`) ya da şemaya uymayan bir yanıt
  dönerse (`ValueError`), hat kural okumasına düşer ve nedeni
  `hat["yedek"]`'e yazar. Arayüz bu durumda uyarı gösterir. Yedekte `kanit`
  denetimi **"uygun"** olur, çünkü karar kural okumasıyla verilir. Karar
  her durumda kurallarla verilir.

**Hatalar**

- `HatHatasi` (bir `ValueError` alt sınıfı): mod bilinmiyor, ya da hibritte
  istemci yok ve `MALZEME_KABUL_MODELI` tanımsız. Arayüz yakalar.
- `ValueError`: yerel model adresi localhost değil, arka uç bilinmiyor, PDF
  okunamadı ya da PDF sınırı aşıldı. Arayüz yakalar.
- `KatalogHatasi`: `defter` verilmiş ama kullanıcı boş, malzeme bilinmiyor,
  onaylı doküman yok ya da parti bilinmiyor. Arayüz yakalar.
- `FileNotFoundError` ve diğer `OSError`'lar: PDF yok ya da okunamıyor.
  Arayüz yakalamaz. Dil modeli bağlantısındaki `OSError`'ı arayüz yakalamaz,
  çünkü hat onu kendisi yakalar ve yedeğe düşer; arayüze ulaşmaz.

**Yan etkiler**: `json_sertifika_karari` ile aynıdır (iki ayrı işlem: parti
durumu, ardından `karar` kaydı). Aynı atomiklik açığı burada da geçerlidir.
Kayda ayrıca şunlar yazılır:

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

- `KatalogHatasi`: gerekçe boş, parti bilinmiyor, durum geçersiz ya da
  onaylı doküman yok. Son durumda parti durumu zaten değişmiş olur. Arayüz
  yakalar.
- `DenetimHatasi`: kullanıcı boş. Arayüz yakalamaz (yalnız `KatalogHatasi`
  yakalar); olağan akışta oluşmaz.

**Yan etkiler**: sırayla şunları yapar:

1. Parti durumunu günceller ve commit eder.
2. Geçerli doküman sürümünü okur.
3. Denetim kaydına bir `duzeltme` kaydı ekler. İçerik: `onceki_durum`,
   `yeni_durum`, `neden`.

2. ya da 3. adım hata verirse durum değişmiş ama kaydı yazılmamış kalır. Bu
açık denetim kaydı PR'ında düzeltilecek.

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
- `üretim`: ISO tarih
- `son kullanma`: ISO tarih ya da boş
- `kalan gün`: `int | None`
- `raf`: `RAF_ETIKETI` değeri
- `ömür uzatma testleri`: uyarılı partide test adları ya da "tanımlı değil"
- `not`

**Raf ömrü seçimi** kural katmanında yapılır (`kural/raf_omru.raf_omru_sec`).
Önce tip/sınıfa uygulanan kayıtlar alınır. Sonra sırayla:

1. Kap türü verilmişse ve bir kaydın kap türüyle eşleşiyorsa (harf büyüklüğü
   gözetilmez), o kayıt alınır.
2. Uygulanan **tek kayıt** varsa o alınır. Kap türü eşleşmese de alınır ve
   not yazılmaz.
3. Kap türü bilinmiyorsa ve kap türü boş olan **tek bir genel kayıt**
   varsa, o genel kayıt alınır. Daha kısa ömürlü bir kap türü kaydı olsa da
   bu böyledir.
4. Bu üç durumun dışında en kısa raf ömrü alınır ve nedeni nota yazılır.

Nida'nın onayladığı karar şudur: "kap türü bilinmiyorsa en kısa raf ömrü
alınır". 3. adım bu kararla çelişir. 2. adım da kap türü verilip
eşleşmediğinde uyarı vermez. Bu iki konu ayrı bir PR'la düzeltilecek.

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
`kayit.denetim_kaydi.DenetimHatasi` (kullanıcı boş, kayıt türü bilinmiyor) ve
`belge.pdf_okuyucu.PdfSiniriAsildi`. Arayüz bunları doğrudan içe aktarmaz.
Yalnız `ValueError` yakalayan çağrılarda yakalanırlar.

Arayüzdeki yakalama tablosu (`main`, `uygulama.py`):

| Çağrı | Yakalananlar | Yakalanmayanlar (örnek) |
|---|---|---|
| `standart_yukle` | KatalogHatasi, ValueError | FileNotFoundError ve diğer OSError'lar |
| `tablodan_dokuman`, `taslak_duzelt` | KatalogHatasi, ValueError (DenetimHatasi dahil) | sqlite3 hataları |
| `taslak_onayla` | yalnız KatalogHatasi | DenetimHatasi, sqlite3 hataları |
| `revizyon_raporu` | yalnız ValueError | FileNotFoundError ve diğer OSError'lar |
| `yeni_revizyon_yukle` | **hiçbiri** (try yok) | KatalogHatasi, sqlite3 hataları |
| `mp_bekleyenler`, `Katalog.malzeme` (revizyon ekranı) | hiçbiri | KatalogHatasi |
| `mp_incelemesini_kapat` | yalnız KatalogHatasi | DenetimHatasi |
| `Katalog.gecerli_dokuman` (giriş kalite) | KatalogHatasi | |
| `parti_hazirla`, `json_sertifika_karari`, `sertifika_hatti` | KatalogHatasi, HatHatasi, ValueError | FileNotFoundError ve diğer OSError'lar |
| `karari_duzelt` | yalnız KatalogHatasi | DenetimHatasi |
| `depo_tablosu` | **hiçbiri** (try yok) | KatalogHatasi |
| `test_tablosu` (taslak ekranı) | hiçbiri (try dışında) | şema/öznitelik hataları |
| `karar_tablosu`, `PARTI_ETIKETI[...]` (giriş kalite, karardan sonra) | hiçbiri (try dışında) | KeyError (beklenmeyen karar değeri) |
| `Katalog(...)`, `giris`, `taslaklar`, `malzemeler`, `partiler`, `onayli_tedarikciler`, `zinciri_dogrula` | hiçbiri | sqlite3 ve şema hataları |

## Sabitler

Sabitlerin başlıkları ilgili ekran bölümlerindedir:

- `EKRANLAR`: Bağlantı ve kimlik
- `TABLO_SUTUNLARI`: M&P ekranı
- `PARTI_ETIKETI` ve `PARTI_DURUMLARI`: Giriş kalite ekranı
- `RAF_ETIKETI`: Depo ekranı

Etiket sözlükleri yalnız gösterim içindir. Karar ve durum değerleri her
zaman sözlüklerin anahtarlarıdır.

## Ortam değişkenleri

Bu liste kodda okunan değişkenlerden çıkarıldı.

| Değişken | Okuyan | Varsayılan | Anlamı |
|---|---|---|---|
| `MALZEME_KABUL_DB` | `arayuz/uygulama.py`, `docker/baslat.sh` | `data/calisma/katalog.sqlite` (Docker: `/veri/katalog.sqlite`) | Katalog, denetim kaydı ve kullanıcıların SQLite dosyası |
| `MALZEME_KABUL_YUKLEME` | `arayuz/uygulama.py` | `data/calisma/yuklenen` (Docker: `/veri/yuklenen`) | Yüklenen PDF ve JSON'ların yazıldığı klasör |
| `MALZEME_KABUL_MODU` | `hat/hibrit_hat.mod_sec` | `kural` | `mod` verilmezse hat modu. Arayüz modu her zaman açıkça verdiği için ekranda etkisi yoktur. |
| `MALZEME_KABUL_MODELI` | `hat/hibrit_hat.ortamdan_istemci` | yok | Hibrit modda yerel model adı. Tanımsızsa hibrit mod `HatHatasi` verir. |
| `MALZEME_KABUL_ARKA_UCU` | `hat/hibrit_hat.ortamdan_istemci` | `ollama` | `ollama` ya da `llamacpp` |
| `MALZEME_KABUL_MODEL_ADRESI` | `hat/hibrit_hat.ortamdan_istemci` | arka ucun localhost adresi | Yalnız localhost kabul edilir; başka bir adres `ValueError` verir. |
| `MALZEME_KABUL_ORNEK_KULLANICILAR` | `docker/baslat.sh` | betikte `0`, `docker-compose.yml`'de `1` | `1` ise ilk açılışta deneme kullanıcıları kurulur |
| `MALZEME_KABUL_PAROLA` | `scripts/kullanici_ekle.py` | yok (parola sorulur) | Eklenecek kullanıcının parolası |
| `KAPI_PORTU`, `KAPI_HEDEFI`, `KAPI_HEDEF_PORTU` | `docker/yerel_kapi.py` (yalnız Docker) | `8501`, `uygulama`, `8501` | Ana makineden uygulamaya TCP iletici ("kapı") |
| `STREAMLIT_*` | Streamlit (yalnız Docker'da `Dockerfile` ile ayarlanır) | `Dockerfile`'a bakın | Başsız çalışma, kullanım istatistiği kapalı, adres `0.0.0.0`, port `8501` |

Arayüzün kendisi parolayla ilgili hiçbir ortam değişkeni okumaz. `KAPI_*`
ve `STREAMLIT_*` yalnız Docker'a özgüdür; ürün kodu (`src/`) bunları okumaz.

## Kullanıcı oluşturma

- Gerçek hesap için `python scripts/kullanici_ekle.py --ad <ad> --rol
  mp|giris_kalite [--db yol]` çalıştırılır. Parola sorulur ya da
  `MALZEME_KABUL_PAROLA`'dan okunur. Parola en az 8 karakter olmalıdır;
  kullanıcı adı boş olamaz; aynı ad ikinci kez eklenemez (`KimlikHatasi`).
- Deneme için `python scripts/katalog_kur.py --ornek --ornek-kullanicilar`
  çalıştırılır. Bu, örnek kataloğu ve iki deneme kullanıcısını kurar:
  - `mp` / `mp-ornek-parola` (M&P)
  - `gk` / `gk-ornek-parola` (giriş kalite)

  Parolalar betikte sabit yazılıdır ve ekrana basılır. Kullanıcılar zaten
  varsa atlanır. Örnek doküman sürümleri `ornek-veri` kullanıcısıyla
  onaylanır ve denetim kaydına `"örnek veri, M&P onayı değil"` notuyla
  yazılır.
- Docker'da `docker/baslat.sh`, katalog dosyası yoksa `katalog_kur.py
  --ornek` çalıştırır. `MALZEME_KABUL_ORNEK_KULLANICILAR=1` ise
  `--ornek-kullanicilar` da eklenir; `docker-compose.yml`'de bu değer
  varsayılan olarak `1`'dir. Yani Docker bugün bilinen deneme parolalarıyla
  açılır (bkz. "Bilinen açıklar").

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
2. **Karantinadan makineyle serbest bırakma.** `malzeme_koduyla_kontrol`
   partinin önceki durumuna bakmaz; yeni bir "kabul" kararı karantinadaki
   bir partiyi `serbest` yapar.
3. **Lot ve tedarikçi karşılaştırması.** Sertifikadaki `parti_no`
   katalogdaki lotla, sertifikadaki tedarikçi de partinin tedarikçisiyle
   karşılaştırılmaz.
4. **Tedarikçi yoksa denetim yok.** Sertifikada tedarikçi boşsa `tedarikci`
   ek denetimi hiç üretilmez.
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
   - Atomiklik: durum değişikliği ile kayıt aynı işlemde yazılmıyor (bkz.
     `taslak_duzelt`, `taslak_onayla`, `json_sertifika_karari`,
     `sertifika_hatti`, `karari_duzelt`, `mp_incelemesini_kapat`).
   - Tetikleyicilerin sınırı: kodda REPLACE kullanılmıyor. Ama SQLite
     dosyasına yazabilen biri `denetim_kaydi` ve `dokuman_surumleri`
     satırlarını değiştirebilir. Üç yolu var:
     - `INSERT OR REPLACE` ya da `REPLACE INTO`. Çakışan satır silinip
       yeniden yazılır; `recursive_triggers` kapalıyken (SQLite
       varsayılanı) DELETE tetikleyicisi çalışmaz, UPDATE tetikleyicisi de
       devreye girmez.
     - `DROP TRIGGER`.
     - Dosyayı doğrudan düzenlemek.

     Tetikleyiciler yalnız uygulamanın kendi UPDATE/DELETE'ine karşı korur.
   - Sürüm özeti: `dokuman_surumleri.ozet` içerikle aynı satırda durur.
     Biri içeriği değiştirip özeti de yeniden hesaplarsa bu fark edilmez.
     Sürüm, denetim kaydındaki onay kaydının özetiyle çapraz
     karşılaştırılmaz. Ayrıca `scripts/katalog_kur.py` örnek onay
     kayıtlarına özet yazmaz (yalnız `dokuman_surumu` ve `not`).
   - Zincir: bir kayıt değiştirilip sonraki bütün kayıtlar yeniden
     hesaplanırsa bunu yalnız dışarıda saklanan son özet yakalar.
     Arayüz bu özeti kullanmaz (bkz. madde 17).

   Bunlar denetim kaydı PR'ında ele alınacak.
8. **Hibrit kanıt gevşekliği.** Kanıt doğrulayıcının eşleştirmesi
   sıkılaştırılacak. Yedekte `kanit` denetiminin "uygun" olması da gözden
   geçirilecek.
9. **Kural ve model anlaşmazlığı.** Kural okuması ile dil modeli okuması
   anlaşmazsa uygulanacak kural ayrı bir PR'da ekleniyor; bu doküman onu
   henüz anlatmıyor.
10. **Demo onayı işareti.** Örnek kabul dokümanları onaylı sayılabilir,
    ama ekranda ve veritabanında "demo onayı" olarak işaretlenmeleri
    gerekiyor. Bugün bu bilgi yalnız serbest metin notlarda durur. Denetim
    kaydında "örnek veri, M&P onayı değil" yazar. `dokuman_surumleri.not_`
    sütununda da `data/ornek/katalog.json`'daki `onay_notu` yazar ("Örnek
    veri: sistemin taslağı, M&P mühendisi onayı değildir."). Giriş kalite
    ekranında sürüm yalnız "onaylayan ornek-veri" olarak görünür
    (`uygulama.py`, `gecerli_dokuman` başlığı); demo olduğu açıkça
    işaretlenmez.
11. **Docker varsayılan parolası.** Compose deneme kullanıcılarını bilinen
    parolalarla açıyor. Parola ilk çalıştırmada belirlenecek ya da ortam
    değişkeninden okunacak; parola yoksa uygulama başlamayacak.
12. **Revizyon ekranı kilidi.** `revizyon_raporu` test kümesi kilidine
    bakmıyor.
13. **Raf ömrü seçimi.** Tek genel kayıt ve tek aday durumları "bilinmiyorsa
    en kısa" kararıyla çelişiyor (bkz. `depo_tablosu`).
14. **Yüklenen dosyanın üzerine yazma.** `dosyayi_kaydet` dosyayı yalnız
    temizlenmiş adıyla yazıyor. Aynı adlı bir yükleme önceki dosyanın
    üzerine yazılır.
15. **Bağlantı sızıntısı.** Streamlit her yeniden çalıştırmada yeni bir
    `Katalog` bağlantısı açıyor ve kapatmıyor.
16. **Rol denetimi yalnız arayüzde.** `ekran_verisi` ve `hat`
    fonksiyonları kullanıcının rolünü denetlemiyor.
17. **Kenar çubuğundaki "sağlam".** Bu ifade yalnız zincirin kendi içinde
    tutarlı olduğunu gösterir; dışarıda saklanan bir özetle
    karşılaştırılmaz (bkz. `zinciri_dogrula`).

18. **Docker'da veri yolları (koddan çıkarım).** `Dockerfile` paketi
    editable olmadan kurar (`pip install --no-deps .`). Bu yüzden
    `ekran_verisi.KOK = Path(__file__).resolve().parents[3]` site-packages
    altını gösterir, `/uygulama`'yı göstermez. İki sonucu var:
    - `BOLUNME` (`data/bolunme.yaml`) bulunamaz ve `standart_yukle` her
      standardı "bölünme dosyası yok" diye reddeder.
    - `hazir_revizyon_raporlari` (`data/cikti`) boş döner.

    `uygulama.py`'nin kendi `KOK`'u doğrudur, çünkü bu dosya
    `/uygulama/src` altından çalıştırılır. Bu madde koddan çıkarılmıştır;
    Docker PR'ında doğrulanıp düzeltilecek.

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
