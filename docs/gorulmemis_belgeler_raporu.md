# Kural tabanlı çıkarıcı: görülmemiş belgeler denemesi

Tarih: 21 Kasım 2026. Çıkarıcı **kod değiştirilmeden** (main, `48fed0c`; yeni `raf_omurleri` şemasıyla) iki
yeni standartta çalıştırıldı. Ölçüm (F1) yapılmadı; doğru cevap taslakları
henüz onaylanmadı ve çıkarıcı bu belgelere göre düzeltilmeyecek.

```bash
python scripts/kabul_dokumani_uret.py data/raw/MIL-PRF-81733D.pdf --cikti data/cikti
python scripts/kabul_dokumani_uret.py data/raw/MIL-PRF-85285E.pdf --cikti data/cikti
```

## Sonuç

| Belge | Çıkarılan test | Raf ömrü | Koşul | Numune | Taslaktaki test (kabul) |
| --- | --- | --- | --- | --- | --- |
| MIL-PRF-81733D (sızdırmazlık macunu, 34 s.) | 0 | yok | 0 | 0 | 55 (27) |
| MIL-PRF-85285E (poliüretan son kat, 24 s.) | 0 | 1 yıl (kap türü boş, plastik kap ve sıcaklık yok) | 0 | 0 | 60 (41) |

Çıkarıcı yalnız başlık, tarih ve 85285E'de ilk raf ömrü süresini (metal kabın 1 yılı, kap türü boş) buldu. Taslak
kabul dokümanları `data/cikti/` altında (JSON, Markdown, Word) ama içleri
boş. Kural tabanlı çıkarıcı 23377K'nın düzenine sıkı bağlı; düzen biraz
değişince bütün test tablosunu kaybediyor. Hibrit yaklaşımın en çok fark
yaratacağı yer burası.

## Nerede zorlandı

Satır numaraları `src/malzeme_kabul/kural_cikarici.py` içindir.

### 1. Test tablosu bulunamıyor ya da okunamıyor (iki belgede de 0 testin nedeni)

- **81733D:** TABLE V'in başlık hücreleri "Test\nMethod" gibi satır sonu
  içeriyor; `"test method" in baslik` (s. 230) tutmuyor, tablo hiç
  bulunmuyor. Bulunsa da pdfplumber tablonun bütün satırlarını **tek hücrede
  alt alta** veriyor (s. 11) ve tablonun ilk beş satırı (s. 10) tablo değil
  düz metin olarak geliyor. Sütun sırası da farklı: ad, metot, şart maddesi,
  test maddesi. Boş hücreler "—" yerine "¾" glifiyle geliyor; `_bos` bunu
  tanımıyor.
- **85285E:** TABLE IV bulunuyor (33 satır) ama sütun sırası şart maddesi,
  ad, test maddesi, EPA metodu, ASTM metodu. Çıkarıcı ilk sütunu ad sayıyor
  (s. 306); "Toxicity" madde numarası olmadığı için her satır atlanıyor.
  Metot iki sütuna bölünmüş (EPA 311, ASTM D...).

### 2. Kabul / yeterlilik ayrımı

- 81733D kabul testlerini **ayrı bir tabloda** (TABLE VI) sayıyor; 85285E
  4.4.1'de "except toxicity (3.3), ..." diyor. Çıkarıcı yalnız "with the
  exception of" kalıbını (s. 218) ve başlığı tam "Conformance inspection"
  olan paragrafı (s. 281) arıyor. 85285E'de o paragraf (4.4) boş, metin
  4.4.1 "Tests" altında. İki belgede de bütün testler kabul sayılırdı:
  yanlış kabul oranı açısından en tehlikeli hata bu.

### 3. Sınırlar tablolarda ve tip/sınıf/renge göre değişiyor

- 81733D'de uçucu olmayan madde, ilk viskozite, uygulama süresi, yapışmazlık
  süresi değerleri TABLE I–IV'te; şart metni yalnız "as specified in table
  I" diyor. Yapışmazlık tablosu (TABLE IV) tip × sınıf × tire numarası
  ızgarası; pdfplumber satırları birleştirdiği için hücre konumları ancak
  kelime koordinatlarından geri kurulabildi.
- Bir cümlede birden çok sınır: "not less than 35 for Types I, II, and III
  or 30 for Type IV", "420 g/l for types I and IV, 340 g/l for type II, and
  50 g/l for type III". Çıkarıcı ilk sayıyı alıp gerisini kaçırır.
- 85285E'de sınırlar renk türüne göre (parlak / yarı parlak / kamuflaj) ve
  renk numarasına göre (34095, 13538) değişiyor. Şemada bunun için yalnız
  serbest metin `uygulanabilirlik` alanı var.

### 4. Kalıp ve birim eksikleri

- Kalıplar: "no more than" (`_UST`, s. 159, "not more than"ı biliyor),
  "less than 1" (dahil olmayan üst sınır), "a value of less than 1.0",
  "within -5 to +15 points", "minimum of 80 G.U.", "change ... of less than
  20".
- Birimler (`_BIRIMLER`, s. 110): inch, poise, psi, piw (pounds per inch
  width), grams per minute, G.U. yok. 85285E sıcaklığı "°C" yerine "oC"
  yazıyor (s. 125 ve 349'daki `°\s?C` tutmuyor), bu yüzden depolama
  sıcaklığı alınamadı.

### 5. Raf ömrü, önlemler, numune

- Raf ömrü: 81733D'de paragraf adı "Long-term storage" (s. 343 yalnız
  "Storage stability" / "Shelf life" arıyor). 85285E'de "one year for metal
  containers and six months for plastic containers": ilk süre alınıyor,
  plastik kap kaçıyor ve kayıtta kap türü boş kalıyor (taslak iki kayıt bekliyor).
- Önlem listesi: 85285E'de başlık "Precautions" (s. 363 "Precaution sheet"
  arıyor), kap ömrü "within four hours". 81733D'de önlem listesi yok.
- Panel tablosu: iki belgede de "Panel | Substrate | Pretreatment" başlıklı
  tablo yok (s. 239). 81733D'de adherend tablosu (TABLE X) başka başlıkla,
  85285E'de panel tarifi yalnız düz metinde (4.5, 4.6.7).

### 6. Küçük metin sorunları

- 81733D "3.2.4. Skin contact ..." madde numarasından sonra nokta; `_PARAGRAF`
  (s. 58) bu maddeyi önceki maddeye ekliyor.
- 81733D tarih "15 May1998" (boşluk eksik) olduğu gibi alınıyor.
- 81733D'nin 34. sayfası taranmış görüntü (son sayfa, içerik yok); OCR
  gerekmedi.

## Doğru cevap taslakları

`data/gold_taslak/` altında her belge için üç dosya: `<belge>.json` (taslak
doğru cevap, yeni `raf_omurleri` şemasıyla), `<belge>_kontrol_listesi.md`
(`scripts/kontrol_listesi_uret.py` ile, 23377K listesiyle aynı biçim) ve
`<belge>_NOTLAR.md` (kontrol etmen gereken kararlar). Taslaklar standart
metninden elle yazıldı; madde/sayfa çiftleri PDF'in paragraf sayfalarıyla
karşılaştırıldı (farklar yalnız değerin tabloda, sonraki sayfada durduğu
satırlar).
