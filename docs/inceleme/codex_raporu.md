# Codex inceleme raporu

28 Kasım 2026 · İncelenen `origin/main` sürümü: `049750e` (PR #69).

Git geçmişi görevdeki on PR'ın birleştiğini doğruluyor. Sonradan gelen parola (#63), karar (#64), hibrit kanıt (#65), denetim (#66), raf ömrü ve revizyon kilidi (#67) ve demo onayı (#68) düzeltmeleri güncel kod üzerinden değerlendirildi. İnceleme sırasında GitHub API açık PR listelemesi boş döndü.

## Bulgular

### PR #52 · Sınırın dışındaki değer dönüştürme sırasında sınıra yuvarlanıyor

- **Önem:** kritik.
- **Yer:** `src/malzeme_kabul/kural/karar_motoru.py:289`, `:303`, `:448`.
- **Senaryo:** En çok 1 saniye şartına karşı sertifikada 1.0000000000004 saniye yazarsa, dönüşüm sonrası 12 anlamlı basamağa yuvarlanan değer 1 olur ve satır uygun çıkıyor. Diğer denetimler uygunsa bu sonuç ilk lot kararında serbest bırakmaya kadar gider.
- **Öneri:** Ölçüm hassasiyeti ve birim dönüşümü için ortak bir sınır politikası belirle. Yakın sınırdaki sayıları kabul yönünde yuvarlamadan karşılaştır.
- **Test:** Üst sınırın hemen üstü ve alt sınırın hemen altı için aynı ve çevrilen birimleri, ayrıca tam sınır için kabulü dene.

### PR #52 ve #56 · Hibrit karşılaştırma ile parti kararı farklı katalog sürümlerini kullanabiliyor

- **Önem:** kritik.
- **Yer:** `src/malzeme_kabul/hat/hibrit_hat.py:247`, `src/malzeme_kabul/hat/katalog_karari.py:204`, `:223`.
- **Senaryo:** Hibrit okuma başladıktan sonra M&P ikinci bir doküman sürümü onaylar ve yeni bir kabul testi ekler. İlk sürüm yeni testi aramadığı için kural ve model arasında o testteki fark karar kaydına yansımaz. Karar motoru ikinci sürümü tekrar yüklediğinde modelin sonucu kabul koşulunu sağlayabilir.
- **Öneri:** Kanıt, okuma karşılaştırması ve karar boyunca aynı sürüm ve tip/sınıfı taşı. Durumu yazmadan önce karar dayanağının hâlâ geçerli olduğunu kontrol et.
- **Test:** Model çağrısını beklet, ikinci SQLite bağlantısıyla yeni bir kabul testi olan sürümü onayla ve model ile kuralın o testte ayrıştığı durumda serbest bırakma olmadığını doğrula.

### PR #61 · Negatif sınır işareti karşılaştırmaya girmiyor

- **Önem:** önemli. Standart tarafında ürün içi model çıkarıcısı henüz bu adımı beslemiyor.
- **Yer:** `src/malzeme_kabul/kural/okuma_karsilastirma.py:244`, `tests/test_okuma_anlasmazligi.py:314`.
- **Senaryo:** Aynı yöne sahip -5 ve 5 sınırları, metinden işaretsiz sayılar toplandığı için aynı kabul ediliyor.
- **Öneri:** Tekil negatif değer ve aralık ayırıcısı için ortak sınır ayrıştırma kuralları belirle.
- **Test:** Mevcut strict xfail senaryosunu, Unicode eksi ve negatif aralığı kapsayacak şekilde genişlet.

### PR #52 ve #61 · Boşlukla ayrılan Roma rakamı revizyon sayılıyor

- **Önem:** önemli.
- **Yer:** `src/malzeme_kabul/kural/karar_motoru.py:143–159`, `tests/test_okuma_anlasmazligi.py:821`.
- **Senaryo:** `MIL-PRF-23377 I` atfındaki ayrı `I` revizyon olarak yorumlanıyor. Atıfta yalnız tip kastedildiyse karar motoru eksik revizyonu gerçek revizyon gibi karşılaştırıyor.
- **Öneri:** Belirsiz tek harfli atıfları insan incelemesine bırak. Açık revizyon işareti ve standart numarasına bitişik revizyon için mevcut kuralları koru.
- **Test:** Ayrı `I`, açık `REV I`, bitişik revizyon ve açık `TYPE I` atıflarını birlikte doğrula.

### PR #61 · İki okuma da red verdiğinde şart red kalıyor

- **Önem:** küçük, inceleme talimatı ile mevcut davranış arasında karar politikası farkı.
- **Yer:** `src/malzeme_kabul/kural/okuma_karsilastirma.py:137`, `tests/test_okuma_anlasmazligi.py:719`.
- **Senaryo:** Kural ve model farklı iki sınır dışı değer okur. Fark kayda girer ve `okuma_uyumu` insan incelemeli olur, ancak şart ve parti red kalabilir. Görev belgesi her anlaşmazlıkta şart için insan incelemesi istiyor.
- **Öneri:** M&P iki okumada da red varsa sonucun korunup korunmayacağını belirlesin. Görev belgesi, mimari ve sözleşmede aynı kural yazsın.
- **Test:** İki farklı sınır dışı okumada seçilen şart ve parti sonucunu, ayrıca `anlasmazliklar` ile `anlasmazlik_sayisi` alanlarını birlikte doğrula.

### PR #57 ve #52 · Giriş kalite ekranı M&P'ye atfedilen serbest bırakmayı yapabiliyor

- **Önem:** kritik.
- **Yer:** `src/malzeme_kabul/arayuz/uygulama.py:257`, `:337`, `src/malzeme_kabul/hat/katalog_karari.py:155`, `:287`.
- **Senaryo:** Giriş kalite kullanıcısı karantinadaki lot hakkında karar alır ve açık düzeltme formundan gerekçe ile `serbest` seçer. Kayıt yazılır, ancak karar satırında M&P'ye atfedilen yetki giriş kalite ekranından kullanılabilir. Sözleşmenin 16. maddesi alt katmanda rol kontrolü eksikliğini zaten anlatıyor. Bu bulgu ekranda sunulan geçişe ilişkindir.
- **Öneri:** Düzeltme ve serbest bırakma yetkilerini rol ve geçiş bazında tanımla, geçişi işlem sınırında doğrula.
- **Test:** Aynı karantinadaki lot için giriş kalite ve M&P hesaplarıyla düzeltme dene. Yetkisiz geçişte durum ve zincir değişmemeli.

### PR #53 ve #57 · Karar tamamlanmadan yeni lot kalıcılaşıyor

- **Önem:** kritik.
- **Yer:** `src/malzeme_kabul/arayuz/uygulama.py:235`, `src/malzeme_kabul/arayuz/ekran_verisi.py:237`, `src/malzeme_kabul/katalog/veritabani.py:584`.
- **Senaryo:** Kullanıcı yeni lotla bozuk bir sertifika yükler. Lot önce katalogda `bekliyor` olarak oluşturulur. Ardından sertifika reddedilir ve karar kaydı oluşmaz. Kullanıcı işlemin başarısız olduğunu görürken depo yeni lotu gösterir.
- **Öneri:** Lot kaydını ayrı, denetimli bir olay olarak tanımla veya başarılı karar yazımıyla birlikte kalıcılaştır.
- **Test:** Yeni lot için geçersiz JSON ve denetim yazma hatasını ayrı ayrı simüle et. Seçilen tasarıma göre lotun yokluğunu veya kayıtlı lot oluşturma olayını doğrula.

### PR #54 · Raf ömrü sipariş revizyonundan kopuyor

- **Önem:** önemli.
- **Yer:** `src/malzeme_kabul/hat/raf_omru_raporu.py:38`, `src/malzeme_kabul/hat/revizyon_etkisi.py:131`.
- **Senaryo:** J ile sipariş edilmiş lot için J raf ömrü 6 ay, K raf ömrü 12 ay olsun. Malzeme kodu K'ya taşındığında depo, eski lot için K'nın 12 aylık süresini gösterebilir. Mimari depodaki lot için sipariş revizyonunun geçerli olduğunu söylüyor.
- **Öneri:** Raf hesabının dayanağını lotun sipariş revizyonuna bağla. Bu revizyon için onaylı doküman yoksa raporda belirsizlik göster.
- **Test:** Farklı raf ömrü olan iki revizyonla eski ve yeni lot oluştur, malzeme kodunu yeni revizyona taşı ve iki lotun kendi sürelerini koruduğunu doğrula.

### PR #55 · Olay yazımı başarısız olursa revizyon ve M&P işaretleri kalıcılaşıyor

- **Önem:** kritik.
- **Yer:** `049750e:src/malzeme_kabul/hat/revizyon_etkisi.py:78–89`.
- **Senaryo:** Katalog revizyonu ekler ve eski malzemelerle lotları işaretler. Ardından `fark_ozeti` JSON'a dönüştürülemez veya olay INSERT'i başarısız olursa çağrı hata verir, değişiklikler olay olmadan kalır.
- **Düzeltme:** PR, katalog, lot işaretleri ve olay kaydını mevcut `Katalog.islem` sınırına alıyor.
- **Test:** Bellek içi katalogda olay yazımı sırasında hata oluştur. Yeni revizyonun ve işaretlerin geri alındığını, geçerli tekrarın tek olay oluşturduğunu doğrula.

### PR #57 ve #58 · Tehdit modeli mevcut dağıtımı yansıtmıyor

- **Önem:** küçük, doküman tutarsızlığı.
- **Yer:** `docs/guvenlik.md:34`, `:136`, `:174` · `Dockerfile:16`, `:36` · `docker-compose.yml:16`.
- **Senaryo:** Tehdit modelini uygulayan bir incelemeci arayüz ve konteynerin bulunmadığını varsayar. Mevcut dağıtımda Streamlit, iki rol, ana makinede loopback portu ve ayrı TCP geçidi var.
- **Öneri:** Tehdit modeline oturum ve yükleme yüzeyini, ağ sınırlarını, konteyner ayarlarını ve uygulanmış PDF/bağımlılık önlemlerini ekle.
- **Test:** Tehdit modelinde belirtilen servis, port, kullanıcı ve dosya sistemi özelliklerini Compose yapılandırmasıyla karşılaştır.

### PR #58 · Windows çalışma kopyasında Docker giriş betiği CRLF olabiliyor

- **Önem:** önemli.
- **Yer:** `Dockerfile:32`, `:40`, `docker/baslat.sh:8`.
- **Senaryo:** `core.autocrlf=true` olan Windows çalışma kopyasında Docker giriş betiği CRLF oluyor. Betiği POSIX kabuğunda çalıştıran mevcut test `set: Illegal option` hatası verdi. Dockerfile aynı betiği imaja kopyalayıp `sh` ile başlatıyor.
- **Düzeltme:** `.gitattributes`, kapsayıcının giriş betiğini LF ile çalışma kopyasına çıkarıyor.
- **Test:** `git ls-files --eol docker/baslat.sh` çıktısında `w/lf` ve `text eol=lf` değerlerini doğrula. `test_baslat_sh_ile_bash_olmadan_calisir` testini tekrar çalıştır.

## Arayüz sözleşmesindeki bilinen maddeler

| Madde | Durum | Kanıt |
|---|---|---|
| 1 · Olumsuz sonuç | Yanlış anlatılmış, #64 ile kapandı | `karar_motoru.py:262–266` olumlu ifadeyi bütün olarak eşler. |
| 2 · Makineyle karantinadan çıkış | Kapandı | `katalog_karari.py:144–152`. İnsan geçişindeki rol farkı yukarıda. |
| 3 · Lot ve tedarikçi | Kapandı | `katalog_karari.py:105–138`. |
| 4 · Eksik tedarikçi | Kapandı | `katalog_karari.py:91–102`. |
| 5 · Tanımsız tip/sınıf | Yanlış anlatılmış, #64 ile kapandı | `katalog_karari.py:206` açıkça `katalogdan=True` geçiriyor. |
| 6 · Boş test listesi | Yanlış anlatılmış, yanlış kabul #64 ile kapandı | `karar_motoru.py:705–710` uygulanabilir kabul testi yoksa inceleme ekliyor. Boş doküman şemada hâlâ mümkün. |
| 7 · Denetim ve sürüm bütünlüğü | Açık, kısmen kapandı | #66 karar ve kayıt işlemini birleştirdi, denetim tablosunda REPLACE koruması var. Doküman sürümleri, tetikleyici onarım kaydı, demo onay özeti ve dış özet konuları açık. |
| 8 · Hibrit kanıt | Açık, kısmen kapandı | #65 sayfa/satır kanıtını sıkılaştırdı. Yedek `kanit=uygun` ve uygun parti üretebiliyor (`hibrit_hat.py:118–132`). Bu davranış önceki tasarım kararıyla uyumlu. |
| 9 · Okuma anlaşmazlığı | Yanlış anlatılmış, #61 birleşti | `hibrit_hat.py:130–158`, `:227–258`. Standart doğrulama adımı mevcut, standart için ürün içi model çıkarımı bekliyor. |
| 10 · Demo işareti | Kapandı, geçiş kararı açık | #68, `veritabani.py:295` · `revizyon_etkisi.py:131` demo sürümünü ayrıca engellemiyor. |
| 11 · Docker parolası | Kapandı | #63, `docker/baslat.sh:14`, `kimlik.py:177`. CLI örnek hesap yolu kontrollü biçimde mevcut. |
| 12 · Revizyon kilidi | Kapandı, belge kimliği sınırı açık | #67, `ekran_verisi.py:199–223`. Sözleşme kontrolün dosya adına bağlı olduğunu belirtiyor. |
| 13 · Raf ömrü seçimi | Kapandı | #67, `kural/raf_omru.py:86–106`. En kısa süre üretim tarihine göre seçiliyor. |
| 14 · Yükleme üzerine yazma | Açık | `uygulama.py:49–58`. Sözleşme mevcut davranışı doğru anlatıyor. |
| 15 · Bağlantı ömrü | Kapandı | `uygulama.py:302–308`. Katalog `with` bloğunda kapanıyor. |
| 16 · Alt katmanda rol | Açık | `uygulama.py:322–337` · `karari_duzelt` kullanıcı adını alıyor. |
| 17 · Zincir özeti | Açık | `uygulama.py:311–319`. Çağrı dış özet vermiyor. |
| 18 · Docker veri yolu | Kapandı | `Dockerfile:12`, `ekran_verisi.py:49`. Veri kökü ve yazılabilir veri birimi ayrı ayarlanıyor. |

#59 için 1, 5, 6 ve 9. maddeler sözleşme güncellemesi gerektiriyor. 11. maddeye göre ilk hesap kurulumundan sonra uygulama içinde parolalar kullanılmıyor, ancak Compose secret kaynakları yapılandırmada zorunlu kalıyor. Açıklama metinleri mevcut imza ve içe aktarma testinin kapsamı dışında.

## Diğer kontroller

- **#49 katalog:** `db309b3`. Tip/sınıf katalogdan geliyor ve onaylı sürüm içeriği okunurken özet doğrulanıyor. Örnek verinin CLI üzerinden yüklenmesi ve demo onay kayıtları tek işlemde (`scripts/katalog_kur.py:50`). Sürüm REPLACE ve çapraz özet kontrolleri sözleşmenin 7. maddesinde.
- **#53 denetim:** `ea1edfd`. #66 sonrası karar, düzeltme, taslak onayı ve M&P kapatmada katalog ve zincir aynı bağlantıya bağlı. Salt okunur doğrulama CLI'sı şema ve zinciri kontrol ediyor.
- **#56 kanıt:** `550ede0`. Modelin okuduğu satır ve alanlar sayfadaki kanıta bağlanıyor. Yerel istemci loopback'i kabul ediyor, vekil ve yönlendirmeyi izlemiyor. Hibrit yedeğin parti bırakabilmesi sözleşmenin 8. maddesinde.
- **#58 çalışma ağı:** `2327b0a`. `docker/yerel_kapi.py` TCP akışını sabit iç servise taşıyor. `scripts/ag_testi.sh` loopback sağlık kontrolü yapıyor, `scripts/ag_kapali_mi.py` ise yalıtımı ölçmek için dış DNS/TCP/HTTPS erişimini deniyor. Geçit dış ağa bağlı. Uygulama iç ağda, Ollama aynı ağ ad alanını paylaşıyor. Model servisine Compose açıkça loopback bind ayarı vermiyor. Uygulama imajı root olmayan kullanıcıyla çalışıyor. Compose kök dosya sistemini salt okunur yapmıyor ve Python ile Ollama imajları digest ile sabitlenmemiş. Model blob doğrulaması başlangıç yolunda yok. Bağımlılık kilitleri mevcut, CI geliştirme ve arayüz kilitlerini `pip-audit` ile tarıyor.
- **Katmanlar:** Ürün ve deney paketlerinin ayrımı, PDF/ham okuma akışı, Python'da birim dönüşümü ve Streamlit dışındaki ekran veri fonksiyonları kontrol edildi. Karşıt iki okumanın satır sonucunu birleştirme kuralı `kural/okuma_karsilastirma.py` içinde, hat bu kuralı uyguluyor.
- **Birleşen diğer odak PR'lar:** #52 `22bc2c7`, #54 `8e3ff04`, #55 `a459dfb`, #57 `3622111`, #59 `5ebdff6`, #61 `6008ea6`.

## Emin olunmayanlar

- `docker compose --profile model config --quiet` başarılı oldu. Docker Desktop motoru erişilebilir değildi. Canlı ağ yalıtımı, Ollama'nın çalışma anındaki bind adresi ve konteynerde ilk açılış bu incelemede doğrulanamadı.
- Yerel modelle gerçek belge okuması çalıştırılmadı. Model davranışına ilişkin değerlendirme kod, sahte istemci ve sentetik testlerle sınırlı.
- Kilitli test kümesi ve `data/gold*` içeriği açılmadı. Bu nedenle tüm pytest paketi yerine seçili testler esas alındı.

## Doğrulama

- Kilitli geliştirme ve arayüz bağımlılıklarıyla, Windows/Python 3.12 ve Git for Windows kabuğunda seçili 19 pytest modülü çalıştırıldı. **977 geçti, 0 başarısız, 0 atlandı, 2 beklenen başarısızlık (strict xfail).** İki xfail negatif sınır işareti ve ayrı yazılmış Roma rakamı bulgularına karşılık geliyor.
- #61 kontrolleri sertifika değer, birim ve satır farklarını, standart sınır ve yön farklarını, ayrıca anlaşmazlık listesini ve sayısını denetledi.
- Bellek içi katalogda revizyon olayının serileştirme hatası ana dalda kalıcı katalog ve lot işaretleri bıraktı. Düzeltme bunları geri aldı ve geçerli tekrar tek olay yazdı. Ayrı bir sentetik şart testi sınır yuvarlaması bulgusunu doğruladı.
- Docker giriş betiğinin POSIX başlangıç testleri LF düzeltmesinden sonra 7/7 geçti. Docker Compose yapılandırma kontrolü model profiliyle geçti.

DÜZELTME GEREKLİ
