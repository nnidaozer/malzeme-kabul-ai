# Mimari

Durum: 24 Kasım 2026, Nida'nın onayladığı genişletilmiş mimari. Kodda bugün
neyin hazır, neyin iskelet olduğu her bölümün sonunda "Bugün" satırında yazar.

Temel kural değişmez: belgeyi yerel dil modeli okur, kabul/red kararını
yalnızca kesin kurallar verir. Sistem internetsiz çalışır; `src/` altında dış
servis yoktur.

## 1. Roller ve ekranlar

Sistem iki rolle çalışır:

- **M&P mühendisi** (malzeme ve proses): standart yükler, sistemin çıkardığı
  kabul dokümanını gözden geçirip onaylar, yeni revizyonların farklarını
  inceler.
- **Giriş kalite kontrol**: gelen partinin CoC / test raporunu yükler, karar
  alır, iç laboratuvar sonuçlarını girer.

Ayrıca bir **depo ekranı** partilerin raf ömrünü ve durumunu (kabul, red,
bekletiliyor, M&P incelemesi bekliyor) gösterir.

Bugün: Streamlit ekranları `arayuz/uygulama.py` (iş kuralı
`arayuz/ekran_verisi.py`'de, Streamlit'siz test edilir). Giriş
`arayuz/kimlik.py`: kullanıcılar katalog veritabanında, parola PBKDF2 özetiyle;
iki rol:

- `mp`: standart yükle (kural çıkarıcıyla taslak; yalnız bölünmede geliştirme
  kümesindeki standartlar), taslağı tabloda düzelt ve onayla (her düzeltme ve
  onay denetim kaydına), revizyon farkı (hazır raporlar ya da iki PDF) ve yeni
  revizyonu yükleyip M&P incelemelerini kapatma, depo.
- `giris_kalite`: malzeme kodu ve lot seç (yeni lot ekle), CoC yükle (PDF:
  kural ya da hibrit mod; JSON: ham hücreler), karar ve madde referansları,
  parti kararı, gerekçeli düzeltme; depo.

Depo ekranı partileri, durumlarını, M&P işaretini ve raf ömrü uyarılarını
gösterir. Çalıştırma: `streamlit run src/malzeme_kabul/arayuz/uygulama.py`
(deneme verisi ve kullanıcıları: `python scripts/katalog_kur.py --ornek
--ornek-kullanicilar`; gerçek hesap: `scripts/kullanici_ekle.py`). Streamlit
`requirements-arayuz.lock` ile kurulur. Kabul dokümanı ayrıca Markdown/Word
olarak üretilebilir (`arayuz/dokuman_uretici.py`).

## 2. Malzeme kataloğu

Katalog SQLite'ta tutulur ve şu bağları kurar:

```
malzeme kodu ──► standart + revizyon + tip/sınıf ──► onaylı kabul dokümanı sürümü
      └──────► onaylı tedarikçiler
```

Her malzeme kodu tek bir tip/sınıf kombinasyonuna bağlıdır (ör.
`AST-001 → MIL-PRF-23377K, Type I, Class N`). Kararda hangi şartların
uygulanacağı bu kombinasyondan ve şartların `uygulanabilirlik` alanından
çıkar; tip/sınıf sertifikadan tahmin edilmez.

Bugün: `katalog/veritabani.py` SQLite kataloğu kuruyor: standartlar,
malzeme kodları (tip/sınıf), değiştirilemez kabul dokümanı sürümleri
(tetikleyicilerle UPDATE/DELETE reddedilir, her sürüm SHA-256 özeti taşır),
onaylı tedarikçiler ve partiler (lot, tedarikçi, sipariş revizyonu, üretim
tarihi, durum: serbest / karantina / bekliyor). Parti yalnız onaylı
tedarikçiden kaydedilir. Karar için malzemenin standart + revizyonunun en son
onaylı sürümü kullanılır. Kurulum ve örnek veri:
`python scripts/katalog_kur.py --ornek` (data/ornek/katalog.json,
varsayılan veritabanı data/calisma/katalog.sqlite).

## 3. Kabul dokümanı sürümleri ve karar kaydı

Kabul dokümanları değiştirilemez sürümlerle tutulur (v1, v2, ...). Bir sürüm
onaylandıktan sonra değişmez; düzeltme yeni sürümdür. Giriş kalite yalnızca
onaylanmış bir sürümle karar verebilir.

Her karar şunları kaydeder:

- kabul dokümanı ve sürümü,
- kararın dayandığı PDF sayfası (sertifika ve standart),
- model ve istem sürümü (dil modeli kullanıldıysa),
- kararı alan kullanıcı ve zaman.

Bugün: sürümler katalogda (`katalog/veritabani.py`). Denetim kaydı
`kayit/denetim_kaydi.py`: her karar, onay ve düzeltme kullanıcı, zaman,
doküman sürümü, PDF sayfası, model ve istem sürümüyle yalnız eklenir. Her
kayıt kendi alanlarının ve bir önceki kaydın SHA-256 özetini taşır (hash
zinciri); tetikleyiciler UPDATE/DELETE'i reddeder. Zinciri doğrulama:
`python scripts/denetim_dogrula.py [--son-ozet HEX]` (bozuksa çıkış kodu 1).
Kayıtları şu fonksiyonlar yazar:
- `hat/katalog_karari`: `malzeme_koduyla_kontrol(defter=...)` (karar),
  `dokuman_onayla` (onay), `karari_duzelt` (düzeltme)
- `arayuz/ekran_verisi`: `taslak_duzelt` (düzeltme), `taslak_onayla` (onay)
- `hat/revizyon_etkisi`: `mp_incelemesini_kapat` (onay)
- `scripts/katalog_kur.py --ornek`: örnek onaylar

Durum değişikliği ile kayıt bugün ayrı işlemlerde yazılır; kayıt adımı
başarısız olursa durum değişmiş kalır. Tetikleyiciler yalnız uygulamanın
kendi UPDATE/DELETE'ine karşı korur. Dosyaya yazabilen biri `REPLACE`,
`DROP TRIGGER` ya da doğrudan düzenlemeyle onları aşabilir. Ayrıntı
docs/arayuz_sozlesmesi.md "Bilinen açıklar" bölümündedir.
Veritabanını baştan yazabilen biri zinciri yeniden hesaplayabilir; buna karşı
son özet dışarıda saklanmalıdır (`--son-ozet`).

## 3a. Raf ömrü

Partinin son kullanma tarihi = üretim tarihi + onaylı kabul dokümanındaki raf
ömrü (`kural/raf_omru.py`). Yıl ve ay takvimle eklenir, gün/hafta gün olarak.
Kap türüne göre birden çok kayıt varsa partinin kap türü (`partiler.kap_turu`)
seçilir; bilinmiyorsa en kısa raf ömrü alınır. 30 gün (ayarlanabilir) kala
`yaklasiyor`, geçmişse `doldu` uyarısı verilir ve uyarılı partiler için o
tip/sınıfa uygulanan ömür uzatma testleri (`test_turleri` içinde
`omur_uzatma`) listelenir. Rapor: `hat/raf_omru_raporu.raf_raporu`, komut
satırı `scripts/raf_omru.py`.

## 4. Revizyon

Depodaki partiler için **siparişte yazan revizyon** geçerlidir. Standardın
yeni revizyonu gelince etkilenen malzeme kodları ve partiler "M&P incelemesi
bekliyor" olarak işaretlenir, kilitlenmez: kullanım sürer, M&P mühendisi
farkı inceleyip kabul dokümanının yeni sürümünü onaylar ya da gerek olmadığını
kaydeder.

Şart hizalaması madde numarasıyla değil, **test kimliğiyle (ad + metot)**
yapılır; revizyonlar arasında madde numaraları kayar. Şüpheli değişiklikler
(ör. bir sınırın ±0 değişmesi, birimin değişip sayının aynı kalması) ayrıca
işaretlenir.

Bugün: `revizyon/revizyon_karsilastirici.py` farkları buluyor ve şüpheli
değişiklikleri işaretliyor (`supheli_nedenleri`); test tablosu satırlarını
test adıyla eşliyor, metin şartlarını madde numarası ve başlıkla. Ad +
metotla hizalama henüz yok. Parti işaretleme `hat/revizyon_etkisi.py`:
`yeni_revizyon_yukle` yeni revizyonu kataloğa ekler, aynı standardın daha eski
revizyonuna bağlı malzeme kodlarını ve partilerini `mp_inceleme` sütunuyla
"M&P incelemesi bekliyor" işaretler (parti durumu değişmez) ve olayı
`revizyon_olaylari` tablosuna yazar. M&P `mp_incelemesini_kapat` ile
`gerek_yok` ya da `yeni_revizyona_gec` (yeni revizyonun onaylı dokümanı
gerekir) der; kapatma denetim kaydına `onay` olarak yazılır. Komut satırı:
`scripts/revizyon_yukle.py`.

## 5. Sonuç kaynağı ve parti kuralı

Kabul dokümanında her testin bir **sonuç kaynağı** vardır:
`sonuc_kaynagi: "coc" | "ic_laboratuvar"`, varsayılan `coc`. İç laboratuvar
sonuçları ekrandan girilir; bu testler CoC'de aranmaz.

Parti kuralı:

- bir test bile **uygun değil** ise parti **uygun değil** (red),
- uygun değil yoksa ve en az bir test **insan incelemeli** ise parti
  **bekletilir** (inceleme),
- hepsi uygunsa parti **uygun** (kabul).

Bugün: alan şemada var. Karar motoru iç laboratuvar testlerini CoC'de aramıyor
ve sonuç girilemediği için "insan incelemeli" veriyor, yani parti bekletiliyor.
Parti kuralı `kural/karar_motoru.parti_karari`. Katalogla karar
`hat/katalog_karari.malzeme_koduyla_kontrol`: kabul dokümanı malzeme koduna
göre katalogdan (en son onaylı sürüm) gelir, tip/sınıf katalogdan alınır
(sertifikadaki atıf yalnız çelişki denetimi), onaylı tedarikçi ve sipariş
revizyonu denetlenir; parti kararı parti durumuna yazılır: kabul → serbest,
red → karantina, inceleme → bekliyor. Komut satırı: `scripts/karar_ver.py`.

Karar güvenliği (K1-K8): kabul yalnız boş olmayan ve tamamı "uygun" karar
listesiyle verilir; uygulanan kabul testi yoksa belge incelemeye gider.
Geçti/kaldı sonucu beyaz listeyle okunur: metin bilinen bir olumlu ifadeye
birebir eşitse geçti, açık kaldı sözcüğüyse kaldı, geri kalan her şey ("Not
passed", "Pass*", "Conforms to reference") insana gider (liste
`kural/karar_motoru._GECTI`). Tip/sınıf katalogdan gelir ve sertifika atfına
hiçbir zaman düşülmez. `tip_sinif` şu durumlarda insan incelemelidir:
kabul dokümanının ürün tanımı bir tip (sınıf) listesi veriyorsa katalogdaki
tip (sınıf) tanımsızsa ya da listede yoksa; liste yoksa ya da boşsa,
katalogdaki tip (sınıf) tanımsızken en az bir kabul testinin
uygulanabilirliği tipe (sınıfa) bağlıysa. Bağlı kabul testi yoksa (yalnız
yeterlilik testi bağlı olsa bile) o boyutun tanımsız olması karar
engellemez. Katalog kodu "Type"/"Class" öneki ve boşluklar atılarak okunur
("Class N" → N, "C 2" → C2, "TYPE 2" → II). Ürün tanımı yokken tanımlı kod,
dokümanın uygulanabilirlik kodlarında ya da standardın bilinen kodlarında
(`karar_motoru.BILINEN_KODLAR`; MIL-PRF-23377: Type I/II, Class C1/C2/N)
yoksa `tip_sinif` insan incelemelidir; bilinen kodu kayıtlı olmayan
standartta yalnız o boyuta bağlı kabul testi varken dokümanın kodlarına
bakılır. Sertifikada
tedarikçi yoksa `tedarikci` insan incelemelidir. Lot verilince `parti_no`
(sertifikadaki parti no = lot) ve `parti_tedarikcisi` (sertifikadaki tedarikçi
= partinin tedarikçisi) de denetlenir. Makine parti durumunu yalnız daha
kısıtlayıcı yöne değiştirir (serbest < bekliyor < karantina); tek istisna hiç
karar verilmemiş yeni partidir (`partiler.durum_kaynagi` boş). Karantinadaki ya
da karar verilmiş bekleyen partiyi makine serbest bırakmaz; `parti_durumu` ek
denetimi nedenini yazar, serbest bırakma `karari_duzelt` ile yapılır. Eski
veritabanlarında sütun eklenirken mevcut partiler `bilinmiyor` (karar
verilmiş) sayılır. Bu göç (sütun ekleme + doldurma) tek bir işlemdir; düşerse
sütun da geri alınır ve sonraki açılış yeniden dener. `durum_kaynagi` CHECK
kısıtıyla yalnız boş, `makine`, `insan` ya da `bilinmiyor` olabilir;
`parti_durumu_ata` kaynağı zorunlu ister.

## 6. Dil modelinin sınırı

Dil modeli **yalnızca** şunları döndürür (`sozlesme/okuma.py`, `HamOkuma`):

- ham metin (belgede yazdığı gibi, ör. "15 to 30 seconds"),
- kaynak konum (sayfa, madde, tablo satırı),
- sınır yönü (en_az, en_cok, aralik, tam, belirsiz).

Sayıya çevirme, pint birimine normalleştirme, birim dönüşümü ve sınırla
karşılaştırma kurallarda yapılır (`kural/`). Sözleşmede sayı, birim ya da
karar alanı yoktur; şema bunu zorlar (`tests/test_okuma_sozlesmesi.py`).

**"Yalnız dil modeli" modu** (modelin doğrudan `TestSarti` yazması) yalnızca
`deney/` klasöründen çalıştırılabilir ve ürünün içinde bulunmaz
(`deney/yalniz_dil_modeli.py`, `deney/dil_modeli_cikar.py`).
`tests/test_katmanlar.py` ürünün `deney/` paketini içe aktarmadığını denetler.

**Kör nokta 6, sınır yönü hatası:** model sayıyı doğru okuyup yönü çevirebilir
("≤ 1 ppm" → alt sınır). Bu yüzden modelin yönü, özgün metinden kuralla
çıkarılan yönle ayrıca karşılaştırılır (`kural/yon_dogrulama.py`); çelişen
yön "belirsiz" yapılır ve şart insan incelemesine gider. Örnekler ve kural:
docs/sinir_yonu_hatasi.md.

Bugün: sözleşme hazır. Standart tarafında `HamOkuma` üreten ürün içi dil
modeli çıkarıcısı hâlâ yok; okumaları doğrulayan adım hazır
(`hat/hibrit_hat.standart_okumalarini_dogrula`: kanıtsız okuma reddedilir,
yönü metinle çelişen okuma `belirsiz` yapılır). Yalnız dil modeli deneyi
çalışıyor.

**Hibrit hat** (`hat/hibrit_hat.py`, sertifika tarafı): mod anahtarı `kural`
ya da `hibrit` (parametre ya da `MALZEME_KABUL_MODU`, varsayılan `kural`).
Açıkça verilen boş mod (`""`) hatadır (`HatHatasi`); betik bunu ve diğer hat
ayarı hatalarını stderr'e yazıp sıfır olmayan kodla çıkar, karar yazmaz.

- `kural`: `cikarim/sertifika_okuyucu.kural_ile_oku` PDF tablosunu başlık
  adlarıyla okur (150 sentetik sertifikanın hepsinde JSON ile aynı).
- `hibrit`: her sayfa yerel modele (yalnız localhost) gider; model hücreleri
  aynen döner (`sozlesme/okuma.SertifikaOkumaYaniti`, karar ve sayı alanı
  yok). Her satır `kural/kanit_dogrulama.satir_kaniti` ile belgenin metin
  katmanında aranır: test adıyla başlayan satır sayfada tam bir olmalı (iki
  satır varsa ikisi de kanıtsız; biri gizli metin olabilir); sonuç o satırda,
  bütün sözcükler olarak geçmeli, birim aynı satırda ve ardından şart
  sözcüğü gelmeyen bir yerde geçmeli ("70 min max 47 s" → "47 min" kanıtsız);
  sonuçtan önce işaret ya da olumsuzluk ("<", "-", "Not"), sonra şart sözcüğü
  ("max", "min") olmamalı ("1 ppm max" şart sütunudur). Sarılan hücre ancak
  satırın sonundan sonraki satırın başına taşabilir. Üst bilgiler (tedarikçi,
  sertifika no, parti no, üretim tarihi) `deger_kaniti` ile sayı ve sözcük
  sınırıyla, standart atfı `atif_kaniti` ile tam atıf olarak aranır
  ("MIL-PRF-23377K", belgede "... Type II" iken kanıt değildir; bilinen
  etiketler "Standart Şartname:", "Şartname:", "Specification", "Spec."
  iki taraftan da atılır). Parti ve sertifika numarasının iki yanında harf,
  rakam ya da "-" olamaz; etikete yapışık değer yalnız üretim tarihinde
  kabul edilir. Sonucun önünde "max/min" (önceki sayının eki değilse), "to",
  "NMT", "NLT" varsa ya da sonuç bir aralıksa ("15-23") şarttır; birimi "min"
  gibi şart sözcüğü olan okuma sonuca bitişik olmalı ve ardından şart dışı
  bir sayı gelmemelidir ("5 min 6"). Kural ve model okumasının tedarikçi,
  parti no, sertifika no ve üretim tarihi farkı da anlaşmazlıktır
  (`test_id=<alan>`). Kanıtsız
  satırlar ve alanlar karara girmez (alan boşaltılır; ör. tedarikçi yoksa
  `tedarikci` denetimi insan incelemeli) ve `kanit` denetimi insan incelemeli
  olur; model hiç satır okumadıysa da `kanit` insan incelemelidir. Kanıtsız
  okumayı `Sertifika` olarak döndüren arayüz yoktur (eski
  `sertifika_okuyucu.sertifika_oku` kaldırıldı). Belge metnindeki `<belge>`
  benzeri etiketler istemde `[belge]` yapılır; sınırlayıcı kapatılamaz.
  Model yanıt vermezse, şemaya uymazsa ya da sunucu beklenmedik yanıt
  dönerse (`cikarim/yerel_model.YEDEK_HATALARI`: OSError, ValueError,
  `ModelYanitHatasi`; yalnız `sohbet` çağrısından gelen KeyError, TypeError,
  IndexError ve HTTPException `ModelYanitHatasi`'na sarılır) kural okumasına
  düşülür ve kayda yazılır.
- Okuma anlaşmazlığı: hibritte model başarılıysa sertifika `kural_ile_oku` ile
  de okunur ve `kural/okuma_karsilastirma.sertifika_okumalarini_karsilastir`
  iki okumayı karşılaştırır: standart atfı (belge no, revizyon, tip, sınıf)
  ve test satırları (değer, birim, satır). Satırlar `kontrol_et` ile aynı
  kümeye eşlenir (`karar_motoru.aranan_testler`, katalogdaki tip/sınıf).
  Karşılaştırma tamamen kuralla yapılır; birimler pint ile aynı birime
  çözülüyorsa eşittir, değer çevrilmez. Karara modelin okuması girer;
  anlaşmazlıkta hiçbir okuma sessizce karara girmez: şart (atıfta `revizyon`
  satırı) insan incelemeli olur ("kural ve model farklı okudu: ..."); iki
  okuma da kural motoruna göre sınır dışındaysa uygun değil kalır.
  `okuma_uyumu` ek denetimi insan incelemeli olur (kabul dokümanı verilmeden
  okunduysa da: "karşılaştırma yapılamadı"), anlaşmazlıklar
  `hat.anlasmazliklar` / `hat.anlasmazlik_sayisi` olarak karar kaydına
  yazılır (ileride güven skoru girdisi). Standart tarafında
  `standart_okumalarini_dogrula(..., kural_dokumani=...)` modelin sınır ve
  yönünü kural dokümanıyla karşılaştırır; farklı okuma `belirsiz` olur.
- Karar her iki modda `hat/katalog_karari` ile verilir; kayıtta mod, model ve
  istem sürümü (`sertifika-okuma-v2`; v2 belge sınırlayıcısını kaçışlar) bulunur. Komut satırı:
  `scripts/sertifika_kontrol.py`. Testler sahte modelle çalışır.

**Standart tarafı hibrit (deney):** ürün içi standart çıkarıcısı gelene kadar
standart için hibrit yalnız deney olarak tanımlıdır (`deney/hibrit_standart.py`,
üç modu yan yana çalıştıran betik `deney/uc_mod.py`):

- Kural öncelikli: kural çıktısının bütün kayıtları aynen kalır.
- Model tamamlar: kuralla eşleşmeyen dil modeli testi, özgün metni söylediği
  sayfada (`kanit_dogrulama.metin_sayfada_mi`) bulunursa eklenir; kanıtsız
  test atılır ve rapora yazılır.
- Sınırı kural hesaplar: eklenen testin sınırı modelden alınmaz,
  `kural_cikarici.sinir_cikar` ile özgün metinden yeniden çıkarılır.
- Anlaşmazlıkta yön belirsiz: kuralla eşleşen, aynı maddedeki ve kanıtlı
  dil modeli testinin sınırı kuralınkiyle karşılaştırılır. Tek hata tek
  kayıt: kriter türü farklıysa yalnız `kriter_turu`, değilse yön farklıysa
  yalnız `yon`, değilse farklı olan her `alt`, `ust`, `birim` (pint ile)
  için bir kayıt. Madde numarası farklı çift eşleşmemiş sayılır (model testi
  kanıt yoluna gider). Anlaşmazlıklı kural testinin sayısal sınırı
  `yon="belirsiz"` yapılır (sayılar korunur) ve karar insan incelemesine
  gider. Sayısal olmayan sınır işaretlenemez, `isaretlenemeyen` listesine
  yazılır. Güven skorunun girdisi için birincil sayı anlaşmazlıklı test
  sayısıdır.
- Dil modelinin ara kaydı (`<ETIKET>_ara/sayfa_NNN.json`) model, arka uç,
  düşünme, bağlam, sistem istemi ve şemadan türetilen parmak iziyle yazılır;
  iz değişirse kayıt kullanılmaz. İstek hatası alan sayfa kayda girmez.

## 7. Ölçüm

- **Yanlış kabul oranı (FAR)** hem parametre (test satırı) hem parti (belge)
  düzeyinde, %95 Wilson güven aralığıyla raporlanır. Birincil ölçüt parti
  düzeyidir. (`deney/karar_olcumu.py`, `deney/karar_olc.py`)
- Alan bazında F1 ve belge başına süre önceki gibi ölçülür
  (`deney/degerlendirme.py`).
- Gerçek CoA'lardan ölçüme yalnız **tam** olanlar girer: ürünün en az iki lotu
  ve sertifikadan ayrı bir şartnamesi var. Eksik olanlar nedeniyle birlikte
  `data/coa_kumesi.csv`'de ayrı listelenir (`deney/coa_kumesi.py`,
  `olcum_sertifikalari`).
- Gerçek CoA'ların her test satırı ürün şartnamesindeki karşılığıyla
  `deney/coa_eslestirme.py` ile eşleştirilir (Thermo Fisher, Alfa Aesar,
  Spectrum Chemical; beş CoA düzeni). Sonuç `data/coa_eslesme/` altındadır;
  test, dosyanın betik çıktısıyla güncel olduğunu denetler. Sınırlar yalnız
  %, ppm, ppb arasında kesin oranla çevrilerek karşılaştırılır; karar yoktur.
- Standartlar `data/bolunme.yaml` ile **geliştirme** ve **test** kümesine
  ayrılır (`deney/bolunme.py`):
  - **Geliştirme:** MIL-PRF-23377 (G, H, J, K), MIL-PRF-81733 (C, D) ve
    MIL-PRF-85285 (E, F). Bunlara (ya da ailelerine) zaten bakıldı;
    görülmemiş sayılmazlar.
  - **Test:** yeni indirilen standartların (`yeni_standartlar`) revizyon
    ailelerinin sabit tohumla seçilen rastgele yarısı (tekse yukarı
    yuvarlanır); bir ailenin bütün revizyonları aynı kümeye gider, kalan
    aileler geliştirmeye. Aile, ön ek ve revizyon harfi atılmış standart
    numarasıdır (MIL-S-81733C ile MIL-PRF-81733D aynı aile). 24 Kasım 2026
    seçimi: 46146, 53022, 81309, 85570 ve 87937 aileleri test kümesinde.
  - **Kilitli klasörler:** `kilitli_klasorler` altındaki klasörlerin belgeleri
    (şimdilik `data/raw/gercek_coc_havacilik/`: gerçek havacılık CoC'si ve test
    raporu) doğrudan test kümesindedir ve aynı kilitle açılmaz;
    `scripts/pdf_tur_kontrol.py` bunları açmadan "kilitli" diye listeler. Seçim `python deney/bolunme.py --sec` ile yapılır ve dosyaya
    yazılır; dosya okunurken seçimin tohumla uyuştuğu denetlenir.
  - **Taranmış belgeler:** bütün sayfaları taranmış standartlar (`ocr_gerekli`:
    MIL-A-46146B, MIL-S-81733C) kümelerinden çıkarılmaz; OCR eklenene kadar
    çıkarıcı ve ölçüm betikleri bunları "OCR gerekli" diye reddeder
    (`OcrGerekli`). Sonuçlar raporlanırken taranmış ve metin tabanlı belgeler
    ayrı gösterilir (`Bolunme.turlere_ayir`, `python deney/bolunme.py --turler`).
    Liste `data/raw/pdf_turleri.csv`'deki "taranmış" belgelerle aynı tutulur.
  - Yeni standartlar gelene ve seçim yapılana kadar test kümesi **bekliyor**
    (`test_durumu: bekliyor`); bu sürede yeni standartların hiçbirine bakılmaz.
  - Test kümesindeki standartlara kimse bakmaz: dil modeli çıkarıcısı
    dondurulana kadar (`test_kumesi_acik: false`) çıkarıcı çalıştırılmaz,
    taslak cevap hazırlanmaz. Kilit şu betiklerde zorlanır:
    `scripts/kabul_dokumani_uret.py`, `scripts/revizyon_karsilastir.py`,
    `deney/dil_modeli_cikar.py`, `deney/kanit_kontrol.py`,
    `deney/taslak_karsilastir.py`, `deney/kontrol_listesi_uret.py`,
    `deney/degerlendir.py`. Bölünmede hiç olmayan standart da reddedilir.
    Kilidi yalnız proje sahibi açar.

## Şema eklemeleri

| Alan | Yer | Anlamı |
|---|---|---|
| `urun_tanimi` | `KabulDokumani` | Tip, sınıf ve kompozisyon tanımları (`UrunTanimi`: `tipler`, `siniflar`, `kompozisyonlar`; her kayıt kod, açıklama, kaynak). Şart değildir (etiketleme kılavuzu K2). |
| `uygulanabilirlik` | `TestSarti`, `Kosul`, `RafOmru`, `NumuneHazirlama` | Şartın geçerli olduğu kodlar, ör. "Chromium content (class N only)" için `["Class N"]`. Boşsa hepsi. Ürün tanımı doluysa her kod orada tanımlı olmalı. |
| `yon` | `Sinir` | `en_az`, `en_cok`, `aralik`, `tam`, `belirsiz`. Boşsa alt/üst sınırdan çıkarılır. Yazılmışsa alt/üst ile tutarlı olmalı. `belirsiz` (ör. 23377K 3.11: "en az" mı "tam" mı belli değil) → karar motoru karşılaştırmaz, insan incelemesine gönderir. |
| `sonuc_kaynagi` | `TestSarti` | `coc` (varsayılan) ya da `ic_laboratuvar`. |

Eski JSON dosyaları (yeni alanlar olmadan) aynen okunur.

## Klasör yapısı

```
src/malzeme_kabul/
  sozlesme/   şemalar: kabul dokümanı (sema), sertifika, dil modeli okuması (okuma)
  belge/      PDF okuma, PDF türü, dosya adlandırma
  cikarim/    kural tabanlı çıkarıcı, yerel dil modeli istemcisi (yalnız localhost)
  kural/      birimler, karar motoru (kabul/red yalnız burada)
  revizyon/   revizyon farkları ve güncelleme önerileri
  katalog/    SQLite katalog, doküman sürümleri, onaylı tedarikçiler, partiler
  kayit/      zincirli denetim kaydı (karar, onay, düzeltme)
  hat/        belge → okuma → kanıt → kural → karar → kayıt hattı (kural / hibrit), katalogla karar, revizyon etkisi, raf ömrü raporu
  arayuz/     Streamlit ekranları (uygulama.py), ekran verisi, kimlik, kabul dokümanı çıktısı (Markdown/Word); sözleşme: docs/arayuz_sozlesmesi.md
deney/        yalnız dil modeli deneyi, ölçüm (F1, FAR), sentetik sertifika, gold taslak araçları
scripts/      ürün betikleri (kabul dokümanı üret, revizyon karşılaştır, PDF türü), hook'lar, CI
data/
  raw/        standart PDF'leri
  sentetik/   sentetik sertifikalar ve doğru kararları
  ornek/      katalog örnek verisi (uydurma malzeme kodu, tedarikçi, lot)
  bolunme.yaml  geliştirme / test bölünmesi
  coa_kumesi.csv  gerçek CoA'ların tam / eksik listesi (deney/coa_kumesi.py)
  coa_eslesme/    CoA test satırlarının şartname karşılıkları (deney/coa_eslestirme.py)
  calisma/    yerel çalışma verisi (SQLite, kararlar, yüklenen belgeler); git'e girmez
  gold/       doğru cevaplar (yalnız proje sahibi yazar)
```

Bağımlılık yönü: `sozlesme` yalnız kendine ve `kural/birimler`'e bağlıdır;
`kural` dil modeli istemcisine bağlanmaz; ürün `deney/`'i hiç içe aktarmaz.
Hepsi `tests/test_katmanlar.py` ile denetlenir.

Deney betikleri depo kökünden çalıştırılır, ör.
`python deney/karar_olc.py ...` ya da `python -m deney.karar_olc ...`.

## Sıradaki işler

1. Colab defterini çalışır hale getirmek.
2. Dil modeli çıkarıcısı (`HamOkuma` üreten, ürün içi).
3. Katalog ve onay akışı (sürümler, karar kaydı, revizyon işaretleme).
4. Streamlit ekranları (M&P, giriş kalite, depo).
