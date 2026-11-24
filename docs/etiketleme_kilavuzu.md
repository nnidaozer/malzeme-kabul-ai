# Etiketleme kılavuzu

Doğru cevaba (gold) neyin girdiğini tanımlar. Taslağı hazırlayan her model ve
kişi aynı kapsamla çalışsın diye yazıldı. Bağımsız etiketleme istemi
(`docs/bagimsiz_etiketleme_istemi.md`) bu kuralları modele aynen verir.

Durum: K1 ve K2'yi Nida belirledi. K3–K7'yi Claude önerdi, Nida 24 Kasım
2026'da onayladı.

## Kurallar

**K1. Şart olan ve doğru cevaba girenler (`testler`).** Standardın şart
bölümündeki (genellikle 3.x) şu ifadeler şarttır:
- sayısal sınırı olan testler (`sayisal`),
- geçti/kaldı kriterleri (`gecti_kaldi`), ör. "shall be compatible with",
  "shall permit", "shall meet all requirements",
- yasaklar, ör. "shall be prohibited", "shall not contain" (`metinsel`),
- sözel kabul kriterleri, ör. "shall not exhibit blistering" (`metinsel`).

**K2. Ürün tanımları (doğru cevaba girmez).** Tip, sınıf ve kompozisyon
tanımları şart değildir. Örnek: "X içeren astarlar sınıf Y olarak adlandırılır".
Bunlar ayrı bir "ürün tanımı" alanına girer: `KabulDokumani.urun_tanimi`
(`tipler`, `siniflar`, `kompozisyonlar`; bkz. docs/mimari.md). Bu alan şartlar
gibi F1'e girmez. Bir şartın yalnız bazı tip/sınıflar için geçerli olduğu
(ör. "Chromium content (class N only)") şartın `uygulanabilirlik` alanına
yazılır (`["Class N"]`).

**K2a. Yönü belirsiz sınırlar.** Metinden "en az" mı "tam" mı olduğu
anlaşılmayan sayısal sınırlarda (ör. MIL-PRF-23377K 3.11) okunan değer
yazılır ve `sinir.yon` alanına `"belirsiz"` konur. Karar motoru bu şartlara
karar vermez, insan incelemesine gönderir.

**K3. Bir kayıt, bir kriter.**
- Ayrı cümlelerde, ayrı ayrı gözlenen ya da ölçülen kriterler ayrı kayıttır.
- Aynı cümlede "or", "nor" ya da "and" ile sayılan kusurlar tek kayıttır (ör.
  "shall not become deformed or the lid shall not become unsealed").
- Aynı kriter farklı numunelere ya da farklı ortamlara ayrı uygulanıyorsa
  (ör. iki farklı test sıvısı, iki ayrı panel) her biri ayrı kayıttır.

**K4. Başarısızlık tanımı ayrı kayıt değildir.** "X constitutes failure" gibi
bir kriteri açıklayan cümle, o kriterin `orijinal_metin` alanına eklenir.

**K5. Depolama ve kullanım koşulları (`kosullar`).** Bir koşul ancak ölçülebilir
bir sınır taşıyorsa (süre, sıcaklık, oran, nem) ya da açık bir yasak ise
girer. Uygulama talimatının ölçülemeyen adımları (ör. "ekipmanı temizle",
"bileşenleri sırayla ekle") girmez. Testte zaten kayıtlı bir sınır koşul olarak
tekrar yazılmaz.

**K6. Bilgi bölümü girmez.** Standardın "Notes" bölümü (genellikle 6.x)
zorunlu değildir; oradaki öneri ve açıklamalar doğru cevaba girmez.

**K7. Muayene ve örnekleme kuralları test değildir.** Parti kabulü, örnekleme
planı ya da "there shall be no failures" gibi muayene sonucu kuralları test
kaydı olmaz. Test panelleri (`numune_hazirlama`) ise doğru cevaptaki bir testte
kullanılıyorsa girer.

## Uygulama örneği

MIL-PRF-23377K'de Codex'in fazladan çıkardığı 41 kaydın bu kurallara göre
sınıflandırması: `/mnt/project-files/codex_23377K/kontrol_listesi.md` (depoda
değil).
