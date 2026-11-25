# Gece kararları

Nida'nın 25 Kasım 2026 gece talimatı: belirsiz noktada makul karar ver, gerekçesiyle buraya yaz, devam et.
Her karar sabah onaylanmak üzere; yanlışsa geri alınır.

## Alfa Aesar / Spectrum eşleştirmesi ve OCR işareti

1. **MIL-S-81733C de "OCR gerekli" listesinde.** İstenen yalnız MIL-A-46146B idi; ama 81733C de bütün
   sayfaları taranmış (data/raw/pdf_turleri.csv) ve metni okunamıyor. Liste pdf_turleri.csv'deki
   "taranmış" belgelerle aynı tutulsun diye ekledim (test bunu denetliyor). 81733C geliştirme kümesinde
   kalıyor; yalnız çıkarıcılar onu "OCR gerekli" diye reddediyor.
2. **Kısmen taranmış belgeler metin tabanlı sayıldı.** MIL-PRF-23377G (hazır OCR katmanlı), MIL-PRF-27617F
   ve MIL-PRF-81733D (bir sayfası taranmış) şu an kullanılıyor; bunları engellemek mevcut işleri bozardı.
3. **Thermo Fisher de yeni betikle yeniden eşleştirildi.** Tek yöntem olsun diye `deney/coa_eslestirme.py`
   üç tedarikçiyi birden işliyor; Thermo sonucu PR #43'teki ile birebir aynı (259 satır, 223 / 6 / 30) ve
   test bunu sabitliyor.
4. **Sigma-Aldrich eşleştirilmedi.** Tek şartnamesi başka bir düzende ve sertifikası tek lot ("eksik");
   ölçüme girmiyor.
5. **Yeni durum: "var; şartnamede sınır yok".** Spectrum şartnamesinde APPEARANCE gibi sınırı boş kalemler
   var; bunları "sınır farklı" saymak yanıltıcı olurdu.
6. **Birim çevrimi yalnız %, ppm, ppb arasında, kesin oranla.** `10 ppm max` ile `≤0.001%` aynı sayılıyor ve
   "birim çevrilerek" notu düşülüyor. Başka birimler metin olarak karşılaştırılıyor.
7. **044227 Sodium nitrite'in ICP ızgarası şartnamenin "Total Metal Impurities" kalemine bağlandı**
   (`eslesme=toplam`). Şartname elementleri tek tek sınırlamıyor; kontrol listesinde tek soru olarak duruyor.
8. **014103'te "On 18 mesh" ile şartnamenin "+16 screen" kalemi eşlenmedi**: elek farklı, aynı ölçüm değil.


## Colab çıktıları ve sınır yönü kuralı

1. **Colab çıktılarının yeri.** 6 dosya `deney/sonuclar/colab/` altına `git mv` ile
   taşındı (içerik aynı). Klasöre README ve geçici değerlendirme raporu
   (`degerlendirme.md`) da kondu; ürün bu klasörü okumaz. Ayrı PR (#46).
2. **"6. kör nokta" adı.** Depoda numaralı bir kör nokta listesi bulunamadı. Bunu
   mimarideki dil modeli sınırının (docs/mimari.md madde 6) kör noktası olarak
   okudum: madde 6'ya kısa bir paragraf, ayrıntılar ve örnekler için
   `docs/sinir_yonu_hatasi.md` eklendi. Listen başka bir yerdeyse numarayı oraya taşı.
3. **Plan onayı (CLAUDE.md kural 5).** Gece soru sorulmaması istendiği için plan
   ayrıca onaya sunulmadı; aşağıdaki tasarım buraya yazılıp uygulandı. Test önce
   yazıldı (kural 3); alt ajan zinciri yerine aynı sırayla (test → kod) elle çalışıldı.
4. **Çelişkide ne olur?** Red değil, insan incelemesi: sınır `yon="belirsiz"` yapılır,
   sayılar korunur. Gerekçe: kural da metni yanlış okuyabilir; en kötü durumda yanlış
   alarm üretsin, yanlış kabul ya da yanlış red üretmesin.
5. **Metin yön söylemiyorsa ya da karışıksa** (iki yön, ya da aralık ile tek yön
   birlikte) kural karar vermez, model yönü kalır. Bunları da insana göndermek
   şartların büyük kısmını incelemeye düşürürdü; amaç açık çelişkiyi yakalamak.
6. **Koşul aralıkları.** nm, °C ve °F ile yazılan aralıklar test koşulu sayıldı (kural
   çıkarıcısı da °C aralıklarını atlıyor). Kalınlık aralıkları (mil, µm) sayılmadı,
   çünkü numune şartında asıl sınır onlar olabilir; bunlar "karışık" kuralına düşüyor.
7. **Nereye bağlandı?** `deney/yalniz_dil_modeli.belgeden_cikar` (çelişkiler
   `_rapor.json` içinde `yon_celiskileri`) ve ürün sözleşmesi için
   `okuma_yonu_dogrula(HamOkuma)`. Ürün içi dil modeli hattı henüz yok; hibrit hat işi
   bu fonksiyonu çağırmalı.
8. **Yanlış alarm denetimi** `data/gold_taslak` ve `data/gold_codex` ile yapıldı (yalnız
   okundu, ikisi de onaysız): 476 testte 0 çelişki.

## 81733D / 85285E etiketleme kararlarının uygulanması

Nida'nın 25 Kasım kararları (soyulma tablosu satır satır, etiketleme/ambalaj "muayene", bölme düzeyi)
etiketleme kılavuzuna K8–K10 olarak, bağımsız etiketleme istemine Kapsam 8–9 olarak yazıldı.

1. **`muayene` tek başına bir test türü.** Kabul ya da yeterlilikle birleşemez; şema birleşimi reddeder.
   Böylece `kabul_testleri` muayene şartlarını kendiliğinden dışarıda bırakıyor: CoC'de aranmıyor,
   sentetik sertifikaya ve doğru karara girmiyor, yani FAR ölçümüne girmiyor. Karar motorunda kod
   değişikliği gerekmedi. Parti düzeyinde iç muayenenin karara nasıl bağlanacağı (ör. muayene
   girilmeden parti "bekliyor") parti kuralı işine bırakıldı.
2. **"İç muayene" yeni bir sonuç kaynağı (`ic_muayene`).** `muayene` şartında sonuç kaynağı boş
   bırakılırsa şema `ic_muayene` koyuyor; `ic_laboratuvar` verilirse ya da `ic_muayene` başka bir türde
   kullanılırsa hata veriyor.
3. **"Koşul alanı" = yeni `TestSarti.test_kosulu` (serbest metin).** Mevcut `kosullar` listesi depolama
   ve kullanım koşulları içindir; testin uygulandığı sıcaklık/süre/ortam için ayrı bir alan açtım.
   Serbest metin olduğu için alan bazında F1'e girmiyor (`orijinal_metin` gibi); ölçmek istersen sonra
   yapılandırılmış alanlara bölünebilir.
4. **Bölüm = kaydın şart maddesi (`kaynak.madde`).** Bölüm ortalaması her maddenin P/R/F1'inin
   aritmetik ortalaması. Gold'daki kayıt gold'un maddesine, yalnız tahminde olan kayıt tahminin
   maddesine yazılıyor. Bir tablo hem "TABLE I" hem "3.3.1.3" diye kaynaklanabildiği için iki taslak
   aynı şartı farklı bölümlere koyabilir; doğru cevapta hangisinin kullanılacağı kılavuzda zaten
   "şartın yazdığı madde (3.x ya da tablo)" diye tanımlı.
5. **`deney/degerlendir.py` tablosunun sonuna "GENEL (bölüm ortalaması)" satırı eklendi**
   (dp/yp/yn sütunları boş). `--bolumler` bölüm tablosunu da yazıyor. Mevcut bir test son satırın
   "GENEL (mikro)" olduğunu denetliyordu; son iki satırı denetleyecek biçimde güncellendi.
6. **Dil modeli çıkarıcısının istemi (`deney/yalniz_dil_modeli.py`) bu işte değiştirilmedi.** Şemadan
   türeyen JSON şeması `muayene` ve `test_kosulu`'nu kendiliğinden içeriyor; istem metnine kural
   eklemek istem sürümünü değiştirir ve Colab ölçümünü etkiler. Colab işine bırakıldı.
7. **Taslaklar yeni kurallara göre yeniden etiketlenmedi.** Claude taslakları (`data/gold_taslak/`)
   ve Codex dosyaları (`data/gold_codex/`) olduğu gibi kaldı; Codex'i güncel istemle yeniden
   çalıştırmak ve Claude taslağını K8–K10'a göre düzeltmek ayrı iş. Karşılaştırma mevcut dosyalarla
   yeniden çalıştırıldı.
8. **Kanıt kontrolünde tolerans kalıbı X ile ± arasında en çok üç rakamsız sözcüğe izin veriyor**
   ("6 fluid ounces ± 1/8"). Daha uzun aralar yanlış eşleşme riski taşıdığı için alınmadı.

## Gece işi 1: katalog veritabanı

- **Örnek kabul dokümanları `data/cikti/` taslaklarından yüklendi, `data/gold_taslak/`
  kullanılmadı.** Gold taslakları doğru cevap adayıdır; ürünün verisine
  karışırsa ölçüm kirlenir. Sonuç: 81733D ve 85285E çıktılarında kural
  çıkarıcının bulduğu test yok (0 test), yalnız 23377K'da 27 test var. Ekran
  ve karar gösterimi 23377K ile anlamlı.
- **Örnek dokümanlar v1 olarak "onaylı" kaydedildi, onaylayan `ornek-veri`.**
  Giriş kalite yalnız onaylı sürümle karar verebildiği için örnek akışın
  çalışması buna bağlı. Not alanında "M&P onayı değildir" yazar.
- **Onaylı sürümler ayrı tabloda, değiştirilemez.** Taslaklar bu tabloya girmez;
  düzeltme yeni sürümdür. SQLite tetikleyicileri UPDATE ve DELETE'i reddeder,
  içerik okunurken SHA-256 özetiyle denetlenir.
- **Malzeme kodu belirli bir sürüme değil, standart + revizyona bağlı;** karar
  en son onaylı sürümle verilir. Böylece M&P yeni sürüm onaylayınca malzeme
  kaydı değişmeden yeni sürüm geçerli olur.
- **Parti yalnız o malzeme için onaylı tedarikçiden kaydedilebilir;** onaysız
  tedarikçi hata verir (sessizce karantinaya almak yerine).
- **Malzeme kodları, tedarikçiler ve lotlar uydurmadır** (`AST-001`,
  `Örnek Tedarikçi A` ...). Sınıflar: AST-001 Type I Class N, AST-002 Type I
  Class C2, SZD-001 (81733D) Type I Class 1, PUB-001 (85285E) Type I Class H.

## Gece işi 2: karar motoru katalogdan

- **Tip/sınıf katalogdan alınır; sertifikadaki atıf yalnız çelişki için okunur.**
  Çelişirse (`tip_sinif` satırı) insan incelemeli; red değil, çünkü yanlış
  malzeme mi geldi yoksa sertifika mı yanlış yazıldı, insan karar verir.
- **Parti kararı katalogdaki durumlara şöyle eşlendi:** kabul → `serbest`,
  red → `karantina`, inceleme → `bekliyor`. Katalogda "red" diye ayrı durum
  istenmediği için reddedilen parti karantinada tutulur.
- **İki ek denetim:** sertifikadaki tedarikçi onaylı listede yoksa ve partinin
  sipariş revizyonu kabul dokümanının revizyonundan farklıysa insan
  incelemeli. Tedarikçi adı büyük/küçük harf ve boşluk farkını yok sayar;
  başka yazım farkları insana gider.

## Gece işi 3: denetim kaydı

- **Denetim kaydı katalogla aynı SQLite dosyasında** (`denetim_kaydi` tablosu).
  Ayrı dosya da olabilirdi; tek dosya kurulumu ve Docker'ı basitleştirir.
- **Zincir: her kaydın özeti = SHA-256(kendi alanları + önceki özet),**
  anahtarları sıralı JSON üzerinden. Ek olarak tetikleyiciler UPDATE/DELETE'i
  reddeder. Zinciri baştan yeniden yazan birine karşı son özet dışarıda
  saklanmalı; doğrulama komutu `--son-ozet` alır.
- **"Düzeltme" iki şey için kullanılır:** insanın parti kararını değiştirmesi
  (`karari_duzelt`, gerekçe zorunlu) ve M&P'nin taslağı düzeltip onaylaması
  (ekranda, iş 7). Onay ayrı tür (`onay`).
- **PDF sayfası:** karar kaydında her satırın standarttaki sayfası içerikte
  (`KararSatiri.sayfa`); sertifikanın okunduğu sayfa ayrı alanda
  (`pdf_sayfasi`), dil modeli hattından gelir.
- Örnek veri yüklenirken üç doküman sürümü için `ornek-veri` kullanıcısıyla
  onay kaydı yazılır.

## Gece işi 4: raf ömrü

- **Son kullanma = üretim tarihi + raf ömrü,** yıl ve ay takvimle (31 Ocak + 1
  ay = 28 Şubat). Kabul dokümanında "teslim tarihinden itibaren" gibi başka bir
  başlangıç yazsa da üretim tarihi kullanılır ve not düşülür; partide teslim
  tarihi tutulmuyor.
- **Kap türü bilinmiyorsa en kısa raf ömrü alınır** (23377K: metal 1 yıl,
  plastik 6 ay → 6 ay). Güvenli taraf; partiye `kap_turu` girilirse doğru kayıt
  seçilir. Partiler tablosuna `kap_turu` sütunu eklendi; eski veritabanına
  açılışta kendiliğinden eklenir.
- **Uyarı eşiği 30 gün dahil** (kalan ≤ 30 gün → yaklaşıyor).
- **Ömür uzatma testleri yalnız uyarılı partiler için listelenir.** Bugünkü
  kabul dokümanlarında `omur_uzatma` türünde test yok (kural çıkarıcı bu türü
  henüz işaretlemiyor), bu yüzden liste boş ve "tanımlı değil" yazıyor.
  M&P taslağı düzeltirken bu testleri işaretleyince liste dolar.

## Gece işi 5: revizyon etkisi

- **"M&P incelemesi bekliyor" parti durumu değil, ayrı bir işaret**
  (`mp_inceleme` sütunu, malzemede ve partide). Mimari "işaretlenir,
  kilitlenmez" diyor; durum (serbest / karantina / bekliyor) olduğu gibi kalır.
- **Etkilenen = aynı standardın daha eski revizyon harfine bağlı malzemeler**
  ve onların bütün partileri. Daha yeni ya da aynı harfe bağlı olanlar
  etkilenmez.
- **Kapatma iki seçenekli:** `gerek_yok` (malzeme eski revizyonda kalır) ya da
  `yeni_revizyona_gec` (yalnız yeni revizyonun onaylı kabul dokümanı varsa).
  Denetim kaydında `onay` türüyle durur; ayrı bir kayıt türü açmadım, çünkü
  kayıt türleri istekte "karar, onay, düzeltme" olarak sayılmıştı.
- Revizyon yükleme olayı denetim zincirine değil `revizyon_olaylari`
  tablosuna yazılır (zincir türlerini genişletmemek için).

## Gece işi 6: hibrit hat

- **Hibrit hat sertifika tarafında kuruldu.** Standart tarafında `HamOkuma`
  üreten ürün içi çıkarıcı henüz yok (mimari "sıradaki işler" 2); onun için
  yalnız doğrulama adımı (kanıt + sınır yönü kuralı) hazır ve test edildi.
  Okumaları kabul dokümanına çevirmek ayrı bir iş.
- **Sınır yönü kuralı (Colab işi, `kural/yon_dogrulama.py`) birleşmişti;** hat
  `okuma_yonu_dogrula`'yı kullanıyor.
- **Kanıt doğrulayıcı ürüne yeniden yazıldı** (`kural/kanit_dogrulama.py`),
  çünkü `deney/kanit_kontrolu.py` ürün tarafından içe aktarılamaz ve başka bir
  iş yapıyor (gold taslaktaki sayıları PDF'te arıyor). Ürün tarafındaki
  doğrulayıcı modelin okuduğu hücre metnini aynen (yalnız boşluk/harf büyüklüğü
  serbest) söylediği sayfada ve aynı satırda arar.
- **Sayfa numarasını model değil hat yazar** (modele hangi sayfa gönderildiyse).
- **Model yanıt vermezse kural okumasına düşülür,** karar durdurulmaz. Kayıtta
  `yedek` nedeniyle görünür. Alternatif (hepsini insana göndermek) model
  sunucusu kapalıyken bütün partileri bekletirdi.
- **Kural tabanlı sertifika okuyucu eklendi** (yalnız-kural modu için gerekli):
  tablo başlıklarını İngilizce/Türkçe adlarla eşler; 150 sentetik sertifikada
  JSON ile birebir aynı okuyor. Gerçek CoC'lerde denenmedi.
- `tests/test_istem_enjeksiyonu.py`'deki dil modeli testinin beklediği
  `cikarim.sertifika_okuyucu.sertifika_oku(pdf, istemci)` arayüzü artık var; o
  test `--dil-modeli` ile yerel modelle çalıştırılabilir (CI'da atlanır).

## Gece işi 7: Streamlit ekranları

- **Streamlit ayrı bir kilitte** (`requirements-arayuz.lock` = geliştirme kilidi
  + streamlit 1.67.0 ve bağımlılıkları, pip-audit temiz). Ana `test` işi
  değişmedi; CI'a ekran testlerini de çalıştıran `arayuz` işi eklendi.
  pyproject'te isteğe bağlı `arayuz` grubu.
- **Rol yetkileri:** M&P → standart, taslak, revizyon, depo; giriş kalite →
  CoC kontrolü, depo. Depo ekranı iki role de açık (ikisinin de görmesi
  gerekiyor, "iki rol" istendiği için üçüncü bir depo rolü açmadım).
- **Parolalar PBKDF2-SHA256 özetiyle** katalog veritabanında. Deneme
  kullanıcıları yalnız `--ornek-kullanicilar` ile açılır (`mp` /
  `mp-ornek-parola`, `gk` / `gk-ornek-parola`); gerçek kullanım için
  `scripts/kullanici_ekle.py`.
- **Ekrandan standart yükleme test kümesi kilidine uyar:** yalnız
  `data/bolunme.yaml` geliştirme listesindeki standartlardan taslak çıkarılır;
  test kümesi ve bölünmede olmayanlar reddedilir. Ürün `deney/`'i içe
  aktaramadığı için listeyi arayüz kendisi okuyor.
- **Taslak düzeltme tablo üzerinden:** test türleri (kabul / ömür uzatma /
  yeterlilik), sınır (alt, üst, birim, özgün metin), madde, sayfa, sonuç
  kaynağı düzeltilir. Test eklemek/silmek ve koşul/raf ömrü düzeltmek ekranda
  yok (ileride). Taslaklar ayrı `taslaklar` tablosunda, değişebilir; onaylanınca
  değiştirilemez sürüm olur ve taslak kapanır.
- **Yüklenen dosyalar `data/calisma/yuklenen/`** altına güvenli adla yazılır
  (git'e girmez).
- Streamlit'in `AppTest` aracı dosya yüklemeyi desteklemediği için CoC yükleme
  akışı ekran testinde değil, aynı işi yapan fonksiyonlarla test edildi.

## Gece işi 8: ağsız Docker

- **Uygulama yalnız iç ağda** (`internal: true`, dışarı yolu yok). Docker, iç
  ağdaki bir kapsayıcının portunu ana makineye yayınlamadığı için arada küçük
  bir TCP iletici (`docker/yerel_kapi.py`, "kapı") var: iç ağ ile ana makine
  arasında yalnız `127.0.0.1:8501` → `uygulama:8501` taşır. Uygulamanın
  kendisi hiçbir dış adrese ulaşamaz.
- **Yerel model (Ollama) isteğe bağlı profil** (`--profile model`) ve
  uygulamanın ağ ad alanını paylaşır; model uygulamaya `localhost` olarak
  görünür, onun da dışarı yolu yoktur. Model dosyaları birime önceden
  konmalıdır (ağ kapalı olduğu için indirilemez).
- **Deneme kullanıcıları compose'da açık** (`MALZEME_KABUL_ORNEK_KULLANICILAR=1`)
  ki ilk açılışta giriş yapılabilsin; gerçek kullanımda kapatılıp
  `scripts/kullanici_ekle.py` kullanılmalı.
- **İmaja girmeyenler** (`.dockerignore`): `data/gold*`, `data/raw`,
  `data/sentetik`, `data/calisma`, `deney/`, `notebooks/`, `tests/`.
- **Ağ testi** (`scripts/ag_testi.sh`): uygulama kapsayıcısında DNS, TCP ve
  HTTPS denemeleri başarısız olmalı, varsayılan yol olmamalı, ekran
  `127.0.0.1:8501`'den açılmalı. Pozitif kontrol (aynı denemenin kapıdan
  başarılı olması, yani testin gerçekten ağı ölçtüğü) yalnız CI'da açık;
  bu ortamın doğrudan internet çıkışı yok. CI'a `ag-testi` işi eklendi.
- Yerelde Docker Hub hız sınırına takıldığım için taban imajı aynalı kaynaktan
  çektim; Dockerfile değişmedi, standart `python:3.11-slim` kullanılıyor.
