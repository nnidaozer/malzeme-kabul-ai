# Plan: Düzeltme döngüsü ve düzeltme panosu

Durum: 28 Kasım 2026. Nida'nın "Şimdi başlanacaklar / 3. Düzeltme döngüsü"
isteğinin planı. Tasarım notu: `docs/muhendis_duzeltmeleri_tasarimi.md`.

İstek: M&P ekranında mühendisin yaptığı her düzeltme kaydedilsin ve yeni
etiketli veri olarak saklansın; düzeltme oranını gösteren basit bir pano.

Sınırlar: `data/gold/` klasörüne hiçbir şey yazılmaz (etiket adayları ayrı
klasördedir, gold'a Nida taşır). İnternetsiz; yeni dış bağımlılık yok. Her
yeni fonksiyon testle gelir.

## Adım 1. Alan düzleştirme üründe tek kaynak

`deney/degerlendirme.py` içindeki `alanlari_duzlestir`, `degerler_esit`,
`kayit_bolumleri`, `_Birim`, `_normal_metin` (ve yardımcıları)
`src/malzeme_kabul/sozlesme/alanlar.py` modülüne taşınır. `deney/degerlendirme.py`
bunları oradan içe aktarır ve aynı adlarla yeniden dışa verir (deney kodu ve
mevcut testler değişmeden çalışır). Neden: düzeltme olaylarının `alan` adları
F1 ölçümüyle aynı olmalı ve ürün `deney/` paketini içe aktaramaz.

## Adım 2. Düzeltme olay deposu (`kayit/duzeltme_kaydi.py`)

Katalogla aynı SQLite bağlantısında iki tablo; ikisi de yalnız eklenir
(UPDATE/DELETE tetikleyicilerle reddedilir):

- `duzeltme_tabanlari`: taslağın sistem çıktısı (taban). Taslak başına bir
  satır: `taslak_id`, `belge`, `icerik` (KabulDokumani JSON), `ozet`
  (SHA-256), `ureten` (JSON: yaklaşım `kural`/`dil_modeli`/`hibrit`/`bilinmiyor`,
  model, istem sürümü), `zaman`.
- `duzeltme_olaylari`: alan düzeyinde olaylar. `olay_id`, `zaman` (UTC),
  `muhendis`, `taslak_id`, `belge` (ör. `MIL-PRF-23377K`), `dokuman_surumu`
  (düzeltilen dokümanın içerik özeti), `kayit_turu` (`test`, `raf_omru`,
  `kosul`, `numune`), `kayit` (ör. `viscosity`), `alan` (ör. `test.sinir.ust`),
  `eski_deger`, `yeni_deger` (JSON), `islem` (`degistir`, `ekle`, `sil`,
  `onayla`), `kaynak` (madde ve sayfa), `gerekce`, `ureten`.

Fonksiyonlar:

- `DuzeltmeKaydi(baglanti)`: şemayı kurar.
- `taban_kaydet(taslak_id, dokuman, ureten)` / `taban(taslak_id)`. Tabanı
  olmayan eski taslakta ilk düzeltmede o anki içerik taban olur, üreten
  `bilinmiyor`.
- `EK_ALANLAR` ve `duzeltme_alanlari(dokuman)`: düzeltme döngüsünün saydığı
  alanlar `alanlari_duzlestir` (F1 alanları) ile her testin dolu ek
  alanlarıdır: `test.kaynak.sayfa`, `test.sinir.orijinal_metin`,
  `test.sonuc_kaynagi`. Bunlar tablodan düzenlenir ama F1'de yoktur.
  Olaylara ve panonun paydasına girer, F1 ölçümüne girmez. Boş (None) sayfa
  alan sayılmaz.
- `alan_farklari(eski, yeni)`: iki doküman arasındaki alan farkları
  (`duzeltme_alanlari` + `degerler_esit`; eski yok → `ekle`, yeni yok → `sil`,
  ikisi de var ve farklı → `degistir`).
- `duzeltmeleri_kaydet(...)`: bir kaydetmenin farklarını olay olarak yazar.
- `onaylari_kaydet(...)`: onay anında tabanla son doküman arasında net değişmemiş
  her alan için `onayla` olayı yazar. Böylece doğru okunmuş alanlar da
  görünür ve oran şişmez. Değiştirip geri alınan alan net değişmemiştir,
  `onayla` alır.
- `olaylar(taslak_id=None)`.

## Adım 3. Ekran işlerine bağlama (`arayuz/ekran_verisi.py`)

- `standart_yukle` taslakla birlikte tabanı tek işlemde kaydeder (üreten:
  `kural`).
- `taslak_duzelt(..., gerekce=None)` taslak güncellemesi, denetim kaydı ve
  düzeltme olaylarını tek işlemde yazar. Eski taslak da bu işlemin içinde,
  yazma kilidi alındıktan sonra okunur.
- `taslak_onayla` onay, denetim kaydı ve `onayla` olaylarını tek işlemde yazar.

## Adım 4. Etiket adayı (`kayit/duzeltme_kaydi.py`)

`etiket_adayi_yaz(katalog, taslak_id, klasor)`: onaylı taslağın son dokümanını
`<belge>_taslak<id>.json` (KabulDokumani) ve olaylarını
`<belge>_taslak<id>.olaylar.jsonl` olarak yazar. Varsayılan klasör
`data/calisma/etiket_adaylari/` (git'e girmez; `MALZEME_KABUL_ETIKET_ADAYI` ile
değişir). Gold koruması public `gold_yolu_mu(yol)` ile yapılır. Verilen yol da
bağlantıları çözülmüş yol da denetlenir. Her parça büyük/küçük harfe
duyarsız ve sondaki nokta ile boşluk atılarak `gold` ile karşılaştırılır.
Klasör oluşturulduktan sonra yeniden denetlenir. Dosya adında
`[A-Za-z0-9._-]` dışındaki karakterler `_` olur, belge numarası yol kaçışı
yapamaz. Her son dosya yolu klasörün içinde mi ve gold'a çözülüyor mu diye
denetlenir. Yazma aynı klasörde geçici dosyaya yapılır ve `os.replace` ile
taşınır, hedefteki dosya bağlantısı izlenmez. Onaylanmamış taslak
reddedilir. Arayüz adayı `uygulama.etiket_adayi_kaydet` ile yazar. Hata
olursa onay bozulmaz, istisna metnini içeren bir uyarı gösterilir.

Komut satırı `scripts/etiket_adaylari.py` bütün onaylı taslakları dışa
verir ve düzeltme oranı özetini basar. Gold klasörü verilirse 2 döner. Var
olan adayın üzerine yazmaz ("atlandı" basar), `--uzerine-yaz` ile yeniler.
Bir taslakta hata olursa diğerlerine devam eder ve 2 döner.

## Adım 5. Pano

- `duzeltme_panosu(baglanti) -> PanoOzeti`: yalnız onaylanmış taslaklar üzerinden
  toplam alan, düzeltilen alan, düzeltme oranı; belge, alan, kayıt türü,
  yaklaşım (üreten) ve mühendis kırılımları; gün bazında eğilim; onay bekleyen
  düzeltme sayısı (ayrı gösterilir, orana girmez). Payda `duzeltme_alanlari`
  (ek alanlar dahil). Aynı belgenin her taslağı ayrı sayılır.
- Tabanı `bilinmiyor` olan onaylı taslakların sistem çıktısı bilinmez. Bu
  taslaklar ana orana ve belge, alan, kayıt türü, mühendis ve gün
  kırılımlarına girmez. Yalnız `yaklasim_bazinda` içinde görünür ve
  `PanoOzeti.tabani_bilinmeyen_taslak` olarak sayılır.
- Kişi atfı: net düzeltilen alan o alanı son düzelten mühendise, düzeltilmeyen
  alan onaylayana sayılır. Gün atfı: taslağın onay günü. Onaylayan ve onay
  zamanı katalogdaki onaylı sürümden (`dokuman_surumleri`) okunur. Bu yüzden
  bütün alanları düzeltilmiş, hiç `onayla` olayı olmayan taslak da doğru
  kişiye ve güne düşer.
- Streamlit: M&P rolüne "Düzeltme panosu" ekranı (metrikler, alan bazında
  çubuk grafik, tablolar). "Taslağı düzelt ve onayla" ekranına isteğe bağlı
  gerekçe kutusu ve onayda etiket adayının yazıldığı yer.

## Kapsam dışı

Giriş kalite parti kararı düzeltmeleri (`karari_duzelt`) bu PR'da olay deposuna
girmez; denetim kaydında zaten var. İstenirse `kayit_turu = karar` ile eklenir.
