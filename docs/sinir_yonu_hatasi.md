# Kör nokta 6: sınır yönü hatası

Dil modeli bir sınırın sayısını doğru okuyup **yönünü** yanlış yazabilir: "en çok"
bir şartı "en az" (ya da tersi) diye kaydeder. Sayı sayfada geçtiği için kanıt
kontrolü bunu yakalamaz; şema da yakalamaz, çünkü "yalnız alt sınır" geçerli bir
sınırdır. Kural motoru ters yönle karşılaştırınca **yanlış kabul** verir.
Bu, mimarideki dil modeli sınırının (docs/mimari.md madde 6) altıncı kör noktasıdır.

## Örnek: qwen2.5 ve kadmiyum (23377K, madde 3.4)

Colab koşusu, 25 Kasım 2026, `deney/sonuclar/colab/MIL-PRF-23377K_dil_modeli_qwen2.json`:

| | Standart (gold taslak) | qwen2.5:7b çıktısı |
|---|---|---|
| Metin | "Incidental cadmium and cadmium compounds shall be not greater than one part per million (ppm)." (TABLE II satırı: "≤ 1 ppm") | `orijinal_metin: "≤ 1 ppm"` |
| Sınır | üst = 1 ppm (en çok) | **alt = 0,001 ppm** (en az) |

Model hem yönü çevirmiş hem sayıyı uydurmuş (0,001 sayfada yok). Kural motoru bu
şartla 100 ppm kadmiyumlu bir partiyi "uygun" bulurdu.

## Aynı koşudaki diğer yön hataları

Yeni kural (aşağıda) üç modelin çıktısında 8 çelişki buldu; hepsi gerçek hata:

| Model | Test | Metin | Model yazdı |
|---|---|---|---|
| llama3.1:8b | VOC (primer-coatings) | "a maximum ... VOC content of 340 g/L" | alt = 340 |
| llama3.1:8b | incidental_cadmium | "not greater than one part per million" | alt = 1 |
| llama3.1:8b | lead | "not more than 0.05 percent by weight" | alt = 0,05 |
| llama3.1:8b | viscosity | "the maximum viscosity ... shall be 40 seconds" | alt = 40 |
| llama3.1:8b | pot_life | "the maximum viscosity ... shall be 70 seconds" | alt = 70 |
| llama3.1:8b | drying_time | "tack free within 5 hours and ... dry hard within 8 hours" | aralık 5–8 |
| qwen2.5:7b | lead_cadmium_content | "≤ 1 ppm" | alt = 0,001 |
| qwen3:8b | kurma_zamani | "tack free within 5 hours and ... dry hard within 8 hours" | aralık 5–8 |

llama3.1'in "en çok" şartların çoğunu alt sınır olarak yazması, ham F1'de
yalnız `sinir.alt`/`sinir.ust` hatası gibi görünüyordu; yön hatası olarak
ayrıca sayılmalı.

## Kural: `malzeme_kabul.kural.yon_dogrulama`

Yön, modelden bağımsız olarak standarttaki özgün metnin ipuçlarından kesin
kurallarla çıkarılır ve modelin yönüyle karşılaştırılır:

- **en çok:** "not greater/more than", "no more than", "maximum", "shall not
  exceed", "within", "up to", "or less", "≤", "<"; olumsuzluk aynı cümlede
  önce geliyorsa ("no component shall contain ... more than 0.05 percent").
- **en az:** "not less than", "at least", "minimum", "or more", "≥", ">".
- **aralık:** "15 to 30", "between 1.0 and 1.5", "0.6 – 0.9", "1.0 ± 0.2".
  Dalga boyu ve sıcaklık aralıkları (nm, °C, °F) test koşuludur, sayılmaz;
  madde numaraları ("4.6.13 through 4.6.13.5") sayı sayılmaz.
- İpucu yoksa ya da karışıksa (iki yön, ya da aralık ile tek yön birlikte)
  kural karar vermez: `metinde_ipucu_yok`, model yönü olduğu gibi kalır.

Çelişkide sınır `yon="belirsiz"` yapılır, sayılar korunur. Karar motoru yönü
belirsiz şartı karşılaştırmaz, **insan incelemesine** gönderir. Kural böylece en
kötü durumda yanlış alarm üretir; bir şartı kendi başına kabul ettirmez.

Bağlı olduğu yerler:

- `deney/yalniz_dil_modeli.belgeden_cikar`: her çıkarılan testte çalışır,
  çelişkileri `_rapor.json` içinde `yon_celiskileri` listesine yazar.
- `okuma_yonu_dogrula(HamOkuma)`: ürün içi dil modeli çıkarıcısı (hibrit hat)
  geldiğinde modelin `sinir_yonu`'nu okuduğu ham metinle karşılaştırmak için.

Yanlış alarm denetimi (25 Kasım 2026): `data/gold_taslak` (23377K, 81733D, 85285E) ve
`data/gold_codex` (81733D, 85285E) taslaklarının 476 testinde 0 çelişki (196 uyumlu,
151 ipucu yok, 129 sayısal değil). Taslaklar henüz onaylı değil; sayı geçicidir.
