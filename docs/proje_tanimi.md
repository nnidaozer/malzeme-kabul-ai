# Proje Tanımı

Havacılıkta kullanılan kimyasal malzemeler (astar, boya, sızdırmazlık macunu, yapıştırıcı gibi) teslim alınmadan önce standartlara uygunluk açısından kontrol edilir. Bugün bu iş büyük ölçüde elle yapılıyor: mühendis standardı okuyup bir kabul dokümanı hazırlıyor, sonra tedarikçiden gelen uygunluk sertifikası ve test raporundaki (CoC/TR) her değeri bu dokümanla tek tek karşılaştırıyor. Standartlar periyodik olarak revize edildiği için kabul dokümanlarının güncel tutulması da ayrı bir yük.

Bu proje süreci üç adımda otomatikleştirir:

1. Kabul dokümanı üretimi: Sistem askeri standartları ve varsa müşteri şartnamesini okur. Test sınırlarını, test metotlarını, raf ömrünü, depolama ve kürlenme koşullarını çıkarır ve mühendisin onaylayacağı bir kabul dokümanı üretir. İki kaynak çakışırsa daha sıkı şart alınır.
2. Çapraz kontrol: Tedarikçinin CoC/TR belgesi kabul dokümanıyla karşılaştırılır. Her test için "uygun / uygun değil / insan incelemeli" kararı verilir ve dayandığı madde gösterilir.
3. Revizyon takibi: Standardın yeni revizyonu eklendiğinde değişen şartlar bulunur ve etkilenen kabul dokümanları için güncelleme önerilir.

Tasarım ilkeleri: Belgeyi yerel bir dil modeli okur, ancak kabul/red kararını kesin kurallar verir. Sistem emin olmadığı durumlarda kararı insana bırakır. Belgeler gizli olabileceği için sistem internetsiz çalışır. Başarı; alan bazında F1, yanlış kabul oranı ve belge başına süre ile ölçülür.
