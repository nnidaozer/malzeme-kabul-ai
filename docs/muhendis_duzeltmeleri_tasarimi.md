# Tasarım notu: Mühendis düzeltmelerinden yeni etiketli veri

Durum: tasarım. Bu not için kod yazılmadı.

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
| `alan` | Değişen alan, değerlendirmedeki adlarla aynı, ör. `test.sinir.ust`. |
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

- Olaylar yerel bir dosyada (satır başına bir JSON olay) ya da yerel SQLite
  tablosunda tutulur. Sistem internetsiz çalıştığı için dış servis kullanılmaz.
- Bir belgenin onaylanmış kabul dokümanı = sistem çıktısı + o belgenin bütün
  olaylarının sırayla uygulanması. Böylece her an hangi değerin kimden geldiği
  bilinir.
- Onaylanan doküman `KabulDokumani` şemasında dışa verilir ve **etiket adayı**
  olur. `data/gold/` klasörüne otomatik yazılmaz; proje sahibi adayı inceleyip
  kendisi taşır (CLAUDE.md, kural 2).

## Değerlendirmede kullanım

- Olaylardaki `alan` adları `degerlendirme.alanlari_duzlestir` ile aynı
  olduğundan alan bazında hata dökümü doğrudan çıkar.
- Bir belgenin düzeltmeleri, sistem o belgeyle bir daha eğitilmeden ya da
  istemi o belgeye göre ayarlanmadan önce test kümesine ayrılır. Aksi halde
  ölçüm şişer.
- Aynı belgeyi iki mühendis düzeltirse ayrışan alanlar bağımsız etiketlemedeki
  gibi (bkz. `bagimsiz_etiketleme_istemi.md`) proje sahibine gösterilir.

## Açık sorular

- Arayüz hangi teknolojiyle yapılacak ve olayları nereye yazacak?
- Mühendis kimliği nasıl belirlenecek (yerel kullanıcı adı yeterli mi)?
- Çapraz kontrol kararlarındaki ("uygun değil" → "uygun") düzeltmeler de aynı
  olay yapısıyla mı tutulsun? Öneri: evet, `kayit` türü `karar` olarak.
