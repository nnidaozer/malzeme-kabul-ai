# Colab dil modeli çıktılarının değerlendirmesi (PR #44)

> **Geçici sayılar.** 23377K ölçümü `data/gold_taslak/MIL-PRF-23377K.json` ile yapıldı. Bu taslak Nida'nın
> kontrolünden geçmedi; `data/gold/` boş. Buradaki P/R/F1 değerleri onaylı sonuç değildir, istem ya da
> çıkarıcı bu sayılara bakılarak ayarlanmamalıdır.

## 1. Ne çalıştı

PR #44 ile 6 dosya girdi; bu klasöre taşındılar. Hepsi **yalnız MIL-PRF-23377K** için.
Defterde `BELGELER = ["data/raw/MIL-PRF-23377K.pdf"]` olduğu için **81733D ve 85285E dil modeliyle hiç çalışmadı.**
Donanım: Colab Tesla T4 (15 GB), Ollama 0.40.18, bağlam 8192, 19 sayfa.

| Model | Belge süresi | Sayfa başına | Kabul edilen test | Şemadan reddedilen | Hatalı sayfa | Tekrar eden ad |
|---|---|---|---|---|---|---|
| qwen3:8b (düşünme kapalı) | 675,7 s (11,3 dk) | 35,6 s | 55 | 1 | 1 | 15 |
| llama3.1:8b-instruct-q4_K_M | 1487,7 s (24,8 dk) | 78,3 s | 65 | 37 (+1 sayfa JSON bozuk) | 10 | 19 |
| qwen2.5:7b-instruct-q4_K_M | 310,4 s (5,2 dk) | 16,3 s | 16 | 24 | 3 | 1 |
| Kural (karşılaştırma için) | ölçülmedi (model yok) | | 27 | 0 | 0 | 0 |

qwen2.5'in hızlı görünmesi yanıltıcı: 19 sayfanın 11'inde 0,5 saniyenin altında boş yanıt döndü (0 test).
llama3.1'in 15. sayfası 203 s sürdü ve JSON çözülemediği için sayfanın tamamı kayboldu.

## 2. Alan bazında P / R / F1, 23377K (geçici)

İki ölçüm var:

- **Resmi betik** (`deney/degerlendir.py`): testleri `id` ile eşler. Modelin seçtiği id ("drying time",
  "chromium_content") gold'daki id'den ("drying_time", "chromium_content_class_n_only") farklıysa doğru değer de
  kaçırılmış sayılır. Genel F1: qwen3 0,235, llama3.1 0,251, qwen2.5 0,124, kural 0,892.
- **Hizalı** (aşağıdaki tablo): önce `deney/taslak_karsilastirma.kaydi_eslestir` ile aynı maddedeki testler ad
  benzerliğiyle eşlendi, sonra aynı betik çalıştırıldı. Model kaydı bulduysa ama id'yi farklı yazdıysa ceza almaz.
  Dil modelini adil ölçen sayı budur.

Gold'da 31 test var. Hizalı eşleşen test: qwen3 29, llama3.1 26, qwen2.5 13, kural 27.

| Alan | qwen3:8b P / R / F1 | llama3.1:8b P / R / F1 | qwen2.5:7b P / R / F1 | Kural P / R / F1 |
|---|---|---|---|---|
| test.test_adi | 0,47 / 0,84 / 0,60 | 0,29 / 0,61 / 0,40 | 0,56 / 0,29 / 0,38 | 1,00 / 0,87 / 0,93 |
| test.kaynak.madde | 0,49 / 0,87 / 0,63 | 0,37 / 0,77 / 0,50 | 0,81 / 0,42 / 0,55 | 1,00 / 0,87 / 0,93 |
| test.test_turleri | 0,02 / 0,03 / 0,02 | 0,02 / 0,03 / 0,02 | 0 / 0 / 0 | 1,00 / 0,87 / 0,93 |
| test.sinir.kriter_turu | 0,24 / 0,42 / 0,30 | 0,28 / 0,58 / 0,38 | 0,31 / 0,16 / 0,21 | 0,85 / 0,74 / 0,79 |
| test.sinir.alt | 0,20 / 0,20 / 0,20 | 0,25 / 0,40 / 0,31 | 0 / 0 / 0 | 1,00 / 1,00 / 1,00 |
| test.sinir.ust | 0 / 0 / 0 | 0,50 / 0,08 / 0,14 | 0 / 0 / 0 | 1,00 / 0,75 / 0,86 |
| test.sinir.birim | 0,20 / 0,14 / 0,17 | 0,78 / 0,50 / 0,61 | 1,00 / 0,07 / 0,13 | 1,00 / 0,79 / 0,88 |
| test.test_metodu | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1,00 / 0,82 / 0,90 |
| test.metot_kaynagi.madde | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1,00 / 0,94 / 0,97 |
| test.numune_hazirlama_id | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1,00 / 0,75 / 0,86 |
| test.uygulanabilirlik | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1,00 / 1,00 / 1,00 |
| **Yalnız test alanları (mikro)** | **0,36 / 0,41 / 0,38** | 0,31 / 0,40 / 0,35 | 0,54 / 0,17 / 0,26 | 0,99 / 0,85 / 0,92 |
| **Genel (mikro, bütün alanlar)** | **0,36 / 0,31 / 0,33** | 0,31 / 0,31 / 0,31 | 0,54 / 0,13 / 0,21 | 0,96 / 0,83 / 0,89 |

Dil modeli deneyi yalnız testleri çıkarıyor; raf ömrü, koşullar ve numune hazırlama hiç üretilmediği için bu alanlarda
recall 0 ve genel F1 aşağı çekiliyor. Bütün alanların tam tablosu: `alan_bazinda.csv` (proje dosyaları).

Precision düşük, çünkü modeller gold'da olmayan çok sayıda kayıt üretiyor (qwen3 55, llama3.1 65 test; gold 31).
Bunların bir kısmı 4.x muayene maddelerinden ya da tablo satırlarından aynı testin tekrarı.

## 3. 81733D ve 85285E: kural ile dil modeli farkı

| Standart | Gold taslak | Kural çıktısı | Kural genel F1 | Dil modeli |
|---|---|---|---|---|
| MIL-PRF-81733D (34 sayfa) | 239 test, 1 raf ömrü, 20 numune | 0 test | 0,000 (0 dp, 3672 yn) | **çalıştırılmadı** |
| MIL-PRF-85285E (24 sayfa) | 91 test, 2 raf ömrü, 17 koşul, 6 numune | 0 test, 1 raf ömrü | 0,000 (0 dp, 5 yp, 1266 yn) | **çalıştırılmadı** |

Kural çıktısı bugünkü kodla yeniden üretildi; sonuç depodakiyle aynı. Kural çıkarıcısı 23377K'nın tablo düzenine
bağlı olduğu için bu iki belgede hiçbir test bulamıyor (ayrıntı: `docs/gorulmemis_belgeler_raporu.md`).
Bu yüzden "kuralın 0 aldığı yerde dil modeli ne kazandırıyor" sorusu **henüz cevaplanamıyor**.

Yapılacak: defterde `BELGELER`'e `data/raw/MIL-PRF-81733D.pdf` ve `data/raw/MIL-PRF-85285E.pdf` eklenip en az
qwen3:8b ile yeniden koşulmalı. qwen3'ün 23377K hızıyla tahmini süre 81733D için yaklaşık 20 dk, 85285E için
yaklaşık 14 dk (tahmin; sayfa yoğunluğuna göre değişir). Çıktılar gelince aynı hizalı ölçüm birkaç dakikada yapılır.

Not: `data/gold_taslak/` altındaki 81733D ve 85285E dosyaları 24 Kasım'daki yüklemeyle (69c8950) değişti. İlk
taslaklarda 55 ve 60 test vardı, şimdi 239 ve 91 test var; bu sayılar Codex'in sayılarıyla aynı. Yani bu iki dosya
artık büyük ihtimalle Codex etiketlemesi. Yukarıdaki kural ölçümü bu yeni dosyalarla yapıldı (eskileriyle de 0).

## 4. Şemaya uymayan ve kanıt kontrolünden geçemeyen değerler (23377K)

**Şema doğrulamasından reddedilen test** (Pydantic; çıktıya hiç girmedi):

| Model | Reddedilen | En sık neden |
|---|---|---|
| qwen3:8b | 1 | "Hegman scale" birimi pint'te yok |
| llama3.1:8b | 37 + 1 bozuk JSON sayfa | 33'ü "sayısal" dedi ama sınır yazmadı |
| qwen2.5:7b | 24 | 13'ü metinsel/geçti-kaldı kritere yön yazdı, 8'i sınırsız sayısal |

**Kanıt kontrolü** (`deney/kanit_kontrol.py`: çıktıya giren her sayısal değer kaynak sayfasında geçiyor mu):

| Model | Sayısal değer | Sayfada bulundu | Bulunamadı (uydurma) |
|---|---|---|---|
| qwen3:8b | 13 | 11 | **2** |
| llama3.1:8b | 10 | 10 | 0 |
| qwen2.5:7b | 1 | 0 | **1** |
| Kural | 29 | 29 | 0 |

Uydurma değerler:

- **qwen3, viscosity, s. 3, madde 3.5.1: alt 10, üst 30 s.** Sayfa 3'te yalnız "Viscosity by Ford Viscosity Cup"
  başlığı var. Model "within the range of 10 to 30 seconds" diye bir alıntıyı da kendisi yazmış. Gerçek şart
  madde 3.6.3'te (s. 7): en çok 40 s.
- **qwen2.5, lead_cadmium_content, s. 11: alt 0,001 ppm.** Belgede "≤ 1 ppm" var. Model hem değeri hem yönü
  değiştirmiş: üst sınır alt sınıra dönmüş. Kural motoru bunu "≥ 0,001 ppm" diye okursa 100 ppm kadmiyumu da
  kabul eder. Bu doğrudan bir **yanlış kabul** riski.

Kanıt kontrolü yalnız sayının sayfada geçip geçmediğine bakıyor. Sayı sayfada olduğu hâlde anlamı yanlış olan
değerler (aşağıda llama3.1 kuruma süresi örneği) bu kontrolden geçiyor.

## 5. Dil modelinin en çok hata yaptığı üç alan

Sayılar en iyi model qwen3:8b için, parantez içinde llama3.1:8b. "Yanlış değer": iki tarafta da var ama farklı.

### 5.1 `test.test_turleri`: 28 yanlış değer (llama3.1: 25), F1 0,02

Model neredeyse her teste yalnız `kabul` yazıyor. Gold'da 21 test `kabul + yeterlilik`, 7 test yalnız `yeterlilik`.
Model test türünü TABLE V/VI'dan (muayene tablosu) değil, test maddesinin kendisinden tahmin etmeye çalışıyor ve
o maddede bu bilgi yok. Örnekler: viscosity, adhesion, odor (model `kabul`, gold `kabul, yeterlilik`).
Bu alan sayfa sayfa okumayla çözülemez; kural tarafında tablodan doldurulması gerekir.

### 5.2 `test.sinir.kriter_turu`: 16 yanlış değer (llama3.1: 8), F1 0,30

qwen3 55 testin 40'ına `metinsel` dedi; gold'da 31 testin 16'sı `sayisal`. Model sayısal şartı metin olarak geçince
alt/üst/birim alanları da boş kalıyor, bu yüzden `sinir.alt` (F1 0,20) ve `sinir.ust` (F1 0) de çöküyor.
Örnekler (qwen3):

- pot_life, drying_time, fineness_of_grind, voc_solvent_content, lead_and_cadmium_content, adhesion:
  model `metinsel`, gold `sayisal`.
- storage_stability: model `sayisal`, gold `gecti_kaldi`.
- llama3.1, condition_in_container / water_resistance / fluid_resistance: model `gecti_kaldi`, gold `metinsel`.

### 5.3 Sayısal sınır değerleri (`sinir.alt`, `sinir.ust`, `sinir.birim`)

Model sayısal sınır yazdığında da sık yanılıyor:

- **llama3.1, drying_time, 3.7.2:** "tack free within 5 hours and dry hard within 8 hours" cümlesini tek bir
  5–8 saat aralığı yapmış. Gold: en çok 5 saat (tack free). Bu okuma 7 saatte yapışmazlaşan bir ürünü kabul
  eder, 2 saatte kuruyan iyi bir ürünü reddeder. İki sayı da sayfada geçtiği için kanıt kontrolünden geçti.
- **qwen3, viscosity:** yukarıdaki uydurma 10–30 s (gold ≤ 40 s).
- **qwen3, birim:** yazdığı 10 birimin 8'i gold'la uyuşmuyor, gold'daki 14 birimin 12'sini kaçırıyor (F1 0,17).

Ayrıca modeller şu alanları **hiç doldurmadı** (recall 0): `test_metodu`, `metot_kaynagi`, `numune_hazirlama_id`,
`uygulanabilirlik`, `kaynak_tablo_adi`. Bunlar şemada var ama sayfa sayfa okumada model bu bilgiyi kurmuyor.

## 6. Kısa yorum

- En iyi aday qwen3:8b: en az şema hatası, en yüksek F1, llama3.1'in yarı süresi. Ama 23377K'da kural
  çıkarıcısının yanında çok geride (genel F1 0,33'e karşı 0,89; geçici).
- Dil modelinin değeri kuralın hiç çalışmadığı 81733D ve 85285E'de görülecek; o koşu yapılmadan hibrit tasarım
  için karar vermek erken.
- Görülen iki uydurma ve bir yön tersine çevirme, CLAUDE.md'deki "sınırı dil modeli değil kural belirler"
  ilkesini destekliyor: modelin sayı ve yön yazdığı "yalnız dil modeli" yaklaşımında yanlış kabul riski somut.

## Nasıl üretildi

- `python deney/degerlendir.py <tahmin> data/gold_taslak/MIL-PRF-23377K.json` (resmi, id ile)
- Hizalı ölçüm: `kaydi_eslestir` + `_b_yi_a_adlariyla_yaz` + `degerlendir` (deney/taslak_karsilastirma.py,
  deney/degerlendirme.py), kod değiştirilmedi.
- `python deney/kanit_kontrol.py <tahmin> data/raw/MIL-PRF-23377K.pdf`
- Kural çıktısı: `python scripts/kabul_dokumani_uret.py data/raw/MIL-PRF-<std>.pdf` (geçici klasöre)
- Test kümesindeki hiçbir dosya açılmadı; `data/gold*` altına bir şey yazılmadı.
