# Dil modeli ortamı

Bu belge, sistemin içindeki yerel dil modelinin nerede ve nasıl çalıştırılacağını
ve hangi modellerin aday olduğunu anlatır. **Model henüz seçilmedi**; aşağıdakiler
ölçümle karşılaştırılacak adaylardır.

## İki ortam

| Ortam | Amaç | Donanım | Model boyutu |
|---|---|---|---|
| Google Colab | Geliştirme ve ölçüm (F1, yanlış kabul oranı, süre) | T4, 15 GB GPU belleği | 7–8B, 4 bit (Q4_K_M) |
| Dizüstü bilgisayar | Nihai, internetsiz çalışma | NVIDIA MX, ~2 GB GPU belleği, 7,7 GB RAM | 1–3B, 4 bit (Q4_K_M) |

**Colab yalnız geliştirme ve ölçüm içindir.** Nihai sistem internetsiz çalışır.
Colab'da internet yalnızca paket ve model dosyası indirmek için kullanılır; model
yine aynı makinedeki yerel sunucuda (Ollama ya da llama.cpp) çalışır ve kod yalnız
`localhost`'a bağlanır. Colab'a gerçek tedarikçi sertifikası ya da gizli belge
yüklenmez; yalnız kamuya açık standartlar ve üretilmiş sentetik sertifikalar.

7B model dizüstüne sığmaz: 4 bitlik 7B model yaklaşık 4,5–5 GB tutar; 2 GB GPU
belleğine sığmaz, 7,7 GB RAM'de de işletim sistemi ve PDF okuma ile birlikte
çok sıkışık kalır.

## Bileşenler

- `src/malzeme_kabul/cikarim/yerel_model.py`: yerel model istemcisi. Yalnız
  `localhost` / `127.0.0.1` / `::1` adreslerini kabul eder, vekil sunucu
  ayarlarını yok sayar. Ollama (`/api/chat`, şema `format` alanında) ve
  llama.cpp (`/v1/chat/completions`, şema `response_format.json_schema`
  içinde) desteklenir. İki sunucu da şemayı dilbilgisine çevirip üretimi ona
  zorlar.
- `deney/yalniz_dil_modeli.py` ("yalnız dil modeli" deneyi, ürünün parçası
  değil): modelin çıktısı `CikarimYaniti` (`{"testler": [TestSarti, ...]}`)
  JSON şemasına zorlanır. `TestSarti`, `sozlesme/sema.py` modelidir. Şemadan
  geçen çıktı ayrıca Pydantic ile doğrulanır (pint birimi, madde biçimi gibi
  kurallar yalnız doğrulayıcılarda vardır); geçmeyen şart atılır ve rapora
  yazılır, diğerleri korunur.
- `deney/dil_modeli_cikar.py`: PDF'i sayfa sayfa modele okutur, kabul
  dokümanı JSON'u ve sayfa başına süre/hata raporu yazar
  (`data/cikti/dil_modeli/`).
- `deney/hibrit_standart.py`: standart tarafı hibrit (deney). Kural
  öncelikli; model yalnız kuralın bulmadığı, özgün metni sayfasında geçen
  testleri tamamlar; eklenen testin sınırını kural hesaplar; kanıtsız test
  atılır; kural ile model aynı test için farklı sınır, birim ya da yön
  bulursa anlaşmazlık yazılır ve kural testinin yönü `belirsiz` yapılır
  (insan incelemeli). Ayrıntı: docs/mimari.md madde 6.
- `deney/uc_mod.py`: bir PDF'i üç modda (kural, yalnız dil modeli, hibrit)
  çıkarır; süreleri, anlaşmazlık sayısını, insan incelemeli sınır sayısını
  ve (gold verilirse) hizalı alan F1'lerini yazar. Dil modeli her sayfanın
  sonucunu `<ETIKET>_ara/` altına ara kayıt olarak yazar; çalışma koparsa
  aynı komut kaldığı yerden devam eder.
- `notebooks/colab_dil_modeli.ipynb`: Colab defteri. Ollama kurar,
  `qwen3:8b`'yi (düşünme kapalı) indirir, tek sayfayla dener, üç standartta
  (MIL-PRF-23377K, MIL-PRF-81733D, MIL-PRF-85285E) `deney/uc_mod.py`'yi
  çalıştırır ve belge × mod özet tablosunu gösterir. İsteğe bağlı bölümde
  aynı işi llama.cpp ile yapar.

Dil modeli yalnız okur (CLAUDE.md, kural 1): değeri ve birimi sayfada yazdığı
gibi aktarır. Birim dönüşümü ve sınır karşılaştırması Python'dadır.

Bu adımda model yalnız **test şartlarını** çıkarır. Raf ömrü, koşullar ve numune
hazırlama sonraki adımdır; şeması (ör. kap türüne göre birden çok raf ömrü)
kesinleşince aynı yöntemle eklenir.

## Colab adayları (7–8B, 4 bit)

| Aday | Ollama etiketi | Boyut (Q4_K_M) | Lisans | Gerekçe |
|---|---|---|---|---|
| Qwen2.5-7B-Instruct | `qwen2.5:7b-instruct-q4_K_M` | ~4,7 GB | Apache 2.0 | Yapılandırılmış çıktı (JSON) ve tablo okumada bu boyutun en güçlülerinden; sayı ve birim aktarmada tutarlı. |
| Llama-3.1-8B-Instruct | `llama3.1:8b-instruct-q4_K_M` | ~4,9 GB | Llama 3.1 Community | En yaygın taban çizgisi; literatürde karşılaştırma için sık kullanılır, sonuçlar başka çalışmalarla kıyaslanabilir. |
| Qwen3-8B | `qwen3:8b` | ~5,2 GB | Apache 2.0 | Daha yeni nesil; talimat izleme daha iyi. Düşünme kipi kapatılarak (`--dusunme-kapali`) kullanılır, yoksa çıktı uzar ve süre artar. |

## Colab için GitHub belirteci

Depo gizli olduğu için defter, depoyu Colab'ın Secrets bölümündeki bir
belirteçle klonlar. Belirteç yalnız bu depoyu, yalnız okuyabilen, süreli bir
"fine-grained" belirteç olmalıdır.

**Belirteci oluştur (GitHub):**

1. GitHub'da sağ üstte profil resmi → **Settings**.
2. Sol menünün en altında **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
3. **Token name:** `colab-malzeme-kabul`. **Expiration:** ör. 30 gün (süre
   dolunca yenisini oluşturursun).
4. **Resource owner:** kendi hesabın.
5. **Repository access:** **Only select repositories** → yalnız
   `malzeme-kabul-ai`.
6. **Permissions → Repository permissions → Contents: Read-only**. Başka
   izin verme (Metadata: Read-only kendiliğinden eklenir).
7. **Generate token** → çıkan değeri kopyala. GitHub onu bir daha göstermez.

**Colab'a ekle:**

1. Defteri aç, sol menüde anahtar simgesine (🔑 **Secrets**) tıkla.
2. **Add new secret** → **Name:** `GITHUB_TOKEN`, **Value:** kopyaladığın
   belirteç.
3. Aynı satırdaki **Notebook access** anahtarını aç.
4. 2a, 2b, 2c hücrelerini sırayla çalıştır. Colab erişim izni sorarsa
   **Grant access** de. 2c "✓ Kurulum doğrulandı" yazmalı.

Belirteci hiçbir hücreye yapıştırma, ekran görüntüsüne ya da depoya koyma.
Defter belirteci yazdırmaz; adrese ya da `.git/config` dosyasına yazmaz,
yalnız klonlama komutuna başlık olarak verir; hata çıktısında maskeler.
Belirteç sızdığını düşünürsen GitHub'da aynı sayfadan **Revoke** ile iptal et.

"No module named 'malzeme_kabul'" hatasının iki nedeni vardı: gizli depo
belirteçsiz klonlanamıyordu, klonlansa bile çalışan çekirdek `pip install -e .`
ile eklenen yolu yeniden başlatılmadan görmüyordu. 2b hücresi `src/`
klasörünü yola ekleyerek ikincisini çözer.

## Dizüstü adayları (1–3B, 4 bit)

Dizüstünde 2 GB GPU belleği var. 3B model (Q4_K_M ~1,9–2,0 GB) bağlam belleğiyle
birlikte GPU'ya tam sığmaz; Ollama katmanların bir kısmını GPU'ya, kalanını
işlemciye koyar. 1,5B model GPU'ya tam sığar.

| Aday | Ollama etiketi | Boyut (Q4_K_M) | Lisans | Gerekçe |
|---|---|---|---|---|
| Qwen2.5-3B-Instruct | `qwen2.5:3b-instruct-q4_K_M` | ~1,9 GB | Qwen Research (ticari olmayan) | 3B sınıfında JSON ve sayı okumada güçlü; Colab'daki Qwen2.5-7B ile aynı aile olduğu için boyutun etkisi doğrudan ölçülür. Bitirme projesi için lisans uygun, endüstride kullanım için ayrıca bakılmalı. |
| Llama-3.2-3B-Instruct | `llama3.2:3b-instruct-q4_K_M` | ~2,0 GB | Llama 3.2 Community | Talimat izlemesi iyi, uzun bağlam destekler; Llama-3.1-8B ile aynı aile, yine boyut karşılaştırması yapılabilir. |
| Qwen2.5-1.5B-Instruct | `qwen2.5:1.5b-instruct-q4_K_M` | ~1,0 GB | Apache 2.0 | GPU'ya tam sığan tek aday, en hızlısı. Doğruluğu düşük olabilir; hibrit yaklaşımda kuralların küçük modelin hatasını ne kadar telafi ettiğini göstermek için değerli. |

Kapsam dışı bırakılanlar: Phi-3.5-mini (3,8B) ve Gemma 3 4B 1–3B aralığının
dışında ve 2 GB'a daha da kötü sığar. Qwen3-1.7B, Qwen2.5-1.5B'nin yerine
denenebilecek bir yedektir (Apache 2.0, düşünme kipi kapatılmalı).

Adayların **doğruluğu** donanımdan bağımsızdır (aynı GGUF dosyası aynı çıktıyı
verir); bu yüzden F1 Colab'da ölçülebilir. **Süre** ise dizüstünde ayrıca
ölçülmelidir. Dizüstünde sayfa başına süre birkaç dakikayı bulabilir (tahmin,
ölçülmedi); bu durumda hibrit yaklaşımda yalnız ilgili sayfaları (3. ve 4.
bölüm, tablolar) modele göndermek belge başına süreyi düşürür
(`--sayfalar`).

## Dizüstünde kurulum (internetsiz çalışma)

1. İnternet varken bir kez: Ollama'yı kur ve adayı indir
   (`ollama pull qwen2.5:3b-instruct-q4_K_M`). Model dosyaları diskte kalır.
2. Sonrasında internet gerekmez: `ollama serve` yalnız `127.0.0.1:11434`
   adresini dinler (varsayılan). Otomatik güncellemeyi kapat.
3. Çalıştır:

```bash
python deney/dil_modeli_cikar.py data/raw/MIL-PRF-23377K.pdf --model qwen2.5:3b-instruct-q4_K_M
```

Bağlamı 8192'de bırak. Bir sayfanın istemi (şema dahil) yaklaşık 2.500 token,
yanıt sınırı 4096 token; 4096'lık bağlamda Ollama sığmayan istemi baştan
kırpar ve sistem mesajı kaybolabilir. 3B modelde 8K bağlamın ek belleği birkaç
yüz MB'tır, 7,7 GB RAM'e sığar. Yanıt yarım kalırsa rapor bunu "JSON
çözülemedi" olarak gösterir.

## Dizüstü ölçümü (tek komut)

`deney/dizustu_olcum.py`, qwen2.5 1.5B ve 3B modellerini geliştirme kümesindeki
gold'lu standartlarda (data/gold_taslak ya da data/gold_codex altında gold'u
olanlar; şu an MIL-PRF-23377K, MIL-PRF-81733D, MIL-PRF-85285E) üç modda (kural,
dil modeli, hibrit) çalıştırır. Belge ve sayfa başına süreyi ve F1'i ölçer,
ağın kapalı olduğunu da gösterir.

1. İnternet varken bir kez:

   ```bash
   ollama pull qwen2.5:1.5b-instruct-q4_K_M
   ollama pull qwen2.5:3b-instruct-q4_K_M
   pip install -r requirements-dev.lock && pip install -e . --no-deps
   ```

   Model adı yedekleri: istenen tam ad Ollama'da yoksa eş adlar sırayla
   aranır (`qwen2.5:1.5b`, `qwen2.5:1.5b-instruct` ve `qwen2.5:3b`,
   `qwen2.5:3b-instruct`). Yani `ollama pull qwen2.5:3b` ile indirilmiş model de
   kabul edilir. Hangi adın kullanıldığı raporda `model_eslesmeleri`ne yazılır;
   satırlarda ve klasör adlarında istenen ad kalır. Ne tam ad ne yedek varsa
   model atlanır ve `ollama pull` önerilir.

2. Wi-Fi'yi kapat ya da Ethernet'i çıkar (uçak modu). Ardından bir terminalde
   `ipconfig /flushdns` çalıştır: Windows'un DNS önbelleğinde kalan pypi.org ve
   github.com kayıtları ağ kapalıyken de çözülür ve betik ağı yanlışlıkla açık
   sayıp 3 koduyla durur. Ağ denetimi WPAD/PAC ile otomatik ayarlanan vekilleri
   görmez (yalnız ortam değişkenleri ve sistem vekil ayarı); bu bir sınırdır.
   Ağ kapalıyken her denetim zaman aşımlarıyla 10-20 saniye sürebilir; bu süre
   ölçülen sürelere girmez.
3. Ollama'nın çalıştığından emin ol: görev çubuğunda simgesi görünmeli ya da
   bir terminalde `ollama serve` çalışıyor olmalı.
4. Çalıştır:

   ```bash
   python deney/dizustu_olcum.py
   ```

   Windows'ta `python` komutu bulunamazsa ya da Microsoft Store'u açarsa
   `python` yerine `py` yaz: `py deney/dizustu_olcum.py`.

Çıktılar `deney/sonuclar/dizustu/` altına yazılır: `dizustu_olcum.md` (tablo),
`dizustu_olcum.csv` (model × belge × mod satırları) ve `dizustu_olcum.json`
(tam rapor: sistem bilgisi, Ollama sürümü, model eşleşmeleri, yükleme
süreleri, ağ denemeleri, satırlar, atlanan modeller, hatalar). Her modelin
uc_mod çıktıları ve sayfa başına ara kaydı model klasöründe tutulur (ör.
`qwen2.5_3b-instruct-q4_K_M/`; model adındaki `<>:"/\|?*` karakterleri `_`
olur).

Kopan çalışma ve `--sifirdan`: Çalışma koparsa aynı komutu yeniden çalıştır;
tamamlanan sayfalar ara kayıttan (`MODEL_KLASORU/ETIKET_ara/`) okunur, modele
yeniden gönderilmez. Bu sayfalar satırlarda `devam_edilen_sayfa` sütununa
yazılır ve raporda `devam_edildi: true` olur. Devam edilen çalışma ağ kanıtı
sayılmaz (`ag_kapali_calisti: false`): ara kayıttaki sayfalar ağın açık olduğu
bir sırada üretilmiş olabilir. Ağ kanıtı için ağ kapalıyken
`python deney/dizustu_olcum.py --sifirdan` ile baştan ölç; bu seçenek yalnız
ölçülen her model × belgenin `ETIKET_ara/` klasörünü siler, öteki dosyalara
dokunmaz.

Isınma ve `yukleme_s`: Her model, belgelerden önce (belge ve test kümesi
denetimlerinden sonra) kısa bir istekle bir kez ısıtılır; böylece modelin
belleğe yüklenme süresi ilk belgenin süresine karışmaz. Bu süre raporda
`yukleme_s`e yazılır. Isınma başarısız olursa (zaman aşımı, bağlantı, bozuk
yanıt) hata `hatalar`a belgesiz yazılır ve o modelin belgeleri ölçülmez; öteki
model ölçülmeye devam eder.

Başarısız sayfa (`basarisiz_sayfa`): Dil modeli isteği hata veren (HTTP 500,
zaman aşımı, bağlantı kopması) sayfaların sayısıdır; dil modeli ve hibrit
satırlarına yazılır, kural satırında 0'dır. Bu genellikle RAM yetmezliği ya da
zaman aşımı belirtisidir (Ollama bellek yetmeyince "model requires more system
memory" ile 500 döner). Başarısız sayfalı ölçüm `hatalar`a "istek başarısız"
ve sayfa sayısıyla yazılır, tamamlanmış sayılmaz ve md tablosunda "geçersiz"
işaretlenir. 3B modelde bu görülürse önce tarayıcı gibi diğer uygulamaları
kapatıp yeniden dene (başarısız sayfalar ara kayda girmez, yeniden istenir).
`--sifirdan` olmadan yeniden denersen başarılı sayfalar ara kayıttan okunur ve
`ag_kapali_calisti` false kalır; ağ kanıtı için `--sifirdan` ile baştan ölç.
Modelin bozuk JSON yanıtı da bu sayaca girer; yani sayı her zaman bellek
sorunu demek değildir, `dizustu_olcum.json` içindeki sayfa hatalarına bak.

Seçenekler:

- `--modeller M1 M2 ...`: Ollama etiketleri (varsayılan iki qwen2.5 modeli).
  Ne tam adı ne yedek adı Ollama'da olan model atlanır, raporda `ollama pull`
  önerisi yazılır.
- `--belgeler PDF1 PDF2 ...`: ölçülecek PDF'ler (varsayılan yukarıdaki
  gold'lu geliştirme belgeleri). Test kümesindeki ya da kilitli klasördeki
  belge hiçbir model çağrılmadan reddedilir.
- `--sifirdan`: ölçülen belgelerin ara kaydını silip baştan ölçer (yukarıda).
- `--ag-acik-izin`: ağ açıkken de ölçer; bu durumda rapor internetsiz
  çalışmayı kanıtlamaz (`ag_kapali_calisti: false`).
- `--baglam N`: bağlam penceresi (varsayılan 8192; yukarıdaki nedenle düşürme).
- `--adres`, `--cikti`, `--bolunme`: Ollama adresi (yalnız localhost), çıktı
  klasörü, bölünme dosyası.

Çıkış kodları: 0 en az bir dil modeli ölçümü başarısız sayfasız tamamlandı;
1 hiçbiri tamamlanmadı (modeller yok, hepsi hatalı ya da sayfa istekleri
başarısız); 2 test kümesindeki / kilitli / OCR gerektiren belge, data/gold
altına çıktı ya da geçersiz girdi; 3 ağ açık (izin yok); 4 Ollama'ya
ulaşılamadı.

Süre tahmini verilmez: ölçülmedi. GPU olmadan, yalnız işlemcide 3B model
belge başına uzun sürebilir (sayfa başına dakikalar). `sayfa_basi_s`, modun
süresinin belgenin bütün sayfa sayısına bölümüdür; payda metinsiz (modele
gönderilmeyen) sayfaları da içerdiği için modele giden sayfa başına gerçek
süre bundan uzun olabilir. Önce kısa bir deneme yap:

```bash
python deney/dizustu_olcum.py --modeller qwen2.5:1.5b-instruct-q4_K_M --belgeler data/raw/MIL-PRF-85285E.pdf
```

Ağ kanıtı: ölçümden önce, her model × belge ölçümünden sonra (`ag_ara`) ve en
sonda `scripts/ag_kapali_mi.py`'deki denemeler (DNS: pypi.org, github.com; TCP:
1.1.1.1:443, 8.8.8.8:53, 140.82.112.3:443; HTTPS: https://pypi.org/simple/)
yapılır ve rapora yazılır. HTTPS denemesinde sunucudan gelen HTTP hatası (ör.
403, 407) ya da TLS/SSL hatası da dışarıdaki bir uca ulaşıldığını gösterir ve
ağ açık sayılır. Vekil denetimi: sistemde vekil (proxy) ayarı varsa aynı HTTPS
isteği sistem vekili üzerinden de denenir ("HTTPS vekil üzerinden ...") ve
vekil ayarı raporda `vekil`e yazılır; böylece yalnız vekille dışarı çıkılabilen
ağ da yakalanır. Konteyner denetimi (`scripts/ag_testi.sh`) varsayılanı
kullanır ve vekil denemesi yapmaz. Rapor `ag_kapali_calisti: true` yazar ancak
bütün denetimlerde hiçbir deneme dışarı çıkamadıysa, ara kayıttan devam
edilmediyse ve en az bir dil modeli ölçümü başarısız sayfasız tamamlandıysa.
Ollama isteği yalnız localhost'a gider ve vekil ayarları yok sayılır.

## Bilinen sınırlar

- Bu ortamda gerçek model çalıştırılamadı (model indirme erişimi yok). İstemci,
  şema ve akış sahte yerel sunucuyla test edildi; gerçek model çıktısı ilk
  kez Colab'da görülecek.
- `deney/dizustu_olcum.py` de bu bulut ortamında gerçek modelle
  çalıştırılamadı (model indirme erişimi yok); sahte istemci, sahte ağ
  denetimi ve sahte Ollama durumuyla test edildi. Gerçek süre ve F1 ilk kez
  dizüstünde görülecek.
- Birimin pint adını ("seconds" → "s") model yazıyor. Bu değer dönüşümü değil,
  ama model birimi kendiliğinden çevirebilir (ör. °F → °C). Ölçümde birim
  alanındaki hatalar ayrıca izlenmeli; gerekirse model ham birimi aktarır,
  pint eşlemesini kod yapar.
- Aynı `id` iki sayfada çıkarsa ilki tutulur, diğeri rapora `tekrar_edenler`
  olarak yazılır.
- Ön değerlendirme `data/gold_taslak/` ile yapılır; bu taslak onaylanana kadar
  istem ya da çıkarıcı bu sonuçlara göre ayarlanmamalıdır.
