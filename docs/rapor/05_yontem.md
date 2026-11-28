# 5. Yöntem

> Durum: taslak. Kaynaklar: `deney/` ve `src/malzeme_kabul/` altındaki kod,
> `docs/mimari.md` madde 6–7, `docs/sinir_yonu_hatasi.md`,
> `docs/dil_modeli_ortami.md`. Güven skoru (5.7) ve OCR (5.8) bu taslak
> yazılırken ayrı işlerde geliştiriliyordu; teslimden önce kodla
> karşılaştırılıp güncellenmeli.

## 5.1 Karşılaştırılan üç yaklaşım

Çalışma, aynı görevi üç yolla çözüp karşılaştırır:

| Yaklaşım | Standarttan şart çıkarma | Sertifikadan değer okuma | Karar |
|---|---|---|---|
| **Yalnız kural** | Düzenli ifade + belge yapısı (`cikarim/kural_cikarici.py`) | Tablo başlıklarıyla (`sertifika_okuyucu.kural_ile_oku`) | Karar motoru |
| **Yalnız dil modeli** | Model şartı ve sınırı doğrudan yazar (`deney/yalniz_dil_modeli.py`) | Tanımlı değil (deney yalnız standart tarafında) | Karar motoru (modelin yazdığı sınırla) |
| **Hibrit** | Kural öncelikli, model tamamlar, sınırı kural hesaplar (`deney/hibrit_standart.py`) | Model okur, kanıt ve kural okumasıyla denetlenir (`hat/hibrit_hat.py`) | Karar motoru |

Üç yaklaşımda da kabul / red kararını aynı karar motoru verir. Fark,
motorun karşılaştırdığı sınırın ve değerin nereden geldiğindedir. Böylece
ölçülen fark okumanın kalitesinden kaynaklanır, kararın nasıl verildiğinden
değil.

## 5.2 Kural tabanlı çıkarım

Kural çıkarıcı MIL-PRF standartlarının ortak yapısından yararlanır:

1. **Numaralı paragraflar** ("3.6.3 Viscosity. …") madde, başlık, metin ve
   sayfa olarak ayrılır.
2. **Test tablosu** ("Requirement paragraph / Test paragraph / Test method")
   satır satır `TestSarti` olur.
3. **Muayene kapsamı**: yeterlilik muayenesi bütün testleri, kabul
   (conformance) muayenesi "with the exception of …" ile sayılanlar
   dışındakileri kapsar.
4. **Panel tablosu**, **depolama kararlılığı** (raf ömrü ve sıcaklık) ve
   **önlem sayfası** maddeleri (kap ömrü, indüksiyon süresi) ayrıca okunur.
5. **Sınır** (`sinir_cikar`): şart metnindeki sayı, birim ve yön ifadeleri
   ("not more than", "minimum", "15 to 30") düzenli ifadelerle çıkarılır.
   Birim pint'in tanıdığı biçimde yazılır; dönüşüm yapılmaz.

Bu yaklaşım hızlı ve tekrar üretilebilirdir, ama belge düzenine sıkı bağlıdır.
Ön gözlem (`docs/gorulmemis_belgeler_raporu.md`): MIL-PRF-81733D'de tablo
başlık hücreleri satır sonu içerdiği için test tablosu bulunamadı;
MIL-PRF-85285E'de tablo bulundu ama sütun sırası farklı olduğu için satırlar
atlandı.

## 5.3 Dil modeliyle çıkarım

- **Sayfa sayfa okuma**: PDF her sayfa için ayrı istemle modele verilir
  (`deney/dil_modeli_cikar.py`). Bir sayfanın istemi şema dahil yaklaşık
  2.500 token, bağlam 8192 token, yanıt en çok 4096 token.
- **Kısıtlı çözümleme**: çıktı JSON şemasına zorlanır. Şema Pydantic
  modelinden üretilir; Ollama (`format`) ve llama.cpp (`response_format`)
  şemayı dilbilgisine çevirip yalnız geçerli belirteçlerin üretilmesine izin
  verir (Willard ve Louf, 2023). Şemadan geçen çıktı Pydantic ile yeniden
  doğrulanır; geçmeyen şart atılır ve rapora yazılır.
- **Belirlenimci çalışma**: sıcaklık 0. Qwen3 için düşünme kipi kapatılır.
- **Birim adı**: yalnız dil modeli deneyinde model birimi pint'in tanıdığı
  biçimde yazar ("seconds" → "s"). Bu değer dönüşümü değildir ama model
  birimi kendiliğinden çevirebilir (ör. °F → °C); birim alanındaki hatalar bu
  yüzden ayrıca izlenir (`docs/dil_modeli_ortami.md`).
- **Ara kayıt**: her sayfanın sonucu model, arka uç, düşünme ayarı, bağlam,
  sistem istemi ve şemadan türetilen parmak iziyle saklanır; iz değişirse kayıt
  kullanılmaz. Kopan çalışma kaldığı yerden sürer.
- **Belge sınırlayıcısı**: belge metni istemde bir sınırlayıcı içinde verilir;
  metindeki sınırlayıcıya benzeyen etiketler kaçışlanır, böylece belge
  sınırlayıcıyı kapatıp talimat ekleyemez (istem enjeksiyonu; bkz. 5.6).

**Model adayları** (`docs/dil_modeli_ortami.md`): Colab'da 7–8B, 4 bit
(Qwen2.5-7B-Instruct, Llama-3.1-8B-Instruct, Qwen3-8B); dizüstünde 1–3B, 4 bit
(Qwen2.5-3B, Llama-3.2-3B, Qwen2.5-1.5B). Doğruluk aynı model dosyasıyla
donanımdan bağımsız olduğu için F1 Colab'da, süre ayrıca dizüstünde ölçülür.

## 5.4 Hibrit yöntem

Hibrit yöntemin amacı, kuralın kesinliğini korurken dil modelinin esnekliğini
yalnız kuralın kör kaldığı yerde kullanmaktır.

**Standart tarafı** (`deney/hibrit_standart.py`):

1. *Kural öncelikli*: kural çıktısının bütün kayıtları aynen kalır.
2. *Model tamamlar*: kuralla eşleşmeyen model testi, özgün metni modelin
   söylediği sayfada bulunursa (`kanit_dogrulama.metin_sayfada_mi`) eklenir;
   kanıtsız test atılır ve rapora yazılır.
3. *Sınırı kural hesaplar*: eklenen testin sınırı modelden alınmaz, özgün
   metinden `sinir_cikar` ile yeniden çıkarılır.
4. *Anlaşmazlıkta yön belirsiz*: aynı maddede eşleşen kural ve model testinin
   sınırı karşılaştırılır. Kriter türü, yön, alt, üst ya da birim farklıysa
   (her hata tek kayıt) anlaşmazlık yazılır ve kural testinin sınırı
   `yon="belirsiz"` yapılır; karar insan incelemesine gider.

**Sertifika tarafı** (`hat/hibrit_hat.py`): model sayfanın hücrelerini aynen
döndürür (sayı ve karar alanı yok). Her okuma iki denetimden geçer:

- *Kanıt*: test satırı sayfada tam bir kez geçmeli; sonuç o satırda bütün
  sözcük olarak, birim aynı satırda ve şart sütunu olmayan bir yerde geçmeli;
  sonuçtan önce işaret ya da olumsuzluk ("<", "Not"), sonra şart sözcüğü
  ("max") olmamalı. Kanıtsız satır karara girmez.
- *Kural okumasıyla karşılaştırma*: sertifika kuralla da okunur; değer, birim
  (pint ile aynı birime çözülüyorsa eşit) ve standart atfı karşılaştırılır.
  Anlaşmazlıkta şart insan incelemeli olur. İki okuma da sınır dışındaysa
  karar "uygun değil" kalır ve anlaşmazlık kaydedilir (proje sahibinin 28
  Kasım 2026 kararı).

**Sınır yönü doğrulaması** (`kural/yon_dogrulama.py`): bir dil modeli bir
sınırın sayısını doğru okuyup yönünü çevirebilir (ör. "a maximum ... VOC
content of 340 g/L" → alt sınır 340; ön gözlem, `docs/sinir_yonu_hatasi.md`).
Bu hata kanıt kontrolünden geçer, çünkü sayı sayfada vardır; şema da
yakalamaz, çünkü "yalnız alt sınır" geçerli bir sınırdır. Bu yüzden yön,
özgün metindeki ipuçlarından ("not more than", "minimum", "≤", "15 to 30")
kuralla ayrıca çıkarılır ve modelin yönüyle karşılaştırılır. Çelişkide yön
`belirsiz` olur. Metinde ipucu yoksa ya da karışıksa kural karar vermez ve
modelin yönü kalır; bu bilinçli bir ödünleşimdir (aksi halde şartların büyük
kısmı incelemeye düşerdi) ve kuralın kapsamı sınırlıdır.

## 5.5 Karar kuralları

Karar motoru (`kural/karar_motoru.py`) her kabul testi için üç karardan birini
verir: **uygun**, **uygun değil**, **insan incelemeli**. Temel ilke:
belirsizlik hiçbir zaman kabule dönüşmez.

- Okunan değer bir aralık olarak temsil edilir ("320" → [320, 320], "<1" → 1'den küçük, alt ucu açık); aralık sınırın
  tamamen içindeyse uygun, tamamen dışındaysa uygun değil, kısmen örtüşüyorsa
  insan incelemeli. Yuvarlama yapılmaz: standarttaki ve sertifikadaki değerler
  olduğu gibi karşılaştırılır. Birime çevrilmiş değerin bir ucu bir sınıra
  bağıl 1e-6 (sıfır sınırda mutlak 1e-12) kadar yakınsa karar insan
  incelemelidir; birim dönüşümü yoksa ve sayı metni float'a kayıpsız sığıyorsa tam
  eşitlikte dahil/hariç kuralı
  geçerlidir (`docs/sinir_yakinligi.md`).
- Birim pint ile çevrilir; çevrilemeyen birim insana gider.
- Geçti/kaldı sonucu beyaz listeyle okunur: yalnız bilinen olumlu ifadeler
  ("Pass", "Conforms", "Uygun" …) birebir eşleşirse geçti; "Not passed",
  "Pass*", "Conforms to reference" gibi her şey insana gider.
- Yönü belirsiz sınır, eksik test, iç laboratuvar testi, revizyon ya da
  tip/sınıf çelişkisi, onaysız tedarikçi, kanıtsız okuma ve okuma
  anlaşmazlığı insan incelemelidir.
- Parti: bir test uygun değilse red; değilse bir test insan incelemeliyse
  bekletme; yalnız boş olmayan ve tamamı uygun liste kabul. Makine durumu
  yalnız daha kısıtlayıcı yöne değiştirir. Karantinadan serbest bırakma
  gerekçeli insan düzeltmesidir; proje sahibi 28 Kasım 2026'da bunun yalnız
  M&P rolüne bırakılmasına karar verdi (uygulanma durumu teslimden önce
  denetlenecek).

**İki kaynak çakışınca daha sıkı şart**: aynı özellik için iki kaynak
(ör. askeri standart ve müşteri şartnamesi) farklı sınır verirse daha sıkı
olan alınır; seçim birim dönüşümünden sonra kuralla yapılır
(`docs/gercek_ornekler.md`).

## 5.6 İstem enjeksiyonuna karşı tasarım

Tedarikçi belgesi güvenilmeyen girdidir: partisini kabul ettirmek isteyen bir
taraf, belgeye modele yönelik talimat gizleyebilir (Greshake ve ark., 2023).
Sistemin savunması tek bir filtreye değil yapıya dayanır:

1. Model karar vermez; "bütün testleri uygun işaretle" talimatına uysa bile
   döndürebileceği bir karar alanı yoktur.
2. Modelin okuduğu her değer belgenin metin katmanında kanıtlanmalı ve kural
   okumasıyla uyuşmalıdır; uydurulan değer karara girmez.
3. Belge sınırlayıcısı kapatılamaz.

Bu tasarım 10 sertifikalık enjeksiyon setiyle (bkz. 4.2) ölçülür; doğru karar
enjeksiyonsuz ikizin kararıdır.

## 5.7 Güven skoru ve seçici karar (planlanan)

<!-- Bu alt bölüm güven skoru işi bittikten sonra kodla karşılaştırılıp
güncellenmeli. -->

Hibrit hat bugün her kararla birlikte kanıtsız okumaları, kural okumasına
düşülüp düşülmediğini (yedek) ve kural ile model arasındaki anlaşmazlıkları
(`hat.anlasmazliklar`, `hat.anlasmazlik_sayisi`) kaydeder. Planlanan güven
skoru; anlaşmazlık, kanıt kontrolü, sınır yönü kontrolü ve şema hatalarını
girdi alan bir **lojistik regresyon** modelidir ve kararın yanlış olma
olasılığını tahmin eder. Yön çelişkisi ve şema hatası bugün standart
tarafındaki deney raporlarında tutuluyor; sertifika kaydına girdi olarak
eklenmesi güven skoru işinin parçasıdır. Model Colab üç mod sonuçlarıyla yalnız **geliştirme kümesinde**
eğitilir.

Skor kararı değiştirmez; yalnız hangi kararların otomatik geçeceğini,
hangilerinin insana gideceğini belirler. Değerlendirme **risk–kapsam eğrisi**
ile yapılır (Geifman ve El-Yaniv, 2017): eşik değiştikçe otomatik verilen
kararların oranı (kapsam) ile bu kararlardaki hata oranı (risk) çizilir.
Proje için asıl risk yanlış kabuldür; eşik, kabul edilebilir yanlış kabul
oranında en yüksek kapsamı verecek biçimde seçilir.

## 5.8 Taranmış belgeler (planlanan)

<!-- OCR işi bittikten sonra güncellenmeli. -->

Taranmış standartlar için tamamen yerel çalışan bir OCR katmanı (Tesseract
ya da ocrmypdf) planlandı. Kapsam: MIL-S-81733C (bütünüyle taranmış,
geliştirme kümesi), MIL-PRF-23377G (taranmış, hazır OCR katmanlı; kendi
OCR'ımızla hazır katman karşılaştırılabilir) ve MIL-A-46146B (bütünüyle
taranmış; test kümesinde, kilit açılana kadar kullanılmaz). OCR'dan
gelen metin aynı çıkarım hattına girer; sonuçlar metin tabanlı belgelerden
ayrı raporlanır, çünkü OCR hataları çıkarım hatalarıyla karışır.

## 5.9 Değerlendirme ölçütleri

### Alan bazında precision, recall ve F1 (`deney/degerlendirme.py`)

Tahmin ve doğru cevap `KabulDokumani` olarak okunur ve (alan, kayıt)
anahtarlı düz bir sözlüğe çevrilir. Testler `id` ile, koşullar "kategori:ad"
ile, numune hazırlama `id` ile, raf ömrü kap türüyle eşleşir. Her alan için:

- **doğru pozitif**: iki tarafta da var ve değerler eşit;
- **yanlış pozitif**: tahminde var, doğru cevapta yok ya da değer farklı;
- **yanlış negatif**: doğru cevapta var, tahminde yok ya da değer farklı.

Yanlış değer hem yanlış pozitif hem yanlış negatif sayılır; boş alanlar
hesaba girmez. Metinler büyük/küçük harf ve boşluk farkı gözetilmeden, sayılar
çok küçük bir toleransla (göreli 10⁻⁹) karşılaştırılır. Birimler pint ile
çözülüp karşılaştırılır ("s" ile "second" eşit), değerler çevrilmez.
Serbest metin alanları (özgün metin, test koşulu) ölçülmez.

İki tahmin kayıtlara farklı kimlik verebildiği için üç mod karşılaştırmasında
(`deney/uc_mod.py`) kayıtlar önce anahtarla, kalanlar aynı maddede ad
benzerliğiyle hizalanır (`taslak_karsilastirma.kaydi_eslestir`).

F1 iki biçimde raporlanır: **genel** (bütün alanların mikro ortalaması) ve
**bölüm bazında** (her şart maddesinin P/R/F1'inin aritmetik ortalaması).
İkincisi, satır satır tutulan büyük bir tablonun (ör. 81733D soyulma
mukavemeti, 126 kayıt) ölçümü domine etmesini önler.

### Yanlış kabul oranı ve karar ölçütleri (`deney/karar_olcumu.py`)

- **Yanlış kabul oranı (FAR)**: doğru kararı kabul olmayan belgelerden
  sistemin kabul ettiklerinin oranı. Projenin ana güvenlik ölçütüdür.
- **Yakalama oranı**: doğru kararı red olan belgelerden sistemin
  reddettiklerinin oranı.
- **Doğruluk** ve **otomasyon oranı** (insana bırakılmayan belgelerin oranı).

Ölçütler hem parti (belge) hem parametre (test satırı) düzeyinde hesaplanır;
birincil ölçüt parti düzeyidir. Oranlar %95 **Wilson skor aralığıyla**
verilir (Wilson, 1927). Wilson aralığı oran 0 iken de anlamlı bir üst sınır
verir; sıfır yanlış kabul "risk yok" anlamına gelmez, ancak riskin hangi
düzeyin altında olduğunu söyler. Payda kabul olmayan belgelerdir: sentetik
sette 150 sertifikanın 48'i (22 red, 26 inceleme); 0/48 için üst sınır
yaklaşık %7,4'tür. Bu, küçük bir sentetik setin yanlış kabul hakkında
söyleyebileceğinin sınırını gösterir.

Muayene türündeki şartlar (etiketleme, ambalaj) CoC'de aranmadığı için FAR'a
girmez.

### Belge başına süre

Her çıkarımda sayfa başına ve belge başına duvar saati süresi kaydedilir
(`*_rapor.json`, `*_uc_mod_rapor.json`). Colab'da (T4 GPU) ve dizüstünde
(GPU'suz sayılabilir, 7,7 GB RAM) ayrı ölçülür; çünkü doğruluk donanımdan
bağımsız, süre değildir.

### Uydurma değer

Dil modelinin yazdığı her sayısal değerin kaynak sayfasında geçip geçmediği
kanıt kontrolüyle (`deney/kanit_kontrolu.py`) sayılır. Sayfada geçmeyen,
`X ± Y` toleransından da türetilemeyen değer uydurma adayıdır.

## 5.10 Deney düzeni ilkeleri

- İstem, kural ve çıkarıcılar yalnız geliştirme kümesine bakılarak
  geliştirilir; test kümesi dil modeli çıkarıcısı dondurulunca bir kez
  açılır (bkz. 4.5).
- Onaylanmamış doğru cevap taslağına göre istem ya da çıkarıcı ayarlanmaz.
- Her ölçüm betiği komut satırından tekrar çalıştırılabilir; model, istem
  sürümü ve parmak izi çıktıya yazılır.
- Her yeni fonksiyon pytest testiyle gelir; testler sahte yerel modelle
  çalışır, gerçek modelle testler ayrıca işaretlenir.

## Kaynaklar

- Geifman, Y. ve El-Yaniv, R. (2017). Selective Classification for Deep
  Neural Networks. *NeurIPS 2017*. https://arxiv.org/abs/1705.08500
- Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T. ve Fritz, M.
  (2023). Not What You've Signed Up For: Compromising Real-World
  LLM-Integrated Applications with Indirect Prompt Injection. *AISec '23
  (ACM CCS çalıştayı)*. https://arxiv.org/abs/2302.12173
- Willard, B. T. ve Louf, R. (2023). Efficient Guided Generation for Large
  Language Models. https://arxiv.org/abs/2307.09702
- Wilson, E. B. (1927). Probable Inference, the Law of Succession, and
  Statistical Inference. *Journal of the American Statistical Association*,
  22(158), 209–212. https://doi.org/10.1080/01621459.1927.10502953
- pint (Python birim kütüphanesi): https://pint.readthedocs.io/
