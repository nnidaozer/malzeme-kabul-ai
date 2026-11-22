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

- `src/malzeme_kabul/yerel_model.py`: yerel model istemcisi. Yalnız
  `localhost` / `127.0.0.1` / `::1` adreslerini kabul eder, vekil sunucu
  ayarlarını yok sayar. Ollama (`/api/chat`, şema `format` alanında) ve
  llama.cpp (`/v1/chat/completions`, şema `response_format.json_schema`
  içinde) desteklenir. İki sunucu da şemayı dilbilgisine çevirip üretimi ona
  zorlar.
- Şema: modelin çıktısı `CikarimYaniti` (`{"testler": [TestSarti, ...]}`)
  JSON şemasına zorlanır. `TestSarti` mevcut `sema.py` modelidir. Şemadan
  geçen çıktı ayrıca Pydantic ile doğrulanır (pint birimi, madde biçimi gibi
  kurallar yalnız doğrulayıcılarda vardır); geçmeyen şart atılır ve rapora
  yazılır, diğerleri korunur.
- `scripts/dil_modeli_cikar.py`: PDF'i sayfa sayfa modele okutur, kabul
  dokümanı JSON'u ve sayfa başına süre/hata raporu yazar
  (`data/cikti/dil_modeli/`).
- `notebooks/colab_dil_modeli.ipynb`: Colab defteri. Ollama kurar, adayı
  indirir, tek sayfayla dener, bütün belgeyi çıkarır, adayları sırayla
  karşılaştırır. İsteğe bağlı bölümde aynı işi llama.cpp ile yapar.

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
python scripts/dil_modeli_cikar.py data/raw/MIL-PRF-23377K.pdf --model qwen2.5:3b-instruct-q4_K_M
```

Bağlamı 8192'de bırak. Bir sayfanın istemi (şema dahil) yaklaşık 2.500 token,
yanıt sınırı 4096 token; 4096'lık bağlamda Ollama sığmayan istemi baştan
kırpar ve sistem mesajı kaybolabilir. 3B modelde 8K bağlamın ek belleği birkaç
yüz MB'tır, 7,7 GB RAM'e sığar. Yanıt yarım kalırsa rapor bunu "JSON
çözülemedi" olarak gösterir.

## Bilinen sınırlar

- Bu ortamda gerçek model çalıştırılamadı (model indirme erişimi yok). İstemci,
  şema ve akış sahte yerel sunucuyla test edildi; gerçek model çıktısı ilk
  kez Colab'da görülecek.
- Birimin pint adını ("seconds" → "s") model yazıyor. Bu değer dönüşümü değil,
  ama model birimi kendiliğinden çevirebilir (ör. °F → °C). Ölçümde birim
  alanındaki hatalar ayrıca izlenmeli; gerekirse model ham birimi aktarır,
  pint eşlemesini kod yapar.
- Aynı `id` iki sayfada çıkarsa ilki tutulur, diğeri rapora `tekrar_edenler`
  olarak yazılır.
- Ön değerlendirme `data/gold_taslak/` ile yapılır; bu taslak onaylanana kadar
  istem ya da çıkarıcı bu sonuçlara göre ayarlanmamalıdır.
