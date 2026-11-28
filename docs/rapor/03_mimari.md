# 3. Mimari

> Durum: taslak. Kaynaklar: `docs/mimari.md` (24 Kasım 2026 onaylı mimari),
> `docs/guvenlik.md`, `docs/dil_modeli_ortami.md` ve `src/malzeme_kabul/`
> altındaki kod (main, 28 Kasım 2026).

## 3.1 Temel ilke: okuma ile kararın ayrılması

Sistemin bütün tasarımı tek bir ayrıma dayanır: **belgeyi dil modeli okur,
kabul ya da red kararını yalnız kesin kurallar verir.** Dil modeli belgede
yazanı aktarır (ham metin, kaynak konum, sınır yönü); sayıya çevirme, birim
dönüşümü ve sınırla karşılaştırma Python kodunda yapılır. Bu ayrım üç amaca
hizmet eder:

1. **Denetlenebilirlik.** Her karar, standarttaki bir maddeye ve kodda
   okunabilir bir kurala dayanır; kararın neden verildiği tekrar üretilebilir.
2. **Yanlış kabulün sınırlanması.** Dil modeli bir sayıyı uydurabilir ya da
   sınırın yönünü çevirebilir (bkz. 5.4). Model karar vermediği ve okuması
   kanıt, yön ve kural okumasıyla denetlendiği için bu hataların büyük kısmı
   insan incelemesine düşer. Denetimlerin yakalayamadığı durumlar da vardır
   (ör. metinde yön ipucu yoksa modelin yönü kalır); bunlar 8. bölümde
   tartışılır.
3. **Gizlilik.** Model yerel çalışır ve yalnız `localhost`'a bağlanılır;
   tedarikçi belgeleri makineden çıkmaz.

Ayrım ürün içinde sözleşmeyle zorlanır: ürünün dil modelinden kabul ettiği
yapılar `sozlesme/okuma.py` içindeki `HamOkuma` (standart tarafı) ve
`SertifikaOkumaYaniti` (sertifika tarafı) şemalarıdır. Bu şemalarda sayı,
birim çevrimi ya da karar alanı yoktur; `HamOkuma` için bunu
`tests/test_okuma_sozlesmesi.py` denetler. (Yalnız `deney/` altında çalışan
"yalnız dil modeli" deneyinde model doğrudan `TestSarti` yazar; bkz. 5.1.)

## 3.2 Kullanıcılar ve iş akışı

Sistem iki rolle çalışır:

- **M&P mühendisi** (malzeme ve proses): standardı yükler, sistemin çıkardığı
  kabul dokümanı taslağını gözden geçirip düzeltir ve onaylar; standardın yeni
  revizyonu geldiğinde farkları inceler.
- **Giriş kalite kontrol**: gelen partinin malzeme kodunu ve lotunu seçer,
  tedarikçinin CoC / test raporunu yükler, her test için kararı ve dayandığı
  maddeyi görür, gerekirse gerekçeyle düzeltir.

Bir **depo ekranı** partilerin durumunu (serbest, karantina, bekliyor), M&P
incelemesi işaretini ve raf ömrü uyarılarını gösterir.

```
 M&P mühendisi                         Giriş kalite
 ─────────────                         ────────────
 standart PDF ──► çıkarım ──► taslak    CoC/TR PDF ──► okuma ──► kanıt ──► kural ──► karar
                               │                                                 │
                        düzelt + onayla                                   parti durumu
                               │                                                 │
                               ▼                                                 ▼
                 onaylı kabul dokümanı (sürüm) ─────────────────────► katalog + denetim kaydı
                               ▲
 yeni revizyon ──► fark ──► "M&P incelemesi bekliyor"
```

Ekranlar Streamlit ile yazıldı (`arayuz/uygulama.py`); iş kuralları ekrandan
ayrı, Streamlit'siz test edilen `arayuz/ekran_verisi.py` modülündedir.
Ekranla çekirdek arasındaki sözleşme `docs/arayuz_sozlesmesi.md`'de tanımlıdır.

## 3.3 Katmanlar

Kod `src/malzeme_kabul/` altında dokuz katmana ayrılır:

| Katman | Görevi | Dil modeli? |
|---|---|---|
| `sozlesme` | Şemalar: kabul dokümanı (`sema.py`), sertifika, dil modeli okuması (`okuma.py`) | yok |
| `belge` | PDF'i sayfa sayfa metin ve tabloya çevirme (pdfplumber), PDF türü (metin / taranmış), dosya adlandırma | yok |
| `cikarim` | Kural tabanlı standart çıkarıcısı, sertifika okuyucu, yerel model istemcisi (yalnız localhost) | istemci burada |
| `kural` | Birimler (pint), karar motoru, kanıt doğrulama, yön doğrulama, okuma karşılaştırma, raf ömrü | **yasak** |
| `revizyon` | İki revizyon arasındaki şart farkları ve güncelleme önerileri | yok |
| `katalog` | SQLite katalog: malzeme kodları, değiştirilemez doküman sürümleri, onaylı tedarikçiler, partiler | yok |
| `kayit` | Zincirli (hash) denetim kaydı | yok |
| `hat` | Belge → okuma → kanıt → kural → karar → kayıt hattı; katalogla karar, revizyon etkisi, raf ömrü raporu | çağırır |
| `arayuz` | Streamlit ekranları, kimlik doğrulama, Markdown/Word kabul dokümanı çıktısı | yok |

Bağımlılık yönü kodla denetlenir (`tests/test_katmanlar.py`): `sozlesme`
yalnız kendine ve `kural/birimler`'e bağlıdır; `kural` dil modeli istemcisini
içe aktarmaz; ürün, deney paketi `deney/`'i hiç içe aktarmaz. "Yalnız dil
modeli" yaklaşımı (modelin doğrudan şart ve sınır yazması) bu yüzden ürünün
içinde değil, yalnız `deney/` altında çalışır.

## 3.4 Kabul dokümanı ve şema

Kabul dokümanı (`sozlesme/sema.py`, `KabulDokumani`) standarttan çıkarılan
şartları tutar:

- **testler** (`TestSarti`): kimlik, ad, test metodu, sınır (`Sinir`: alt, üst,
  birim, yön, özgün metin), test türleri (kabul, yeterlilik, ömür uzatma,
  muayene), sonuç kaynağı (CoC, iç laboratuvar, iç muayene), tip/sınıf
  uygulanabilirliği ve test koşulu;
- **koşullar**: depolama ve kullanım koşulları (sıcaklık, süre, nem);
- **raf ömrü**: kap türüne göre birden çok kayıt olabilir;
- **numune hazırlama**: kupon malzemesi, yüzey hazırlığı, kuru film kalınlığı,
  kürlenme;
- **ürün tanımı**: tip, sınıf ve kompozisyon tanımları (şart sayılmaz).

Her kayıt dayandığı standardı, revizyonu ve maddeyi (`Kaynak`) taşımak
zorundadır; kabul dokümanında her satırın yanında madde numarası görünür.
Birimler pint'in tanıdığı biçimde yazılır ve şema bunu doğrular. Sınırın yönü
`en_az`, `en_cok`, `aralik`, `tam` ya da `belirsiz` olabilir; `belirsiz` sınır
karşılaştırılmaz, insan incelemesine gider.

## 3.5 Standart tarafı: kabul dokümanı üretimi

Üç çıkarım yolu tanımlıdır:

1. **Yalnız kural** (`cikarim/kural_cikarici.py`): düzenli ifadeler ve MIL-PRF
   belge yapısıyla numaralı paragrafları, test tablosunu, kabul / yeterlilik
   muayenesi kapsamını, panel tablosunu, raf ömrü ve kap ömrü maddelerini
   okur. Dil modeli kullanmaz; taban çizgisidir.
2. **Yalnız dil modeli** (`deney/yalniz_dil_modeli.py`, yalnız deney): her
   sayfa yerel modele gönderilir, model JSON şemasına zorlanarak doğrudan
   `TestSarti` listesi yazar.
3. **Hibrit** (`deney/hibrit_standart.py`, şimdilik deney): kural çıktısı
   aynen kalır; model yalnız kuralın bulmadığı ve özgün metni sayfada geçen
   testleri ekler; eklenen testin sınırını model değil kural, özgün metinden
   yeniden hesaplar; kural ile model aynı test için farklı sınır, birim ya da
   yön bulursa sınır `belirsiz` yapılır.

Ürün içi standart okuma hattı (`hat/hibrit_hat.standart_okumalarini_dogrula`)
modelden gelen `HamOkuma`'ları doğrular: kanıtsız okuma reddedilir, yönü
metinle çelişen okuma `belirsiz` yapılır. Taslak M&P ekranında düzeltilir ve
onaylanır; onaylı doküman Markdown ve Word olarak da dışa verilir
(`arayuz/dokuman_uretici.py`).

## 3.6 Sertifika tarafı: çapraz kontrol hattı

`hat/hibrit_hat.py` iki modda çalışır (`MALZEME_KABUL_MODU`, varsayılan
`kural`):

- **kural**: sertifika tablosu başlık adlarıyla okunur
  (`cikarim/sertifika_okuyucu.kural_ile_oku`).
- **hibrit**: her sayfa yerel modele gider; model hücreleri belgede yazdığı
  gibi döndürür. Ardından üç güvenlik adımı çalışır:
  1. **Kanıt doğrulama** (`kural/kanit_dogrulama.py`): modelin okuduğu her
     satır ve üst bilgi (tedarikçi, parti no, sertifika no, üretim tarihi,
     standart atfı) belgenin metin katmanında aranır. Kanıtsız okuma karara
     girmez; ilgili denetim insan incelemeli olur.
  2. **Okuma karşılaştırma** (`kural/okuma_karsilastirma.py`): sertifika
     kuralla da okunur ve iki okuma karşılaştırılır. Anlaşmazlıkta hiçbir
     okuma sessizce karara girmez: şart insan incelemeli olur; iki okuma da
     sınır dışındaysa "uygun değil" kalır ve anlaşmazlık kaydedilir.
  3. **Yedek**: model yanıt vermezse ya da şemaya uymazsa kural okumasına
     düşülür ve bu kayda yazılır; ama karar bu okumayla verilmez: satırlar
     insan incelemeli olur ve parti bekletilir (eksik bilgi "uygun"a yol
     açmaz).

Karar her iki modda aynı karar motoruyla verilir (`kural/karar_motoru.py`,
`hat/katalog_karari.py`). Adımlar:

1. Kabul dokümanı malzeme koduna göre katalogdan (en son onaylı sürüm), tip ve
   sınıf katalogdan alınır; sertifikadaki atıf yalnız çelişki denetimidir.
2. Yalnız o tip/sınıfa uygulanan kabul testleri aranır.
3. Sertifikadaki test adı normalleştirilip eşanlamlılar tablosu, kaynak tablo
   adı ve kelime benzerliğiyle eşleştirilir.
4. Sonuç metni ("320", "<1", "Conforms") sayı aralığına ya da beyaz listeyle
   geçti/kaldı sonucuna çevrilir.
5. Birim pint ile hedef birime çevrilir; çevrilemeyen birim insana gider.
6. Okunan aralık sınırın tamamen içindeyse **uygun**, tamamen dışındaysa
   **uygun değil**, ikisi de değilse **insan incelemeli**. Yuvarlama yapılmaz;
   sınıra çok yakın değerler (bağıl 1e-6, sıfır sınırda mutlak 1e-12) insan
   incelemesine gider. Birim dönüşümü yoksa ve sayı metni float'a kayıpsız sığıyorsa tam
   eşitlikte dahil/hariç kuralı
   karar verir (`docs/sinir_yakinligi.md`).

Parti kuralı: bir test uygun değilse parti reddedilir (karantina); uygun değil
yoksa ve bir test insan incelemeliyse parti bekletilir; yalnız boş olmayan ve
tamamı uygun karar listesi kabul (serbest) verir. Makine parti durumunu yalnız
daha kısıtlayıcı yöne değiştirir (tek istisna: hiç karar verilmemiş yeni
parti); karantinadaki partiyi makine serbest bırakmaz, serbest bırakma
gerekçeli bir insan düzeltmesiyle (`karari_duzelt`) yapılır. Proje sahibi 28
Kasım 2026'da bu düzeltmeyi yalnız M&P rolüne bırakmaya karar verdi.
<!-- Teslim öncesi: rol kısıtı kodda uygulandı mı, denetle. Bu taslak
yazılırken düzeltme formu giriş kalite ekranındaydı ve rol denetlenmiyordu. -->

## 3.7 Revizyon takibi

`revizyon/revizyon_karsilastirici.py` iki revizyonu (ör. MIL-PRF-23377 J → K)
üç düzeyde karşılaştırır: numaralı paragraflar (eklenen, kaldırılan, değişen,
numarası kayan), test tablosu satırları ve kabul muayenesi kapsamı. Değişiklik
sayısal, metinsel ya da biçimsel diye derecelenir; şüpheli değişiklikler (ör.
birimin değişip sayının aynı kalması) ayrıca işaretlenir. Karşılaştırma dil
modeli kullanmaz.

Yeni revizyon kataloğa eklenince (`hat/revizyon_etkisi.py`) eski revizyona
bağlı malzeme kodları ve partiler "M&P incelemesi bekliyor" olarak işaretlenir
ama kilitlenmez: depodaki partiler için siparişte yazan revizyon geçerlidir.
M&P farkı inceleyip yeni sürümü onaylar ya da gerek olmadığını kaydeder.

## 3.8 Katalog, sürümler ve denetim kaydı

- **Katalog** (`katalog/veritabani.py`, SQLite): malzeme kodu → standart +
  revizyon + tip/sınıf → onaylı kabul dokümanı sürümü; onaylı tedarikçiler;
  partiler (lot, tedarikçi, sipariş revizyonu, üretim tarihi, kap türü, durum).
- **Değiştirilemez sürümler**: onaylı doküman sürümü SQLite tetikleyicileriyle
  UPDATE/DELETE'e kapalıdır ve SHA-256 özeti taşır; düzeltme yeni sürümdür.
  Örnek verinin dokümanları "demo onayı" olarak işaretlenir ve gerçek M&P
  onayıyla karışmaz.
- **Denetim kaydı** (`kayit/denetim_kaydi.py`): her karar, onay ve düzeltme
  kullanıcı, zaman, doküman sürümü, PDF sayfası, model ve istem sürümüyle
  yalnız eklenir. Her kayıt bir önceki kaydın özetini taşır (hash zinciri);
  zincir `scripts/denetim_dogrula.py` ile doğrulanır. Durum değişikliği ile
  kaydı tek veritabanı işlemidir: kayıt yazılamazsa durum da değişmez.
- **Raf ömrü** (`kural/raf_omru.py`): son kullanma = üretim tarihi + onaylı
  dokümandaki raf ömrü. Kap türü bilinmiyor ve birden çok kayıt varsa en kısa
  ömür alınır. Süresi yaklaşan partiler için ömür uzatma testleri listelenir.

## 3.9 Çalışma ortamı ve güvenlik

- **Yerel model**: `cikarim/yerel_model.py` yalnız `localhost`, `127.0.0.1`
  ve `::1` adreslerini kabul eder, vekil sunucu ayarlarını yok sayar. Ollama
  ve llama.cpp desteklenir; iki sunucu da JSON şemasını dilbilgisine çevirerek
  üretimi şemaya zorlar. `src/` altında dış servis kütüphanesi içe aktarmak
  `tests/test_dis_servis_yok.py` ile yakalanır.
- **İki donanım**: geliştirme ve ölçüm Google Colab'da (T4 GPU, 7–8B model,
  4 bit); nihai çalışma dizüstünde (7,7 GB RAM, 1–3B model). Colab'a yalnız
  kamuya açık standartlar ve sentetik sertifikalar yüklenir.
- **Ağsız Docker**: `docker-compose.yml` uygulamayı dış ağa çıkışı olmayan bir
  ağda çalıştırır; `scripts/ag_testi.sh` ağın kapalı olduğunu gösterir.
  Varsayılan parola yoktur; parolalar Docker secrets ile verilir.
- **Tehdit modeli** (`docs/guvenlik.md`): istem enjeksiyonu, kötü niyetli
  PDF, bağımlılık açıkları, kimlik doğrulama, model dosyası bütünlüğü,
  konteyner ve doğru cevap verisinin bütünlüğü. Örnek önlemler: istemde belge
  sınırlayıcısının kapatılamaması, PDF boyut / sayfa / süre sınırı, sabit
  bağımlılık sürümleri, `data/gold/` için hook ve CI denetimi.

## 3.10 Henüz olmayanlar

<!-- Raporu teslim öncesi güncelle. 28 Kasım 2026 durumu: -->

- Ürün içi standart dil modeli çıkarıcısı (`HamOkuma` üreten) henüz yok;
  standart tarafı hibrit yalnız deney olarak çalışıyor.
- OCR katmanı, güven skoru ve mühendis düzeltmelerinden etiketli veri
  (düzeltme döngüsü) ayrı işler olarak geliştiriliyor.
- Revizyonlar arası test hizalaması test adıyla yapılıyor; ad + metotla
  hizalama henüz yok.
