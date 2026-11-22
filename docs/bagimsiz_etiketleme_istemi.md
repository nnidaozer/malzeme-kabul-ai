# Bağımsız etiketleme istemi

Bu dosya, doğru cevap (gold) taslağını ikinci, bağımsız bir modele (ör. Codex)
hazırlatmak için kullanılır. İki taslak `scripts/taslak_karsilastir.py` ile
karşılaştırılır; proje sahibi yalnızca ayrışan satırlara ve uyuşan satırlardan
seçilen kontrol örneğine bakar.

**Bağımsızlık için:** Modele mümkünse depoyu değil yalnızca iki dosyayı ver:
bu istem ve standardın PDF'i (`data/raw/<BELGE>.pdf`). İstem şemayı kendi
içinde tanımlar. `src/malzeme_kabul/sema.py` dosyasını verme: içindeki
açıklama örneklerinin bir kısmı MIL-PRF-23377K taslağından geliyor (ör. raf
ömrü ve 3.4 adlandırması). Depoya erişimi varsa aşağıdaki "Okuma yasağı"
bölümü geçerlidir.

Aşağıdaki çizginin altı modele olduğu gibi verilecek metindir. `<BELGE>` yerine
belge numarasını ve revizyonu yaz (ör. `MIL-PRF-12345X`).

---

## Görev

`<BELGE>.pdf` standardını baştan sona oku ve içindeki şartları aşağıdaki
şemaya uyan **tek bir JSON belgesi** olarak çıkar. Bu çıktı, bir belge kontrol
sisteminin doğru cevap anahtarı olacak. Hız değil doğruluk önemli: her değeri
PDF'teki maddeye bakarak yaz, tahmin etme.

## Okuma yasağı

Yalnızca standardın PDF'ini ve bu istemi kullan. Depodaysan şunları
**açma, okuma, arama**: `src/` (aşağıdaki doğrulama komutunu çalıştırmak
serbest, kaynak kodu okumak değil), `data/gold/`, `data/gold_taslak/`,
`data/cikti/`, `data/sentetik/`, `tests/`, `notebooks/`, `docs/` (bu dosya
hariç), `scripts/`,
git geçmişi (`git log`, `git show`, eski commit'ler), açık ya da kapalı PR'lar.
Bunlarda başka bir modelin aynı belge için hazırladığı cevaplar var; onları
görmek bu işin amacını bozar.

## Çıktı

1. `<BELGE>_bagimsiz.json`: `KabulDokumani` şemasına uyan tek JSON nesnesi.
   UTF-8, girintili (2 boşluk). JSON dışında hiçbir şey yazma; şemada olmayan
   alan ekleme (şema fazladan alanı reddeder).
2. `<BELGE>_bagimsiz_NOTLAR.md`: Emin olmadığın her karar için bir madde:
   hangi kayıt, hangi madde, neden emin değilsin, hangi seçeneği neden seçtin.

Depoda çalışıyorsan dosyaları `data/bagimsiz_taslak/` altına yaz ve şu
komutla doğrula (hata verirse düzelt):

```bash
python -c "from pathlib import Path; from malzeme_kabul.sema import KabulDokumani; KabulDokumani.model_validate_json(Path('data/bagimsiz_taslak/<BELGE>_bagimsiz.json').read_text(encoding='utf-8')); print('geçerli')"
```

## Şema

Şema aşağıda tam olarak tanımlıdır; doğrulama komutu çıktının ona uyup
uymadığını denetler. `null` yazılabilen alanlar "isteğe bağlı" diye
işaretli.

### KabulDokumani (en üst nesne)

| Alan | Tür | Açıklama |
|---|---|---|
| `standart` | StandartBilgisi | Belgenin kendisi. |
| `durum` | `"taslak"` | Her zaman `"taslak"`. |
| `testler` | TestSarti listesi | Standarttaki bütün test şartları (kabul, ömür uzatma, yeterlilik). |
| `raf_omurleri` | RafOmru listesi | Raf ömrü kayıtları; kap türü başına bir kayıt. |
| `kosullar` | Kosul listesi | Depolama ve kullanım koşulları. |
| `numune_hazirlama` | NumuneHazirlama listesi | Test panelleri / kuponlar. |

### StandartBilgisi

| Alan | Tür | Açıklama |
|---|---|---|
| `belge_no` | metin | Revizyon harfi olmadan, ör. `"MIL-PRF-12345"`. |
| `revizyon` | metin | Yalnızca harf, ör. `"X"`. |
| `baslik` | metin, isteğe bağlı | Kapaktaki başlık, PDF'teki gibi. |
| `tarih` | metin, isteğe bağlı | Kapaktaki tarih, PDF'teki gibi (ör. `"1 January 2000"`). |

### Kaynak (her kayıtta zorunlu)

| Alan | Tür | Açıklama |
|---|---|---|
| `belge_no` | metin | `standart.belge_no` ile aynı. |
| `revizyon` | metin | `standart.revizyon` ile aynı. |
| `madde` | metin | Şartın **yazdığı** madde: `"3.5.1"`, ek maddesi `"A.3.1"` ya da tablo `"TABLE II"`. Başka biçim kabul edilmez. |
| `sayfa` | tam sayı, isteğe bağlı | PDF görüntüleyicideki sayfa numarası (1'den başlar), belgenin üstündeki baskı numarası değil. |
| `alinti` | metin, isteğe bağlı | `null` bırak. |

### Sinir (kabul kriteri)

| Alan | Tür | Açıklama |
|---|---|---|
| `kriter_turu` | `"sayisal"`, `"gecti_kaldi"`, `"metinsel"` | Aşağıdaki kurallara bak. |
| `alt` | sayı, isteğe bağlı | Alt sınır. |
| `ust` | sayı, isteğe bağlı | Üst sınır. |
| `alt_dahil` | mantıksal | Alt sınır dahil mi (`"not less than"`, `"minimum"` → `true`; `"greater than"`, `"more than"` → `false`). Varsayılan `true`. |
| `ust_dahil` | mantıksal | Üst sınır dahil mi (`"not more than"`, `"maximum"` → `true`; `"less than"` → `false`). Varsayılan `true`. |
| `birim` | metin, isteğe bağlı | pint'in tanıdığı birim. |
| `orijinal_metin` | metin, zorunlu | Kriterin standarttaki cümlesi, PDF'teki gibi (satır sonu tirelerini birleştir, başka değişiklik yapma). |

Kriter türü kuralları:

- **`sayisal`**: Sayıyla ölçülen kriter. `alt` ve `ust` alanlarından en az biri
  dolu olur. "En az" yalnız `alt`, "en çok" yalnız `ust`, tam değer iki sınırın
  eşit olmasıdır. `±` toleransında sınırları hesapla: `50 ± 5` → `alt: 45,
  ust: 55`. Aralıkta (`"between 4 and 38"`) iki sınır da dolu olur.
- **`gecti_kaldi`**: Sayısal değeri olmayan, sonucu geçti/kaldı olan test
  (ör. "bütün şartları sağlamalıdır", "başarısız olmamalıdır").
- **`metinsel`**: Sözel kriter (ör. "kabarma, çatlama olmayacak", "renk
  doğal olacak").
- `gecti_kaldi` ve `metinsel` kriterlerde `alt`, `ust` ve `birim` `null`
  olmalıdır.

Sayı ve birim kuralları:

- **Birim çevirme yapma.** Değeri standardın yazdığı birimle al. Standart iki birim
  veriyorsa (ör. `°C (°F)`) ilk yazılanı al, ikincisini yalnızca
  `orijinal_metin`'de bırak.
- Sözle yazılmış sayıları rakama çevir (`"one part per million"` → `1`).
- Yüzdeyi `%` birimiyle ve yüzde olarak yaz (`"0.5 percent"` → `0.5`, birim `"%"`).
- Birim pint biçiminde yazılır: `"°C"`, `"°F"`, `"%"`, `"ppm"`, `"g/L"`,
  `"mm"`, `"µm"`, `"mil"` (inçin binde biri), `"second"`, `"minute"`, `"hour"`,
  `"day"`, `"month"`, `"year"`.
- Birimi pint'in tanımadığı bir ölçek ya da derece ise (ör. bir test metodunun
  derece numarası) `birim: null` yaz; ölçeğin adı `orijinal_metin`'de kalır.

### TestSarti

| Alan | Tür | Açıklama |
|---|---|---|
| `id` | metin | Belge içinde benzersiz kimlik; aşağıdaki kurala göre. |
| `test_adi` | metin | Bu kaydın gerçekten kapsadığı testin İngilizce adı. |
| `kaynak_tablo_adi` | metin, isteğe bağlı | Şart bir test tablosunda (ör. TABLE I) `test_adi`'ndan farklı bir satır adıyla geçiyorsa o satır adı, tablodaki gibi. Ad aynıysa ya da şart tabloda yoksa `null`. |
| `test_metodu` | metin, isteğe bağlı | Uygulanan test metodu, ör. `"ASTM D 0000"`, `"FED-STD-141 Method 0000"`. Standart bir metot belirtmiyorsa `null`. |
| `metot_kaynagi` | Kaynak, isteğe bağlı | Testin nasıl yapılacağını anlatan madde (genellikle 4.x). |
| `sinir` | Sinir | Kabul kriteri. |
| `kaynak` | Kaynak | Şartın yazdığı madde (genellikle 3.x ya da bir tablo). |
| `test_turleri` | liste, en az bir öğe | `"kabul"`, `"omur_uzatma"`, `"yeterlilik"` öğelerinden. |
| `uygulanabilirlik` | metin listesi | Şart yalnızca bazı tip/sınıflar için geçerliyse, ör. `["Type I", "Class C"]`. Hepsi için geçerliyse `[]`. |
| `numune_hazirlama_id` | metin, isteğe bağlı | Test bir panel/kupon üzerinde yapılıyorsa `numune_hazirlama` kaydının `id`'si. |

Test kuralları:

- **Bir kayıt, bir kriter.** Bir madde ya da tablo satırı birden fazla ayrı
  kriter içeriyorsa (ör. iki farklı madde için iki ayrı sınır, ya da iki
  ayrı süre), her kriter ayrı bir test kaydıdır. `test_adi` o kaydın neyi
  ölçtüğünü söyler; tablodaki ortak satır adını değil. Ortak satır adı
  `kaynak_tablo_adi` alanına yazılır.
- **`id` kuralı:** `test_adi` küçük harfe çevrilir, harf ve rakam dışındaki
  her karakter dizisi tek `_` olur, baştaki ve sondaki `_` atılır (ör.
  `"Example Property (Type I)"` → `example_property_type_i`). Aynı ad iki kez
  çıkarsa ikinciye ayırt edici bir ek koy.
- **Test türleri:** Standardın muayene bölümüne (genellikle 4.x'teki
  yeterlilik ve kabul/conformance muayenesi tabloları ve maddeleri) göre
  belirle. Her partide yapılan test `kabul`; yalnız ürün yeterliliğinde
  yapılan `yeterlilik`; raf ömrü uzatmak için tekrarlanan `omur_uzatma`. Bir
  test birden fazla türde olabilir.
- Standardın kapsamındaki bütün test şartlarını çıkar; yalnız kabul
  testlerini değil.

### RafOmru

| Alan | Tür | Açıklama |
|---|---|---|
| `kap_turu` | metin, isteğe bağlı | Raf ömrü kap türüne göre değişiyorsa kabın türü, Türkçe ve küçük harfle (tek sözcük, kabın malzemesi). Bütün kaplar için tek süre varsa `null`. |
| `sure` | sayı (> 0) | Süre. |
| `birim` | metin | Zaman birimi: `"day"`, `"month"`, `"year"`, ... |
| `kosul` | Sinir, isteğe bağlı | Raf ömrünün geçerli olduğu koşul. |
| `baslangic` | metin, isteğe bağlı | Sürenin başladığı an, standart açıkça yazıyorsa (Türkçe, ör. `"üretim tarihinden itibaren"`). |
| `kaynak` | Kaynak | |

Her kap türü için **tek** kayıt olur; aynı `kap_turu` iki kez yazılmaz.

### Kosul

| Alan | Tür | Açıklama |
|---|---|---|
| `kategori` | `"depolama"` ya da `"kullanim"` | |
| `ad` | metin | Koşulun kısa Türkçe adı; standarttaki ifadenin karşılığı. |
| `sinir` | Sinir, isteğe bağlı | Sayısal ya da sözel sınır. |
| `aciklama` | metin, isteğe bağlı | Sınırla ifade edilemeyen koşul metni. |
| `kaynak` | Kaynak | |

`sinir` ile `aciklama` alanlarından en az biri dolu olur. Raf ömrünün kendisi
koşul olarak tekrar yazılmaz; `raf_omurleri` altında durur.

### NumuneHazirlama

| Alan | Tür | Açıklama |
|---|---|---|
| `id` | metin | Standart panellere ad veriyorsa o ad (ör. `"panel_X"`), yoksa kısa bir ad. |
| `kupon_malzemesi` | metin, isteğe bağlı | Alt malzeme, standarttaki gibi. |
| `kupon_boyutu` | metin, isteğe bağlı | Boyut, standarttaki gibi. |
| `yuzey_hazirligi` | metin, isteğe bağlı | |
| `uygulama_yontemi` | metin, isteğe bağlı | |
| `kuru_film_kalinligi` | Sinir, isteğe bağlı | |
| `kurlenme` | metin, isteğe bağlı | Süre ve koşul, standarttaki gibi. |
| `kaynak` | Kaynak | |

## Biçim örneği

Aşağıdaki örnek **uydurma** bir standarttandır; yalnızca JSON biçimini
gösterir. Değerlerini ve adlarını gerçek belgeye taşıma.

```json
{
  "standart": {
    "belge_no": "MIL-PRF-00000",
    "revizyon": "A",
    "baslik": "EXAMPLE COATING",
    "tarih": "1 January 2000"
  },
  "durum": "taslak",
  "testler": [
    {
      "id": "example_density",
      "test_adi": "Example density",
      "kaynak_tablo_adi": "Example density and gloss",
      "test_metodu": "ASTM D 0000",
      "metot_kaynagi": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "4.9.1", "sayfa": 12, "alinti": null},
      "sinir": {
        "kriter_turu": "sayisal",
        "alt": 1.1,
        "ust": 1.3,
        "alt_dahil": true,
        "ust_dahil": true,
        "birim": "g/mL",
        "orijinal_metin": "The density shall be between 1.1 and 1.3 g/mL."
      },
      "kaynak": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "3.9.1", "sayfa": 5, "alinti": null},
      "test_turleri": ["kabul", "yeterlilik"],
      "uygulanabilirlik": [],
      "numune_hazirlama_id": null
    },
    {
      "id": "example_appearance",
      "test_adi": "Example appearance",
      "kaynak_tablo_adi": null,
      "test_metodu": null,
      "metot_kaynagi": null,
      "sinir": {
        "kriter_turu": "metinsel",
        "alt": null,
        "ust": null,
        "alt_dahil": true,
        "ust_dahil": true,
        "birim": null,
        "orijinal_metin": "The film shall be free of example defects."
      },
      "kaynak": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "3.9.2", "sayfa": 5, "alinti": null},
      "test_turleri": ["yeterlilik"],
      "uygulanabilirlik": ["Type Z"],
      "numune_hazirlama_id": "panel_Q"
    }
  ],
  "raf_omurleri": [
    {
      "kap_turu": null,
      "sure": 9,
      "birim": "month",
      "kosul": {"kriter_turu": "sayisal", "alt": 0, "ust": 30, "alt_dahil": true, "ust_dahil": true, "birim": "°C", "orijinal_metin": "stored between 0 and 30 °C"},
      "baslangic": null,
      "kaynak": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "3.9.3", "sayfa": 6, "alinti": null}
    }
  ],
  "kosullar": [
    {
      "kategori": "kullanim",
      "ad": "Örnek bekleme süresi",
      "sinir": null,
      "aciklama": "Örnek bileşenler karıştırıldıktan sonra beklenir.",
      "kaynak": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "6.9", "sayfa": 20, "alinti": null}
    }
  ],
  "numune_hazirlama": [
    {
      "id": "panel_Q",
      "kupon_malzemesi": "example alloy",
      "kupon_boyutu": "1 by 2 inches",
      "yuzey_hazirligi": null,
      "uygulama_yontemi": "spray",
      "kuru_film_kalinligi": null,
      "kurlenme": "1 day at room temperature",
      "kaynak": {"belge_no": "MIL-PRF-00000", "revizyon": "A", "madde": "4.8.1", "sayfa": 11, "alinti": null}
    }
  ]
}
```

## Son kontrol

Teslim etmeden önce:

- JSON şemaya uyuyor (yukarıdaki doğrulama komutu `geçerli` yazıyor).
- Her kaydın `kaynak.madde` değeri PDF'teki gerçek madde numarası.
- `test` kimlikleri benzersiz; her `numune_hazirlama_id` var olan bir panele bağlı.
- Hiçbir değeri birim çevirerek yazmadın.
- Emin olmadığın her karar `_NOTLAR.md` dosyasında.
