# Mimari

Durum: 24 Kasım 2026, Nida'nın onayladığı genişletilmiş mimari. Kodda bugün
neyin hazır, neyin iskelet olduğu her bölümün sonunda "Bugün" satırında yazar.

Temel kural değişmez: belgeyi yerel dil modeli okur, kabul/red kararını
yalnızca kesin kurallar verir. Sistem internetsiz çalışır; `src/` altında dış
servis yoktur.

## 1. Roller ve ekranlar

Sistem iki rolle çalışır:

- **M&P mühendisi** (malzeme ve proses): standart yükler, sistemin çıkardığı
  kabul dokümanını gözden geçirip onaylar, yeni revizyonların farklarını
  inceler.
- **Giriş kalite kontrol**: gelen partinin CoC / test raporunu yükler, karar
  alır, iç laboratuvar sonuçlarını girer.

Ayrıca bir **depo ekranı** partilerin raf ömrünü ve durumunu (kabul, red,
bekletiliyor, M&P incelemesi bekliyor) gösterir.

Bugün: ekran yok. Kabul dokümanı Markdown/Word olarak üretiliyor
(`arayuz/dokuman_uretici.py`). Streamlit ekranları sıradaki dördüncü iş.

## 2. Malzeme kataloğu

Katalog SQLite'ta tutulur ve şu bağları kurar:

```
malzeme kodu ──► standart + revizyon + tip/sınıf ──► onaylı kabul dokümanı sürümü
      └──────► onaylı tedarikçiler
```

Her malzeme kodu tek bir tip/sınıf kombinasyonuna bağlıdır (ör.
`AST-001 → MIL-PRF-23377K, Type I, Class N`). Kararda hangi şartların
uygulanacağı bu kombinasyondan ve şartların `uygulanabilirlik` alanından
çıkar; tip/sınıf sertifikadan tahmin edilmez.

Bugün: `katalog/` iskelet. Karar motoru tip/sınıfı hâlâ sertifikadaki atıftan
okuyor (`kural/karar_motoru.atfi_coz`); katalog gelince oradan alınacak.

## 3. Kabul dokümanı sürümleri ve karar kaydı

Kabul dokümanları değiştirilemez sürümlerle tutulur (v1, v2, ...). Bir sürüm
onaylandıktan sonra değişmez; düzeltme yeni sürümdür. Giriş kalite yalnızca
onaylanmış bir sürümle karar verebilir.

Her karar şunları kaydeder:

- kabul dokümanı ve sürümü,
- kararın dayandığı PDF sayfası (sertifika ve standart),
- model ve istem sürümü (dil modeli kullanıldıysa),
- kararı alan kullanıcı ve zaman.

Bugün: `KabulDokumani.durum` (taslak / onaylandi) var; sürüm numarası ve
karar kaydı yok. `katalog/` ve `kayit/` iskelet; katalog ve onay akışı
sıradaki üçüncü iş.

## 4. Revizyon

Depodaki partiler için **siparişte yazan revizyon** geçerlidir. Standardın
yeni revizyonu gelince etkilenen malzeme kodları ve partiler "M&P incelemesi
bekliyor" olarak işaretlenir, kilitlenmez: kullanım sürer, M&P mühendisi
farkı inceleyip kabul dokümanının yeni sürümünü onaylar ya da gerek olmadığını
kaydeder.

Şart hizalaması madde numarasıyla değil, **test kimliğiyle (ad + metot)**
yapılır; revizyonlar arasında madde numaraları kayar. Şüpheli değişiklikler
(ör. bir sınırın ±0 değişmesi, birimin değişip sayının aynı kalması) ayrıca
işaretlenir.

Bugün: `revizyon/revizyon_karsilastirici.py` farkları buluyor ve şüpheli
değişiklikleri işaretliyor (`supheli_nedenleri`); test tablosu satırlarını
test adıyla eşliyor, metin şartlarını madde numarası ve başlıkla. Ad +
metotla hizalama ve parti işaretleme katalogla birlikte gelecek.

## 5. Sonuç kaynağı ve parti kuralı

Kabul dokümanında her testin bir **sonuç kaynağı** vardır:
`sonuc_kaynagi: "coc" | "ic_laboratuvar"`, varsayılan `coc`. İç laboratuvar
sonuçları ekrandan girilir; bu testler CoC'de aranmaz.

Parti kuralı:

- bir test bile **uygun değil** ise parti **uygun değil** (red),
- uygun değil yoksa ve en az bir test **insan incelemeli** ise parti
  **bekletilir** (inceleme),
- hepsi uygunsa parti **uygun** (kabul).

Bugün: alan şemada var. Karar motoru iç laboratuvar testlerini CoC'de aramıyor
ve sonuç girilemediği için "insan incelemeli" veriyor, yani parti bekletiliyor.
Parti kuralı `kontrol_et` sonucundaki `belge_karari` ile aynı.

## 6. Dil modelinin sınırı

Dil modeli **yalnızca** şunları döndürür (`sozlesme/okuma.py`, `HamOkuma`):

- ham metin (belgede yazdığı gibi, ör. "15 to 30 seconds"),
- kaynak konum (sayfa, madde, tablo satırı),
- sınır yönü (en_az, en_cok, aralik, tam, belirsiz).

Sayıya çevirme, pint birimine normalleştirme, birim dönüşümü ve sınırla
karşılaştırma kurallarda yapılır (`kural/`). Sözleşmede sayı, birim ya da
karar alanı yoktur; şema bunu zorlar (`tests/test_okuma_sozlesmesi.py`).

**"Yalnız dil modeli" modu** (modelin doğrudan `TestSarti` yazması) yalnızca
`deney/` klasöründen çalıştırılabilir ve ürünün içinde bulunmaz
(`deney/yalniz_dil_modeli.py`, `deney/dil_modeli_cikar.py`).
`tests/test_katmanlar.py` ürünün `deney/` paketini içe aktarmadığını denetler.

Bugün: sözleşme hazır, onu dolduran ürün içi dil modeli çıkarıcısı yok
(sıradaki ikinci iş). Yalnız dil modeli deneyi çalışıyor.

## 7. Ölçüm

- **Yanlış kabul oranı (FAR)** hem parametre (test satırı) hem parti (belge)
  düzeyinde, %95 Wilson güven aralığıyla raporlanır. Birincil ölçüt parti
  düzeyidir. (`deney/karar_olcumu.py`, `deney/karar_olc.py`)
- Alan bazında F1 ve belge başına süre önceki gibi ölçülür
  (`deney/degerlendirme.py`).
- Standartlar `data/bolunme.yaml` ile **geliştirme** ve **test** kümesine
  ayrılır. Test kümesi dil modeli çıkarıcısı bitene kadar kullanılmaz:
  `test_kumesi_acik: false` iken `deney/dil_modeli_cikar.py` test kümesindeki
  standardı reddeder (`deney/bolunme.py`). Kilidi yalnız proje sahibi açar.

Bugünkü bölünme: geliştirme MIL-PRF-23377 G/H/J/K; test MIL-PRF-81733D ve
MIL-PRF-85285E. Kural tabanlı çıkarıcı bu iki belgeye göre düzeltilmedi
(docs/gorulmemis_belgeler_raporu.md), bu yüzden test kümesi olarak temiz.

## Şema eklemeleri

| Alan | Yer | Anlamı |
|---|---|---|
| `urun_tanimi` | `KabulDokumani` | Tip, sınıf ve kompozisyon tanımları (`UrunTanimi`: `tipler`, `siniflar`, `kompozisyonlar`; her kayıt kod, açıklama, kaynak). Şart değildir (etiketleme kılavuzu K2). |
| `uygulanabilirlik` | `TestSarti`, `Kosul`, `RafOmru`, `NumuneHazirlama` | Şartın geçerli olduğu kodlar, ör. "Chromium content (class N only)" için `["Class N"]`. Boşsa hepsi. Ürün tanımı doluysa her kod orada tanımlı olmalı. |
| `yon` | `Sinir` | `en_az`, `en_cok`, `aralik`, `tam`, `belirsiz`. Boşsa alt/üst sınırdan çıkarılır. Yazılmışsa alt/üst ile tutarlı olmalı. `belirsiz` (ör. 23377K 3.11: "en az" mı "tam" mı belli değil) → karar motoru karşılaştırmaz, insan incelemesine gönderir. |
| `sonuc_kaynagi` | `TestSarti` | `coc` (varsayılan) ya da `ic_laboratuvar`. |

Eski JSON dosyaları (yeni alanlar olmadan) aynen okunur.

## Klasör yapısı

```
src/malzeme_kabul/
  sozlesme/   şemalar: kabul dokümanı (sema), sertifika, dil modeli okuması (okuma)
  belge/      PDF okuma, PDF türü, dosya adlandırma
  cikarim/    kural tabanlı çıkarıcı, yerel dil modeli istemcisi (yalnız localhost)
  kural/      birimler, karar motoru (kabul/red yalnız burada)
  revizyon/   revizyon farkları ve güncelleme önerileri
  katalog/    (iskelet) SQLite katalog, doküman sürümleri, onaylı tedarikçiler
  kayit/      (iskelet) karar kaydı
  hat/        (iskelet) belge → çıkarım → kural → kayıt akışı
  arayuz/     kabul dokümanı çıktısı (Markdown/Word); ileride Streamlit
deney/        yalnız dil modeli deneyi, ölçüm (F1, FAR), sentetik sertifika, gold taslak araçları
scripts/      ürün betikleri (kabul dokümanı üret, revizyon karşılaştır, PDF türü), hook'lar, CI
data/
  raw/        standart PDF'leri
  sentetik/   sentetik sertifikalar ve doğru kararları
  bolunme.yaml  geliştirme / test bölünmesi
  calisma/    yerel çalışma verisi (SQLite, kararlar, yüklenen belgeler); git'e girmez
  gold/       doğru cevaplar (yalnız proje sahibi yazar)
```

Bağımlılık yönü: `sozlesme` yalnız kendine ve `kural/birimler`'e bağlıdır;
`kural` dil modeli istemcisine bağlanmaz; ürün `deney/`'i hiç içe aktarmaz.
Hepsi `tests/test_katmanlar.py` ile denetlenir.

Deney betikleri depo kökünden çalıştırılır, ör.
`python deney/karar_olc.py ...` ya da `python -m deney.karar_olc ...`.

## Sıradaki işler

1. Colab defterini çalışır hale getirmek.
2. Dil modeli çıkarıcısı (`HamOkuma` üreten, ürün içi).
3. Katalog ve onay akışı (sürümler, karar kaydı, revizyon işaretleme).
4. Streamlit ekranları (M&P, giriş kalite, depo).
