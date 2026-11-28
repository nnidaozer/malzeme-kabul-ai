# Güven skoru ve risk–kapsam eğrisi

Durum: 28 Kasım 2026. Kod ve testler hazır; model **henüz eğitilmedi**. Eğitim
Colab üç mod sonuçları `deney/sonuclar/colab_uc_mod/` altına gelince yalnız
geliştirme kümesinde yapılır.

## Amaç ve sınır

Güven skoru, hibrit çıkarıcının bir test şartını yanlış okumuş olma
olasılığını tahmin eder. **Skor kabul ya da red kararı vermez.** Tek etkisi bir
şeyi insan incelemesine göndermektir:

- `uygun` + düşük güven (eşiğin altında) → `insan_incelemeli`
- `uygun` + güven NaN (skor hesaplanamadı) → `insan_incelemeli` (temkinli yön)
- `uygun_degil` ve `insan_incelemeli` hiçbir skorla değişmez
- model dosyası yoksa (güven `None`) hiçbir karar değişmez
- `uygun` yalnız güven >= eşik **ve** eşik < 1.0 iken geçer; eşik 1.0 "otomatik
  geçiş yok" demektir (güven 1.0 olsa da `uygun` insan incelemesine gider)
- NaN olmayan ve [0, 1] dışındaki güven `yonlendir` ve `incelenecek_testler`
  tarafından karardan bağımsız olarak `ValueError` ile reddedilir (NaN güven
  eskisi gibi incelemeye gider)
- eşik NaN, sonsuz ya da [0, 1] dışındaysa `yonlendir` ve `incelenecek_testler`
  karardan önce `ValueError` verir

Böylece skor ancak yanlış alarm üretebilir; yanlış kabulü artıramaz.

## Girdiler (her hibrit test şartı için)

| Özellik | Kaynak | Anlamı |
|---|---|---|
| `anlasmazlik_sayisi` | `hibrit_raporu.anlasmazliklar` (`test_id`) | Kural ve model sınırı farklı okudu (kayıt sayısı) |
| `kanit_yok` | hibrit raporu | Kural testine kanıtlı model testi eşleşmedi (kural tek başına) |
| `yalniz_model` | `hibrit_raporu.eklenen` | Test yalnız modelden geldi (kanıt kontrolünden geçti) |
| `sayfa_kanitsiz_sayisi` | `hibrit_raporu.kanitsiz` + model testinin sayfası | Aynı sayfada kanıtsız atılan model testi sayısı |
| `yon_celiskisi` | `dil_modeli_raporu.yon_celiskileri`, `alan == "yon"` anlaşmazlığı | Model yönü metinden kuralla çıkan yönle çelişti |
| `sayfa_sema_hatasi` | `dil_modeli_raporu.sayfalar[].hatalar` | Testin sayfasında modelin şemaya uymayan yanıt sayısı |

Sayılar `log(1 + n)` ile, ikili özellikler 0/1 olarak girer.

## Etiket

Hibrit çıktı gold ile hizalanır (`taslak_karsilastirma.kaydi_eslestir`). Bir
test **hatalı** sayılır: gold'da karşılığı yoksa ya da sınır alanlarından biri
(`kriter_turu`, `alt`, `ust`, `alt_dahil`, `ust_dahil`, `birim`) gold'dan farklıysa.
Gold yalnız okunur; belge başına ilk bulunan kullanılır, sıra `data/gold` >
`data/gold_taslak` > `data/gold_codex`. Gold'u olmayan belge atlanır ve
listelenir. Hiçbir çıktı `data/gold/` altına yazılmaz.

Sınırının yönü `belirsiz` olan test kurallar gereği zaten insan incelemesine
gider (`zorunlu_inceleme`); eğriye girer ama hiçbir eşikte otomatik geçmez.

## Model

L2 düzenlemeli lojistik regresyon, saf Python (Newton yöntemi, belirlenimci).
Ağırlıklar JSON'da saklanır; özellik adları birebir eşleşmezse dosya reddedilir.

- Ürün: `src/malzeme_kabul/kural/guven_skoru.py` (girdiler, skor, yönlendirme;
  eğitim yok, dil modeli yok)
- Deney: `deney/guven_verisi.py` (üç mod çıktısından girdi ve etiket),
  `deney/guven_egitimi.py` (eğitim, revizyon ailesi bazında dışarıda bırakmalı tahmin,
  eşik seçimi), `deney/risk_kapsam.py` (eğri, AURC, CSV + SVG)

Eğri, eğitimde kullanılmayan revizyon ailesinin tahminleriyle çizilir (bir aile,
ör. 23377'nin G ve K revizyonları birlikte, dışarıda bırakılır; kalanlarla
eğitilir; `deney.bolunme.aile`). Tek aile varsa dışarıda bırakmalı tahmin hata
verir. Eşik, hedef riski (varsayılan %1; `hedef_risk` [0, 1] içinde sonlu
olmalı) aşmayan en yüksek kapsamı veren güven değeridir.

Güven hiçbir zaman 1.0'a ulaşmaz (en çok `nextafter(1.0, 0.0)`). Hedefi
sağlayan nokta yoksa eşik 1.0 seçilir; 1.0 eşiği "otomatik geçiş yok" demektir,
her `uygun` insan incelemesine gider.

## Komutlar (sonuçlar gelince)

```bash
python deney/guven_egitimi.py --girdi deney/sonuclar/colab_uc_mod --cikti deney/sonuclar/guven_skoru
python deney/risk_kapsam.py deney/sonuclar/guven_skoru/tahminler.csv --cikti deney/sonuclar/guven_skoru
```

İki betik de yalnız `data/bolunme.yaml`'daki geliştirme kümesini kullanır; test
kümesindeki bir belgeyi görürse 2 koduyla çıkar. Taranmış belgeler
(`ocr_gerekli`) OCR katmanı gelene kadar aynı şekilde reddedilir (`OcrGerekli`,
çıkış kodu 2). Geçersiz `--hedef-risk` de 2 koduyla reddedilir. Bu durumların
hiçbirinde dosya yazılmaz.

## Kapsam ve risk

Eşik `t` için skoru `t`'nin üstünde olan ve zorunlu incelemede olmayan testler
otomatik geçer.

- kapsam = otomatik geçen test / bütün test
- risk = otomatik geçenler içinde hatalı oranı
- AURC = risk–kapsam eğrisinin altında kalan alan (küçük daha iyi)

## Sınırlılıklar

- Eşik dışarıda bırakmalı skorlarla seçilir, ama kaydedilen model bütün veriyle
  eğitilir. Bu yüzden kaydedilen modelin gerçek riski, raporlanan (dışarıda
  bırakmalı) riskten biraz farklı olabilir.
