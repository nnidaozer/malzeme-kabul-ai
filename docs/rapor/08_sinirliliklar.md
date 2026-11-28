# 8. Sınırlılıklar

> Durum: aday maddeler. Aşağıdakiler depodaki belgelerde (`docs/`) bugün
> kayıtlı bilinen sınırlardır; sonuçlar geldikten sonra seçilip yorumla
> yazılacak. Sonuçlara dayanan sınırlılıklar henüz eklenmedi.

## 8.1 Veri

- Doğru cevaplar (`data/gold/`) henüz onaylanmadı; geliştirme ölçümleri
  onaysız taslaklarla yapıldı.
- Sentetik sertifikalar tek standarttan (MIL-PRF-23377K) ve üreticinin
  bildiği hata türlerinden oluşuyor; gerçek tedarikçi belgelerinin
  çeşitliliğini temsil etmiyor. Kural modunda ölçüm ham hücrelerle yapıldığı
  için "kusursuz okuma" varsayıyor.
- Gerçek CoA'lar havacılık malzemesi değil, laboratuvar kimyasalları; gerçek
  havacılık belgesi sayısı çok az ve test kümesinde kilitli.
- Test kümesi beş revizyon ailesinden oluşuyor; sonuçların genellenebilirliği
  sınırlı.

## 8.2 Yöntem

- Kural çıkarıcı MIL-PRF-23377K'nın düzenine sıkı bağlı; 81733D ve 85285E'de
  test tablosunu bulamadı (`docs/gorulmemis_belgeler_raporu.md`).
- Standart tarafında ürün içi dil modeli çıkarıcısı henüz yok; hibrit
  standart çıkarımı deney olarak çalışıyor.
- Kanıt kontrolü sayının sayfada geçtiğine bakar; birimi ve hangi cümlede
  geçtiğini denetlemez. Sınır yönü hatası bu yüzden ayrı bir kuralla
  yakalanıyor ve o kural da yalnız açık ipuçlarında karar veriyor; metinde
  ipucu yoksa modelin yönü olduğu gibi kalır. Doğru cevap taslaklarının 476
  testinin 151'inde metinde yön ipucu yoktu (`docs/sinir_yonu_hatasi.md`).
- Revizyon karşılaştırıcı testleri ada göre hizalıyor; ad + metotla
  hizalama yok.
- Dil modeli birimi kendiliğinden çevirebilir (ör. °F → °C); birim
  alanındaki hatalar ayrıca izlenmeli (`docs/dil_modeli_ortami.md`).

## 8.3 Güvenlik ve işletim

- Arayüzdeki test kümesi kilidi belge no ve revizyonu dosya adından okuyor;
  dosyayı yeniden adlandırmak kilidi aşar.
- PDF okumada süre sınırı sayfa aralarında denetleniyor; tek bir sayfada
  takılan ayrıştırıcıyı kesmek için ayrı süreçte okuma gerekiyor.
- Denetim kaydının hash zinciri, veritabanını baştan yazabilen birine karşı
  ancak son özet dışarıda saklanırsa koruma sağlar.

## 8.4 Sonuçlara bağlı sınırlılıklar

<!-- Boş: sonuçlar geldikten sonra yazılacak. -->
