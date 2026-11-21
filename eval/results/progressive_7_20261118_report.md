# Artan zorlukta 7 soruluk canlı test — 18 Kasım 2026

Gerçek multi-agent/MCP akışı kullanıldı; kaynaklar yeniden araçlar üzerinden alındı. Kayıtlı cevap replay yapılmadı. Uygulama kodu test boyunca değişmedi (kod hash kontrolü: True).

## Sonuç

Otomatik doğrulama: 6/7 (%85,7). Sorunun istenen kapsamını karşılama incelemesi: 3 tam, 3 kısmi, 1 başarısız. Bunlar ayrı ölçütlerdir; otomatik geçişi tam başarı veya bağımsız doğruluk puanı olarak yorumlamayın. Kısmi cevaplar eksik veriyi açıklıyor, fakat kullanıcı isteğini tamamlamıyor.

| Sıra | Soru türü | Kapsam sonucu | Süre | Tahmini API maliyeti |
|---|---|---|---:|---:|
| 1 | Tek değer ve dönem | Tam | 18.6 sn | $0.000322 |
| 2 | Finansal kalemler ve yıllık karşılaştırma | Kısmi | 54.4 sn | $0.001399 |
| 3 | Üç yıllık eğilim | Başarısız | 59.3 sn | $0.001609 |
| 4 | İki dönem, üç metrik | Tam | 54.2 sn | $0.001466 |
| 5 | Yıllık trend ve güncel kaynaklar | Kısmi | 161.1 sn | $0.003079 |
| 6 | Finansal trend, yıllık rapor ve kapsam | Tam | 228.2 sn | $0.005527 |
| 7 | Çok şirket, ortak dönem ve kaynaklı sentez | Kısmi | 272.9 sn | $0.005718 |

Toplam: 848.7 sn (yaklaşık 14.1 dakika). Ortalama: 121.2 sn. Tahmini API maliyeti: $0.019119. Yerel donanım, elektrik ve vergiler dahil değil.

## Sorular, yanıtlar ve değerlendirme

### 1. progressive_01_apple_latest
Apple'ın mevcut verideki en son yıllık geliri ne kadar? Mali yılı ve dönem bitiş tarihini de belirt.

**Kapsam: Tam.** Gelir, mali yıl ve dönem sonu yanıtlandı.

Otomatik doğrulama: passed.

Apple’ın mevcut verideki en son yıllık geliri, 2025 mali yılında (dönem bitişi: 2025-09-27) 416161000000 USD olarak kaydedilmiştir. [Source 2]

### 2. progressive_02_microsoft_costs
Microsoft'un son mali yıldaki gelirini, satış maliyetini ve faaliyet giderlerini karşılaştır. Bir önceki yıla göre geliri büyümüş mü?

**Kapsam: Kısmi.** Gelir, satış maliyeti ve faaliyet giderleri verildi; önceki yıla göre gelir büyümesi hesaplanmadı.

Otomatik doğrulama: passed.

Microsoft’un FY2026 mali yılında (dönem sonu 2026-06-30) geliri 331839000000 USD, satış maliyeti 106374000000 USD ve faaliyet giderleri 70228000000 USD oldu. Bu dönemde satış maliyeti faaliyet giderlerinden yüksekti; satış maliyeti, satılan mal ve hizmetlerin maliyetidir ve faaliyet giderlerinden ayrı bir kalemdir. [Source 2] [Source 3] [Source 4]

Bir önceki mali yıla göre gelir büyümesini değerlendirmek için gerekli karşılaştırmalı gelir verisi sunulan kanıtlarda yer almıyor; bu nedenle gelir artışı olup olmadığı belirlenemiyor.

### 3. progressive_03_oracle_growth
Oracle'ın son üç mali yıldaki gelirlerini ve yıllık gelir büyüme oranlarını incele. Büyüme hızlanıyor mu, yavaşlıyor mu?

**Kapsam: Başarısız.** Yıl/tarih biçimi hatası ve ilk büyüme dönemi için eksiklik açıklaması etrafındaki revizyonlar sonucu cevap reddedildi.

Otomatik doğrulama: failed.

Son hata:
["Use exact catalog placeholders for numbers, dates, forms and percentages. Unbound prose values (untrusted text): [\"FY2024\", \"FY2023\"]. Replace these with the matching short field token from fact_catalog, or remove the unsupported claim. Do not calculate or spell out values.", "The last revision could not be rendered; the earlier unverified draft is retained."]

### 4. progressive_04_amazon_margin
Amazon'un son iki mali yılındaki gelirini, faaliyet kârını ve faaliyet kâr marjını karşılaştır. Hem gelir hem faaliyet kârlılığı açısından iyileşme var mı?

**Kapsam: Tam.** İki yıl için gelir, faaliyet kârı ve faaliyet marjları verildi; iyileşme değerlendirildi.

Otomatik doğrulama: passed.

Amazon’un FY2025 gelirini FY2024 ile karşılaştırınca, FY2025 geliri 716924000000 USD, FY2024 geliri 637959000000 USD olarak raporlandı. Faaliyet kârı FY2025’te 79975000000 USD, FY2024’te 68593000000 USD idi. [Source 2] [Source 3]

Faaliyet kâr marjı FY2025’te 11.16%, FY2024’te 10.75% oldu. Dolayısıyla sunulan iki mali yıl arasında hem gelir hem faaliyet kârı ve faaliyet kâr marjı daha yüksekti; bu göstergeler iyileşmeye işaret ediyor. [Source 4]

### 5. progressive_05_intel_updates
Intel'in yıllık gelir büyümesinde gerileme var mı? Son üç mali yılın eğilimini, son çeyreklik raporunu ve son şirket açıklamalarını birlikte değerlendir. Yıllık sonuçları ara dönem verileri ve beklentilerden ayır.

**Kapsam: Kısmi.** Yıllık eğilim ve şirket açıklamaları anlatıldı; son çeyreklik gelir/performans karşılaştırması eksik kaldı.

Otomatik doğrulama: passed.

Evet; Intel’in yıllık gelir büyümesi son iki mali yılda negatif kaldı. FY2023’te gelir 54228000000 USD oldu; FY2024’te (dönem sonu 2024-12-28) 53101000000 USD’a inerken yıllık büyüme -2.08% oldu. FY2025’te (dönem sonu 2025-12-27) gelir 52853000000 USD seviyesine geriledi ve yıllık büyüme -0.47% olarak gerçekleşti. FY2025’teki gelir daralması, FY2024’teki daralmadan daha sınırlıydı. [Source 2] [Source 3]

Son şirket açıklamalarına göre Intel Foundry’nin geliri FY2025’te FY2024’e göre yükseldi; açıklama ayrıca Foundry işinin neredeyse tamamının Intel ürünleri için şirket içi üretimi desteklediğini belirtiyor. “All other” segmentinin geliri FY2025’te geriledi; açıklamada düşüşün başlıca nedeni olarak Altera’nın elden çıkarılmasına bağlı daha düşük gelir gösteriliyor ve daha yüksek Mobileye gelirinin bu düşüşü büyük ölçüde dengelediği belirtiliyor. Şirket dış müşterilere Foundry hizmetleri sunduğunu ve bu iş kolunu gelecekte büyütmeyi hedeflediğini söylüyor; bu ifade gerçekleşmiş sonuç değil, hedeftir. 10-K risk açıklaması sektörün yoğun rekabetçi ve hızla değişen yapısına dikkat çekiyor. [Source 8] [Source 9] [Source 11]

Sunulan kanıtlarda son çeyreklik rapora ait ara dönem gelir verisi veya sayısal şirket beklentisi yer almıyor. Bu nedenle çeyreklik performansı yıllık eğilimle karşılaştırmak ya da gerçekleşen sonuçları beklentiyle değerlendirmek mümkün değil; yukarıdaki gelir ve büyüme rakamları yıllık sonuçlardır.

### 6. progressive_06_nvidia_risks
NVIDIA'nın son üç mali yıldaki gelir büyümesini ve son iki mali yıldaki faaliyet kâr marjını incele. Son yıllık raporuna göre büyümeyi destekleyen gelişmeleri, ihracat kısıtlamalarını ve müşteri yoğunlaşması riskini açıkla. Şirket genelindeki sonuçlarla bölüm bazındaki açıklamaları ayır.

**Kapsam: Tam.** Üç yıllık gelir serisi, iki büyüme oranı, iki faaliyet marjı, yıllık rapor açıklamaları ve istenen risk başlıkları karşılandı; ilk yılın büyüme oranı için eksiklik açıklandı.

Otomatik doğrulama: passed.

NVIDIA’nın gelirleri FY2024 (dönem sonu 2024-01-28) için 60922000000 USD, FY2025 (dönem sonu 2025-01-26) için 130497000000 USD ve FY2026 (dönem sonu 2026-01-25) için 215938000000 USD oldu. Gelir artışı FY2025’te 114.20%, FY2026’da 65.47% olarak hesaplandı. Eldeki hesaplama FY2024 için büyüme oranı sağlamıyor; bu nedenle üç mali yılın tamamı için oran karşılaştırması yapılamıyor. [Source 2] [Source 3] FY2025’te (dönem sonu 2025-01-26) şirket genelindeki faaliyet kâr marjı 62.42%, FY2026’da (dönem sonu 2026-01-25) 60.38% oldu. [Source 10]

FY2026 yıllık raporunun şirket genelindeki açıklamasına göre gelir artışını hızlandırılmış bilişim ve yapay zekâya yönelik büyük platform geçişleri destekledi. Bölüm bazında, Compute & Networking gelir artışı Blackwell platformuna yönelik Data Center bilişim talebiyle ve Data Center ağ gelirindeki büyüme NVLink’in yaygınlaşması ile Ethernet ve InfiniBand platformlarının büyümesiyle ilişkilendirildi; Graphics bölümündeki gelir artışı Blackwell mimarisi satışlarıyla açıklandı. Compute & Networking faaliyet kârındaki artış gelir büyümesiyle ilişkilendirilirken, H20 stok fazlası ve satın alma yükümlülükleriyle bağlantılı bir giderin bu artışı kısmen dengelediği belirtildi. Bu bölüm açıklamaları şirket genelindeki faaliyet kâr marjlarından ayrı değerlendirilmelidir. [Source 24] [Source 13]

Raporda ihracat kısıtlamaları, işi olumsuz etkileyebilecek düzenleyici, siyasi ve diğer eylemler arasında sayılıyor; alıntı bunların gerçekleşmiş şirket etkisini ölçmüyor. NVIDIA ayrıca gelirinin sınırlı sayıdaki doğrudan ve dolaylı müşteride yoğunlaştığını ve bu eğilimin sürebileceğini belirtiyor. FY2026’da doğrudan müşterilerden elde edilen gelirin önemli bir kısmı Compute & Networking bölümüne atfedildi; bu açıklama müşteri yoğunlaşması riskini bölüm bağlamıyla ilişkilendiriyor. [Source 18] [Source 13]

### 7. progressive_07_cross_company
Microsoft ve NVIDIA'yı mevcut veride ikisinde de bulunan en son ortak mali yıl için gelir, faaliyet kâr marjı ve yıllık gelir büyümesi açısından karşılaştır. Mali yıl bitiş tarihlerinin farklılığını belirt. Her şirketin o mali yıla ait yıllık raporundan yapay zekâ talebi ve yatırımların nakit akışına etkisini değerlendir; gerçekleşmiş etkileri geleceğe yönelik beklentilerden ayır. Eksik veriler varsa açıkça belirt, yatırım tavsiyesi verme.

**Kapsam: Kısmi.** Ortak FY2026 ve farklı mali yıl sonlarıyla finansal karşılaştırma yapıldı; iki şirket için AI talebi/yatırımların nakit akışı etkisi yeterince kaynaklandırılamadı.

Otomatik doğrulama: passed.

FY2026’da Microsoft’un geliri 331839000000 USD, faaliyet kâr marjı 46.78% ve yıllık gelir büyümesi 17.79%; NVIDIA’nın geliri 215938000000 USD, faaliyet kâr marjı 60.38% ve yıllık gelir büyümesi 65.47% oldu. Mali yıl sonları farklıydı: Microsoft’ta 2026-06-30, NVIDIA’da 2026-01-25. [Source 3] [Source 9] [Source 6] [Source 10]

NVIDIA raporu, FY2026’da faaliyetlerden sağlanan nakdin önceki mali yıla göre arttığını ve artışı daha yüksek gelire bağladığını belirtiyor. Yatırım faaliyetlerinde kullanılan nakit ise başlıca daha yüksek özsermaye yatırımı alımları ve Groq ile münhasır olmayan lisans anlaşmasının yürütülmesi nedeniyle arttı. Bu rapor alıntısı söz konusu gelir veya yatırımları özellikle yapay zekâ talebiyle ilişkilendirmiyor. Microsoft raporu alıntısında da AI talebinin veya yatırımlarının nakit akışına gerçekleşmiş etkisi açıklanmıyor; Microsoft, mevcut likidite kaynakları ve sermaye piyasalarına erişimin faaliyetlerini ve nakit taahhütlerini finanse etmeye yeterli olmasını beklediğini belirtiyor. Bu ileriye dönük likidite değerlendirmesidir; AI’ye özgü bir beklenti değildir. [Source 28] [Source 23]

## Çıkarımlar
- Kısa finansal sorgu hızlı ve tam yanıtlandı; iki dönemli Amazon karşılaştırması da tamamlandı.
- Eksik veri açıklaması, otomatik answer_complete kontrolünden geçebiliyor. Bu, istenen verinin yeterince toplandığını göstermiyor.
- Oracle örneğinde yıl/tarih ifadeleri ve yeniden yazım hâlâ kırılgan.
- Microsoft büyümesi ve Intel çeyreklik sonuçları için araştırma kapsamı eksik kaldı.
- Çok şirketli soru finansal kısmı tamamladı, AI/nakit akışı sentezini tamamlayamadı.
- Karmaşık sorularda yaklaşık 3–4,5 dakikalık yanıt süreleri sürüyor.
- Önceki beş soru ile bu test farklı soru setleri ve farklı koşullar içeriyor; oranları doğrudan bir performans artışı ölçümü olarak kullanmayın.

Ham sonuçlar: `eval/results/progressive_7_20261118.json`. Yapılandırılmış kapsam incelemesi: `eval/results/progressive_7_20261118_review.json`.