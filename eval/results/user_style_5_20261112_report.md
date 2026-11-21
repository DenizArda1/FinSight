# Kullanıcı tarzı beş soruluk canlı test — 12 Kasım 2026

İlk plan 10 soruydu; kullanıcı isteğiyle beş tamamlanmış soruda durduruldu. Altıncı sorunun başlamış planlama işlemi iptal edildi ve değerlendirmeye dahil edilmedi.

Gerçek multi-agent/MCP akışı; kayıtlı cevap replay değil. Mevcut yerel model ve yapılandırılmış Writer/Critic kullanıldı. Test boyunca uygulama kodu değiştirilmedi. Veri indirme/önbellek yenileme serbestti.

| Şirket | Sonuç | Süre | Tahmini API maliyeti |
|---|---|---:|---:|
| INTC | Başarısız | 161.5 sn | $0.002186 |
| MSFT | Geçti | 160.9 sn | $0.002397 |
| AAPL | Başarısız | 212.9 sn | $0.002000 |
| NVDA | Başarısız | 272.2 sn | $0.003637 |
| AMZN | Geçti; kapsam kısmi | 90.0 sn | $0.001541 |

Toplam tamamlanan soru süresi: 897.5 sn. Ortalama: 179.5 sn. Tahmini API maliyeti: $0.011761. Yerel donanım ve vergiler dahil değildir.

Otomatik doğrulama geçişi 2/5 (%40); bu oran bağımsız doğruluk puanı değildir. Amazon karşılaştırması eksik kapsamı açıkça bildirse de tam bir yıllık marj karşılaştırması sunmuyor. Bu küçük test, üretim güvenilirliğini kanıtlamaz; mevcut sonuç canlıya çıkmak için yeterli değildir.

## Sorular ve gözlemler

### INTC
Intel'in büyüme oranlarında bir gerileme var mı? Son gelişmeler ile güncel finansal durumu analiz et

Anlatıdaki 2025’te ifadesi sayısal alan kontrolüne takıldı.

Son doğrulama: {"status": "failed", "supported": false, "issues": ["Use exact catalog placeholders for numbers, dates, forms and percentages. Unbound prose values (untrusted text): [\"2025’te\"]. Replace these with the matching short field token from fact_catalog, or remove the unsupported claim. Do not calculate or spell out values."], "stage": "writer_validation", "deterministic_fields": "failed", "method": "source_fields_and_llm_judge"}

### MSFT
Microsoft'un yıllık gelir gider verilerini ve makro olayların şirkete etkisini açıkla

Gelir/gider ayrımı ve makro etki/risk ayrımı cevapta mevcut.

Son doğrulama: {"supported": true, "issues": [], "evidence_supported": true, "language_matches": true, "answer_complete": true, "status": "passed", "stage": "grounding_and_language", "deterministic_fields": "passed", "method": "source_fields_and_llm_judge"}

Cevap:
Microsoft’un mali yılı 2026, 2026-06-30 tarihinde sona erdi. Bu dönemde gelir 331839000000 USD, satılan mal ve hizmetlerin maliyeti 106374000000 USD, faaliyet giderleri ise 70228000000 USD oldu. Satılan mal ve hizmetlerin maliyeti ile faaliyet giderleri ayrı kalemlerdir; bu veriler tek başına net kârlılığı göstermez. [Source 2] [Source 3] [Source 4]

Microsoft, mali yılda ABD dolarındaki bazı yabancı para birimleri karşısındaki dalgalanmaların raporlanan geliri artırdığını ve uluslararası faaliyetlere ait raporlanan giderler üzerinde önemli bir etkisi olmadığını belirtti. Ayrıca küresel, bölgesel ve yerel ekonomik gelişmeler ile ticaret politikalarındaki değişikliklerin tedarik zinciri zorluklarını, maliyet oynaklığını ve tüketici ile ekonomik belirsizliği artırarak sonuçları olumsuz etkileyebileceğini ifade etti. [Source 15]

### AAPL
Apple'ın son mali yıldaki gelirini, satış maliyetini ve faaliyet giderlerini karşılaştır. Bir önceki yıla göre gelirinde büyüme var mı?

Sayısal soruya eklenen rapor araştırması, zorunlu rapor atfı kontrolünü tetikledi.

Son doğrulama: {"status": "failed", "supported": false, "issues": ["Cite the report explanation in prose using its actual report source IDs: [Source 8], [Source 13], [Source 18], [Source 19], [Source 23]. Financial-record citations cannot support macro events or business-risk claims. Citations on metadata cards alone do not cite the explanation."], "stage": "writer_validation", "deterministic_fields": "failed", "method": "source_fields_and_llm_judge"}

### NVDA
NVIDIA'nın son üç yıllık gelir büyümesini incele. Son yıllık raporuna göre bu büyümeyi destekleyen gelişmeler ve önemli riskler neler?

Yıllık rapor yerine çeyreklik kanıt; bölüm büyümesinden şirket geneline taşınan yorum.

Son doğrulama: {"supported": false, "issues": ["Ayrı çeyreklik rapor alıntısının platform değişimlerini ilgili çeyrekteki genel gelir büyümesinin nedeni olarak sunduğu izlenimi veriliyor; kaynak bunları özellikle Data Center gelirindeki yıllık artışın nedeni olarak belirtiyor."], "evidence_supported": false, "language_matches": true, "answer_complete": true, "status": "failed", "stage": "grounding_and_language", "deterministic_fields": "passed", "method": "source_fields_and_llm_judge"}

### AMZN
Amazon'un son mali yıldaki gelirini ve faaliyet kâr marjını değerlendir. Önceki yıla göre finansal performansı iyileşmiş mi?

Önceki yılın faaliyet marjı getirilmedi; cevap eksikliği açıkça belirtiyor.

Son doğrulama: {"supported": true, "issues": [], "evidence_supported": true, "language_matches": true, "answer_complete": true, "status": "passed", "stage": "grounding_and_language", "deterministic_fields": "passed", "method": "source_fields_and_llm_judge"}

Cevap:
Amazon’un FY2025 mali yılında (dönem sonu: 2025-12-31) geliri 716924000000 USD, faaliyet kârı 79975000000 USD ve faaliyet kâr marjı 11.16% oldu. [Source 2] [Source 4] [Source 7]

Gelir, FY2024 mali yılında (dönem sonu: 2024-12-31) 637959000000 USD iken FY2025 mali yılında 716924000000 USD seviyesine yükseldi; hesaplanan yıllık gelir büyümesi 12.38%. Bu, gelir performansının önceki yıla göre iyileştiğini gösteriyor. Sağlanan kanıtlarda önceki mali yılın faaliyet kâr marjı bulunmadığından marjın yıllık bazda iyileşip iyileşmediği belirlenemiyor. [Source 9] [Source 12] [Source 2]

## Öncelikli sorunlar
1. Sayısal yer tutucu şartı, kaynak destekli doğal tarih ifadelerini hâlâ reddedebiliyor.
2. Planner görevi gereksiz genişletebiliyor; mixed türüne bağlı genel atıf şartı asıl soruyu engelleyebiliyor.
3. Yıllık/çeyreklik kaynak seçimi ve segment/şirket kapsamı ayrımı korunmalı.
4. Karşılaştırmalı sorularda iki dönemin aynı metrikleri toplanmalı.
5. Ortalama yaklaşık üç dakika; doğruluk dışında gecikme de çözülmeli.

Ham sonuç: `eval/results/user_style_10_20261112.json` (dosya adı ilk 10 soruluk plana aittir; içinde 5 sonuç vardır).