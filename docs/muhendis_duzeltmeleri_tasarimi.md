# Tasarım notu: Mühendis düzeltmelerinden yeni etiketli veri

Durum: uygulandı (28 Kasım 2026, plan: `docs/plan_duzeltme_dongusu.md`).
Kod: `src/malzeme_kabul/kayit/duzeltme_kaydi.py` (olay deposu, etiket adayı,
pano), `arayuz/ekran_verisi.py` (`standart_yukle`, `taslak_duzelt`,
`taslak_onayla`), Streamlit "Düzeltme panosu" ekranı, `scripts/etiket_adaylari.py`.

## Amaç

Kalite mühendisi arayüzde sistemin ürettiği kabul dokümanını onaylamadan önce
düzeltir. Her düzeltme, sistemin o belgede neyi yanlış okuduğunun elle
doğrulanmış kaydıdır. Bu kayıtlar saklanırsa:

- çıkarıcının hangi alanlarda ve hangi belge türlerinde hata yaptığı ölçülür,
- yeni standartlar için etiketli veri elle sıfırdan hazırlanmadan birikir,
- ileride istem ya da kural iyileştirmesinin etkisi aynı veriyle sınanır.

## Ne kaydedilir

Her düzeltme bir olaydır. Olaylar eklenerek tutulur, hiçbiri silinmez ya da
üzerine yazılmaz.

| Alan | Açıklama |
|---|---|
| `olay_id` | Benzersiz kimlik. |
| `zaman` | Düzeltmenin yapıldığı an (UTC). |
| `muhendis` | Düzeltmeyi yapan kişi. |
| `belge` | Standart ve revizyon, ör. `MIL-PRF-23377K`. |
| `dokuman_surumu` | Düzeltilen kabul dokümanının sürümü (içerik özeti). |
| `kayit` | Değişen kayıt: tür ve kimlik, ör. `test` / `viscosity`. |
| `alan` | Değişen alan, ör. `test.sinir.ust`. F1 alanları değerlendirmedeki adlarla aynıdır. Tablodan düzenlenen üç ek test alanı da (`EK_ALANLAR`: `test.kaynak.sayfa`, `test.sinir.orijinal_metin`, `test.sonuc_kaynagi`) olay olur. |
| `eski_deger` | Sistemin önerdiği değer. |
| `yeni_deger` | Mühendisin yazdığı değer. |
| `islem` | `degistir`, `ekle` (sistem kaydı kaçırmış) ya da `sil` (sistem fazladan kayıt üretmiş). |
| `kaynak` | Mühendisin dayandığı madde ve sayfa. |
| `gerekce` | İsteğe bağlı kısa not. |
| `ureten` | Eski değeri hangi yaklaşım üretti: kural, dil modeli, hibrit; model ve istem sürümü. |

Mühendis bir alanı değiştirmeden onaylarsa bu da kaydedilir (`islem: onayla`).
Yalnız düzeltmeleri tutmak, doğru okunmuş alanları görünmez yapar ve hata
oranını olduğundan yüksek gösterir.

## Nasıl saklanır

- Olaylar katalogla aynı yerel SQLite dosyasında iki tabloda tutulur:
  `duzeltme_tabanlari` (taslak başına sistem çıktısı, üreteniyle) ve
  `duzeltme_olaylari`. İkisi de yalnız eklenir; UPDATE, DELETE ve üzerine
  yazma tetikleyicilerle reddedilir. Olaylar ayrıca kayıt türünü
  (`kayit_turu`: `test`, `raf_omru`, `kosul`, `numune`) ve taslak kimliğini
  taşır. Sistem internetsiz çalıştığı için dış servis kullanılmaz.
- Tabanı olmayan eski bir taslakta ilk düzeltme (ya da onay) anındaki içerik
  taban olur; üreten `{"yaklasim": "bilinmiyor"}` yazılır.
- Bir belgenin onaylanmış kabul dokümanı = sistem çıktısı + o belgenin bütün
  olaylarının sırayla uygulanması. Böylece her an hangi değerin kimden geldiği
  bilinir.
- Onaylanan doküman `KabulDokumani` şemasında dışa verilir ve **etiket adayı**
  olur. `data/gold/` klasörüne otomatik yazılmaz; proje sahibi adayı inceleyip
  kendisi taşır (CLAUDE.md, kural 2). Adaylar `data/calisma/etiket_adaylari/`
  altına (`MALZEME_KABUL_ETIKET_ADAYI` ile değişir) `<belge>_taslak<id>.json`
  ve `<belge>_taslak<id>.olaylar.jsonl` olarak yazılır. Dosya adında
  `[A-Za-z0-9._-]` dışındaki karakterler `_` olur. `gold_yolu_mu` olan klasör
  reddedilir: bağlantı çözülerek denetlenir, büyük/küçük harfe duyarsızdır,
  sondaki nokta ve boşluk atılır. Gold'a işaret eden dosya bağlantısı
  izlenmez, yazma geçici dosya ve `os.replace` ile yapılır. Komut satırı var
  olan adayın üzerine yazmaz (`--uzerine-yaz` ile yeniler).

## Düzeltme panosu nasıl sayar

- Payda, onaylı taslağın tabanıyla son dokümanının `duzeltme_alanlari`
  birleşimidir: F1 alanları ve dolu ek alanlar. Boş sayfa alan sayılmaz. Ek
  alanlar F1 ölçümüne girmez.
- Aynı belgenin her taslağı ayrı sayılır. Bir belge iki kez yüklenip
  onaylanırsa alanları iki kez paydaya girer.
- Tabanı `bilinmiyor` olan taslakların sistem çıktısı bilinmez, bu yüzden
  oranları ölçüm değildir. Bu taslaklar ana orana ve belge, alan, kayıt
  türü, mühendis ve gün kırılımlarına girmez. Yalnız yaklaşım kırılımında
  (`bilinmiyor`) görünür ve `tabani_bilinmeyen_taslak` olarak sayılır.
- Kişi atfı: net düzeltilen alan, o alanı son düzelten mühendise yazılır.
  Düzeltilmeyen alan onaylayana yazılır. Gün atfı: taslağın onay günü.
  Onaylayan ve onay zamanı katalogdaki onaylı sürümden okunur.

## Değerlendirmede kullanım

- Olaylardaki `alan` adları `alanlari_duzlestir` (tek kaynak
  `sozlesme/alanlar.py`; `deney/degerlendirme.py` oradan alır) ile aynı
  olduğundan alan bazında hata dökümü doğrudan çıkar.
- Bir belgenin düzeltmeleri, sistem o belgeyle bir daha eğitilmeden ya da
  istemi o belgeye göre ayarlanmadan önce test kümesine ayrılır. Aksi halde
  ölçüm şişer.
- Aynı belgeyi iki mühendis düzeltirse ayrışan alanlar bağımsız etiketlemedeki
  gibi (bkz. `bagimsiz_etiketleme_istemi.md`) proje sahibine gösterilir.

## Açık sorular (yanıtlandı)

- Arayüz hangi teknolojiyle yapılacak ve olayları nereye yazacak?
  Yanıt: Streamlit (`arayuz/uygulama.py`); olaylar katalogla aynı yerel
  SQLite dosyasına, taslak güncellemesi ve denetim kaydıyla tek işlemde yazılır.
- Mühendis kimliği nasıl belirlenecek (yerel kullanıcı adı yeterli mi)?
  Yanıt: arayüz girişindeki kullanıcı adı (`arayuz/kimlik.py`, PBKDF2 parolalı
  yerel hesap); `muhendis` alanına o yazılır, boş olamaz.
- Çapraz kontrol kararlarındaki ("uygun değil" → "uygun") düzeltmeler de aynı
  olay yapısıyla mı tutulsun? Yanıt: bu sürümde kapsam dışı. Giriş kalite
  parti kararı düzeltmeleri (`karari_duzelt`) denetim kaydında zaten var;
  istenirse ileride `kayit_turu = karar` ile olay deposuna eklenir.
