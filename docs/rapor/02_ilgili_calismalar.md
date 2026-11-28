# 2. İlgili çalışmalar

> Durum: taslak (28 Kasım 2026). Ürünlerle ilgili bilgiler üreticilerin kendi
> sayfalarından ve basın bültenlerinden alındı; bağımsız olarak doğrulanmadı
> ve bu ürünlerin hiçbiri denenmedi. Bir özellik "belirtilmemiş" diye
> yazıldıysa incelenen sayfada geçmiyor demektir, üründe olmadığı anlamına
> gelmez.

Bu çalışma üç alanın kesişiminde durur: tedarikçi sertifikalarının
şartnameye göre otomatik doğrulanması, teknik standartlardan bilgi çıkarımı
ve dil modellerinin güvenilir biçimde (kısıtlı, denetlenebilir, insana
bırakabilen) kullanılması. Bölüm önce piyasadaki ürünleri, sonra akademik
yaklaşımları özetler ve çalışmanın bunlar arasındaki yerini gösterir.

## 2.1 Piyasadaki ürünler

### 2.1.1 Sertifika doğrulama ürünleri

Son iki yılda, tedarikçi sertifikasını okuyup şartnameyle karşılaştıran ve
çoğu büyük dil modeline dayanan ürünler çıktı. Bunlar ağırlıkla gıda, ilaç ve
metal sektörlerine yöneliktir.

- **TraceGains, AI-Powered Certificate of Analysis** (gıda). Mart 2025'te
  duyuruldu. Gelen CoA'ları gerekli şartnamelere göre inceler ve ek insan
  denetimi gereken olası sorunları işaretler. Bültene göre OpenAI temel
  modeli üzerine kuruludur.
- **Tenthpin Intelligent Certificate Verification (TICV)** (ilaç ve yaşam
  bilimleri). SAP BTP üzerinde çalışan bir SAP ortak eklentisidir. Uygunluk,
  analiz ve sterilizasyon sertifikalarından dil modeliyle veri çıkarır ve
  şartnameyle karşılaştırır; önerilen eşleştirmeyi kullanıcı değiştirebilir.
- **Tata Consultancy Services, Automated Certificate of Analysis Extractor**
  (tüketim ürünleri). ABBYY Marketplace'te Temmuz 2025'te yayımlandı. CoA
  verisini çıkarıp kurum sistemlerindeki iç şartnamelerle doğrular; ABBYY
  Vantage ile üretken yapay zekâ sağlayıcısı olarak Azure OpenAI kullanır.
- **Ai4Pharma, CoASmart** (ilaç). CoA'ları önceden tanımlı ürün
  şartnamelerine göre doğrular; uyuşmazlıkları, eksik bilgiyi ve yanlış
  değerleri bulur. Ürün sayfasında erişilebilirlik "yakında" diye
  belirtiliyor.
- **Certivo, MTR analizi** (metal). Haziran 2025 tarihli tanıtıma göre OCR ve
  dil modeliyle malzeme test raporlarından kimyasal bileşim, mekanik değerler
  ve döküm numarasını çıkarır, ASTM / EN / ASME şartnameleri ve RoHS / REACH
  eşikleriyle karşılaştırıp farkları işaretler.
- **Apolo, MTR CrossCheck** (metal). Nisan 2026'da duyuruldu. PDF ya da
  taranmış malzeme test raporlarını okuyup alıcının şartnamesine göre
  "geçti, kaldı ya da işaretli" sonuç verir. Bültene göre şirket içinde
  (on-premises) ya da özel bulutta çalışabilir.

### 2.1.2 Standart yönetimi ve revizyon takibi

- **Accuris, Engineering Workbench**. Standart kütüphanesi, anlamsal arama,
  şart çıkarımı ve madde düzeyinde değişiklik uyarıları ("Change
  Intelligence": tam olarak neyin değiştiğini gösterir) sunar.
- **Accuris, Change Impact Analysis**. Ağustos 2026'da duyuruldu. Bir standart
  revize edildiğinde etkiyi, önem derecesini ve mühendislik gerekçesini şart
  düzeyindeki değişikliğe bağlı olarak kaydeder; değerlendirmeyi mühendis
  yapar. İncelenen sayfada sertifika verisi çıkarma ya da tedarikçi
  değerlerini sınırlarla karşılaştırma anlatılmıyor.

### 2.1.3 Ürünlerin karşılaştırması

| Ürün | Sektör | Sertifika → şartname | Standart revizyonu | Kararı kim verir | Çalışma ortamı |
|---|---|---|---|---|---|
| TraceGains CoA | gıda | var | belirtilmemiş | ürün işaretler, insan denetler | belirtilmemiş (OpenAI temelli) |
| Tenthpin TICV | ilaç | var | belirtilmemiş | ürün önerir, kullanıcı değiştirebilir | SAP BTP (bulut) |
| TCS CoA Extractor | tüketim | var | belirtilmemiş | belirtilmemiş | ABBYY Vantage + Azure OpenAI |
| Ai4Pharma CoASmart | ilaç | var | belirtilmemiş | belirtilmemiş | belirtilmemiş |
| Certivo MTR | metal | var | belirtilmemiş | belirtilmemiş | belirtilmemiş |
| Apolo MTR CrossCheck | metal | var | belirtilmemiş | ürün (geçti / kaldı / işaretli) | şirket içi ya da özel bulut |
| Accuris Workbench + CIA | genel mühendislik | belirtilmemiş | var | mühendis | belirtilmemiş |
| **Bu çalışma** | havacılık kimyasalları | var | var, parti etkisiyle | **kesin kurallar; belirsizse insan** | **internetsiz, yerel model** |

Gözlemler:

1. İncelenen sertifika ürünlerinden ikisi açıkça bulut ya da bulut dil
   modeli üzerinde çalışıyor (Tenthpin: SAP BTP; TCS: Azure OpenAI),
   TraceGains OpenAI temel modeline dayanıyor; Apolo şirket içi kurulum da
   sunuyor. Gizli savunma belgeleri için bulut, belgenin kurum dışına çıkması
   demektir; bu çalışmada sistem internetsiz çalışır.
2. İncelenen sayfalar, karşılaştırmanın ve birim dönüşümünün modelde mi
   kodda mı yapıldığını söylemiyor. Bu çalışmada model yalnız okur;
   dönüşüm ve karşılaştırma kesin kurallarla yapılır (bkz. 3.1).
3. İncelenen sayfalarda sertifika doğrulama ile standart revizyon takibini
   birlikte anlatan bir ürün görülmedi; revizyon takibi Accuris'te,
   sertifika doğrulama diğerlerinde anlatılıyor. Bu çalışmada yeni revizyon, katalogdaki etkilenen malzeme kodlarını ve
   depodaki partileri doğrudan "M&P incelemesi bekliyor" olarak işaretler.
4. İncelenen sayfaların hiçbiri yanlış kabul oranı gibi bir güvenlik ölçütü
   ya da bağımsız bir doğruluk ölçümü yayımlamıyor.

## 2.2 Akademik yaklaşımlar

### 2.2.1 Kural ve sözlük tabanlı bilgi çıkarımı

Bilimsel ve teknik metinden yapılandırılmış veri çıkarmanın klasik yolu kural,
sözlük ve dil bilgisi örüntüleridir. **ChemDataExtractor** (Swain ve Cole,
2016) kimya literatüründen özellik ve değerleri bu yolla çıkaran bir araç
takımıdır; belge biçimine özgü ayrıştırıcılar, kimyasal adlandırma tanıma ve
kural tabanlı ayrıştırma kullanır. Bu çalışmadaki kural çıkarıcı aynı
geleneğe dayanır: MIL-PRF belgelerinin ortak yapısını (numaralı paragraflar,
test tablosu, kabul muayenesi kapsamı) düzenli ifadelerle okur. Bu tür
çıkarıcıların bilinen zayıflığı belge düzeni
değişince kırılmalarıdır; bu çalışmadaki ön gözlemler de bunu gösteriyor
(bkz. 5.2).

### 2.2.2 Belge yapısını öğrenen modeller

Düzen bilgisini (metin, konum, görüntü) birlikte kullanan ön eğitimli
modeller, form ve belge anlama görevlerinde yaygınlaştı. **LayoutLMv3**
(Huang ve ark., 2022) metin ve görüntü maskelemeyi tek bir ön eğitimde
birleştirir. Tablolar için **PubTables-1M** veri kümesi ve onunla eğitilen
Table Transformer modeli (Smock ve ark., 2022) tablo bulma ve yapı tanımayı
ele alır. Bu modeller etiketli veriyle ince ayar ister; bu çalışmada etiketli
veri az olduğu ve sınırın yönü gibi anlam bilgisi gerektiği için talimatla
çalışan genel bir dil modeli seçildi. Tablo yapısı tanıma, standartlardaki
karmaşık tablolar (ör. 81733D'de tip × sınıf ızgaraları) için gelecek bir
iyileştirme adayıdır.

### 2.2.3 Dil modelleriyle yapılandırılmış çıkarım

Büyük dil modelleri, az ya da hiç örnekle metinden yapılandırılmış kayıt
çıkarmada etkili bulundu. Dagdelen ve ark. (2024), ince ayarlı bir dil
modeliyle malzeme bilimi metinlerinden varlıkları ve aralarındaki ilişkileri
JSON gibi yapılandırılmış biçimde çıkardı. Polak ve Morgan (2024), sohbet
tipi modellerle araştırma makalelerinden malzeme verisi çıkarırken bir dizi
takip sorusuyla modelin kendi cevabını sorgulamasını sağlayan istem
mühendisliğiyle (ChatExtract) uydurma değerleri azalttı.

Bu çalışmalar iki noktada bu projeye yol gösterir: dil modelinin esnekliği,
kuralların kaçırdığı düzenleri yakalar; ama modelin değer uydurma eğilimi
ayrı bir doğrulama adımı gerektirir. Bu çalışma doğrulamayı modelin kendisine
değil belgeye bağlar: her okunan değerin belgenin metin katmanında geçmesi
(kanıt) ve kural okumasıyla uyuşması gerekir. Ayrıca bu çalışmalar
değerlendirmede doğruluğu ölçer; bu projede asıl ölçüt yanlış kabuldür.

### 2.2.4 Kısıtlı çözümleme

Modelin çıktısının bir JSON şemasına uyması, çıktıyı ayrıştırıp sonra
düzeltmek yerine üretim sırasında da zorlanabilir. Willard ve Louf (2023),
düzenli ifade ve bağlamdan bağımsız dilbilgilerini sonlu durum makinelerine
çevirip her adımda yalnız geçerli belirteçlerin üretilmesine izin veren
verimli bir yöntem önerdi (Outlines kütüphanesi). Bu çalışmada kullanılan
yerel sunucular (Ollama, llama.cpp) da JSON şemasını dilbilgisine çevirip
üretimi buna zorlar. Kısıtlı çözümleme çıktının **biçimini** garanti eder,
**doğruluğunu** etmez: şemaya uyan ama yönü ters bir sınır (bkz. 5.4) geçerli
bir çıktıdır.

### 2.2.5 Kural tabanlı uyum denetimi ve dil modelleri

Mevzuata uyum denetimi, özellikle yapı sektöründe, uzun süredir kural
tabanlı yapılır. Son çalışmalar dil modellerini bu sürece katıyor; ör.
Madireddy ve ark. (2025) dil modelleriyle yapı yönetmeliği maddelerinden yapı
bilgi modeli üzerinde çalışan denetim betikleri üretti. Bu çalışmada da
benzer bir iş bölümü vardır, ama yönü farklıdır: dil modeli kural üretmez,
yalnız belgeden değer okur; kurallar elle yazılır ve testle sabitlenir.

### 2.2.6 Seçici tahmin ve insana bırakma

Bir sistemin emin olmadığı örneklerde karar vermeyip insana bırakması seçici
sınıflandırma olarak incelenir. Geifman ve El-Yaniv (2017), istenen hata
düzeyinde kapsamı en yükseğe çıkaran bir reddetme eşiği seçmeyi ve sonucu
risk–kapsam eğrisiyle göstermeyi önerdi. Bu çalışmanın "insan incelemeli"
kararı ve planlanan güven skoru (bkz. 5.7) bu çerçeveye oturur. Fark,
reddetmenin bir kısmının öğrenilmiş bir skordan değil, kesin kurallardan
gelmesidir (yönü belirsiz sınır, kanıtsız okuma, anlaşmazlık).

### 2.2.7 Dil modeli uygulamalarına yönelik saldırılar

Greshake ve ark. (2023), dil modeliyle bütünleşik uygulamaların işledikleri
belge ve web sayfalarına gizlenen talimatlarla yönlendirilebileceğini
(dolaylı istem enjeksiyonu) gösterdi. Tedarikçi sertifikası, partisini kabul
ettirmekte çıkarı olan bir tarafın hazırladığı belge olduğu için bu tehdit
burada doğrudandır. Bu çalışma savunmayı filtrelemeye değil yapıya dayandırır:
model karar vermez, okuduğu değer belgeyle kanıtlanmalıdır (bkz. 5.6).

### 2.2.8 Taranmış belgeler için OCR

Eski revizyonların bir kısmı yalnız taranmış görüntü olarak bulunur.
Tesseract (Smith, 2007) yerel çalışabilen açık kaynaklı bir OCR motorudur ve
ocrmypdf gibi araçlar onu PDF'e metin katmanı eklemek için kullanır. Bu
çalışmada OCR katmanı yerel çalışma şartı nedeniyle bu araçlarla
planlanmıştır (bkz. 5.8).

## 2.3 Bu çalışmanın yeri

İncelenen ürün sayfaları ve çalışmalarla karşılaştırıldığında bu çalışmanın
öne çıkan yanları şunlardır (ürünlerin incelenen sayfalarda anlatılmayan
özellikleri olabilir):

1. **Okuma ile kararın ayrılması.** Dil modeli yalnız okur; birim dönüşümü,
   sınır karşılaştırması ve kabul / red kesin kurallarla verilir. Kararın
   dayandığı madde her satırda gösterilir.
2. **Yanlış kabulü önceleyen değerlendirme.** Alan bazında F1'in yanında,
   parti ve parametre düzeyinde Wilson aralıklı yanlış kabul oranı ölçülür;
   yalnız kural, yalnız dil modeli ve hibrit yaklaşım aynı ölçütlerle
   karşılaştırılır.
3. **İnternetsiz çalışma.** Şirket içi kurulum sunan ürünler de var (Apolo);
   bu çalışmada ayrıca ağ tamamen kapalıyken çalışma hedeflenir, model yerel
   çalışır ve dizüstü bilgisayara sığacak boyutlar (1–3B) ayrıca ölçülür.
4. **Kabul dokümanı, çapraz kontrol ve revizyon takibinin tek akışta
   birleşmesi.** Revizyon farkı, etkilenen malzeme kodlarına ve partilere
   bağlanır; her adım değiştirilemez sürümler ve zincirli denetim kaydıyla
   izlenir.

## Kaynaklar

### Ürünler (erişim: 28 Kasım 2026)

- TraceGains (2025). TraceGains Launches First Purpose-Built, AI-Powered
  Certificate of Analysis Solution. Basın bülteni, Food Dive.
  https://www.fooddive.com/press-release/20250326-tracegains-launches-first-purpose-built-ai-powered-certificate-of-analysis/
- SAP. Tenthpin Intelligent Certificate Verification (TICV).
  https://www.sap.com/uk/products/erp/partners/tenthpin-management-consultants-ag-tenthpin-intelligent-certificate-verificaition-ticv.html
- ABBYY Marketplace. Automated Certificate of Analysis Extractor (Tata
  Consultancy Services).
  https://www.abbyy.com/marketplace/assets/var/tata-consultancy-services/solution/automated-certificate-of-analysis-extractor/
- CPHI Online. CoASmart – Automated CoA Verification (Ai4Pharma).
  https://www.cphi-online.com/product/coasmart-automated-coa-verification-2/
- Certivo (2025). Certivo Simplifies Mill Test Report Analysis with
  AI-Powered Compliance Tools.
  https://www.certivo.com/blog-details/certivo-simplifies-mill-test-report-analysis-with-ai-powered-compliance-tools
- Apolo (2026). Apolo Expands AI Launchpad with MTR CrossCheck. Basın
  bülteni (üçüncü taraf yeniden yayın; birincil kaynak teslimden önce
  aranmalı).
  https://lifestyle.capitalcityrock.com/story/161478/apolo-expands-ai-launchpad-with-mtr-crosscheck-ai-powered-mill-test-report-validation/
- Accuris. Engineering Workbench.
  https://accuristech.com/solutions/engineering-workbench/
- Accuris (2026). Accuris Launches Change Impact Analysis.
  https://accuristech.com/news/accuris-launches-change-impact-analysis-to-make-standards-decisions-traceable-and-audit-ready/

### Akademik

- Dagdelen, J. ve ark. (2024). Structured information extraction from
  scientific text with large language models. *Nature Communications*.
  https://doi.org/10.1038/s41467-024-45563-x
- Geifman, Y. ve El-Yaniv, R. (2017). Selective Classification for Deep
  Neural Networks. *NeurIPS 2017*. https://arxiv.org/abs/1705.08500
- Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T. ve Fritz, M.
  (2023). Not What You've Signed Up For: Compromising Real-World
  LLM-Integrated Applications with Indirect Prompt Injection. *AISec '23*.
  https://arxiv.org/abs/2302.12173
- Huang, Y. ve ark. (2022). LayoutLMv3:
  Pre-training for Document AI with Unified Text and Image Masking. *ACM
  Multimedia 2022*. https://arxiv.org/abs/2204.08387
- Madireddy, S. ve ark. (2025). Large Language Model-Driven Code Compliance
  Checking in Building Information Modeling. https://arxiv.org/abs/2506.20551
- Polak, M. P. ve Morgan, D. (2024). Extracting accurate materials data from
  research papers with conversational language models and prompt
  engineering. *Nature Communications*.
  https://doi.org/10.1038/s41467-024-45914-8
- Smith, R. (2007). An Overview of the Tesseract OCR Engine. *Ninth
  International Conference on Document Analysis and Recognition (ICDAR
  2007)*. Yazılım: https://github.com/tesseract-ocr/tesseract
- Smock, B. ve ark. (2022). PubTables-1M: Towards
  Comprehensive Table Extraction from Unstructured Documents. *CVPR 2022*.
  https://arxiv.org/abs/2110.00061
- Swain, M. C. ve Cole, J. M. (2016). ChemDataExtractor: A Toolkit for
  Automated Extraction of Chemical Information from the Scientific
  Literature. *Journal of Chemical Information and Modeling*.
  https://doi.org/10.1021/acs.jcim.6b00207
- Willard, B. T. ve Louf, R. (2023). Efficient Guided Generation for Large
  Language Models. https://arxiv.org/abs/2307.09702
