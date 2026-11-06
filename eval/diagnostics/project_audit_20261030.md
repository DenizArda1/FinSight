# FinSight — proje raporuna göre denetim

Güncel iş sırası ve deney durumu: [Birleşik uygulama planı](implementation_plan_20261031.md).
Bu belge 30 Ekim denetiminin kanıt kaydıdır; ilerleme birleşik planda tutulur.

Tarih: 30 Ekim 2026. Ana kontrol kaynağı: `01_FinSight_Finans.pdf`, sürüm 1.0,
özellikle s. 7–13. Belge gereksinim kaynağıdır; içerdiği örnek komutlar kendiliğinden
çalıştırılmadı. Mevcut kullanıcı tercihleri: yerel Qwen, BGE-M3, `src.*` importları,
serbest kaynaklı anlatım; NLI veya yeni agent katmanı eklenmeyecek.

## Yöntem ve sınır

İndirme/cache, metrik sözleşmesi ve hesaplar, HTML/bölüm/chunk hazırlama,
embedding/Chroma, retrieval, tool/MCP sözleşmeleri, Planner/specialistler,
Writer/Critic/revizyon, UI/export ve eval kodu incelendi. Yerel veri bütünlüğü
modelden bağımsız kontrol edildi. Birim testleri ile canlı cevap kalitesi ayrı
ölçüldü; testlerin geçmesi, Critic'in anlam hatalarını yakaladığını kanıtlamaz.

## Doğrulanan temel durum

- 4 şirket, her birinde 5 yıllık rapor dönemi; 20 raporda 60 bölüm.
- 29 ham dosya kendi indirme SHA-256 kaydıyla eşleşiyor. Bu kontrol yeni SEC
  doğrulaması veya dosyaların güncel olduğunun kanıtı değildir.
- 109 hazırlanmış metrik kaydı, ham companyfacts içindeki etiket/birim/dönem/
  accession/form/filed/değer ile eşleşiyor.
- 2702 chunk kaynak metindeki offsetleriyle eşleşiyor; Chroma'da eksik veya fazladan
  chunk ID'si yok. Model yeniden eğitilmedi, embedding yeniden oluşturulmadı.
- AMZN gross_profit/operating_expenses ve eski bir MSFT operating_expenses dönemi
  mevcut sözleşmede eksik. Bunlar sıfır veya LLM tahminiyle doldurulmamalı.
- Araçlarda sıkı girdi şeması, MCP'de dönüşüm öncesi doğrulama, yıl/bölüm filtresi,
  hesap tool'ları, yeni dosyaya export sınırı ve kalıcı uyarı mevcut.
- Sayısal ayrıntılar: `project_audit_data_20261030.json`.

## Bulgular ve son durum

| ID | Öncelik | Bulgu / kanıt | Rapor | Durum |
|---|---|---|---|---|
| A01 | Kritik | Writer sayı alanının tam kaynak yolunu yazdığı halde ayrıca aynı kaynak etiketini yazmazsa bütün yanıt reddediliyor. `compose_template`; son readability probe iki kez bu yüzden durdu. Kaynak zaten alan referansından kesin biliniyor. | s.8 sayıların render edilmesi ve kaynak | Düzeltildi: kesin alan referansından paragraf kaynağı otomatik ekleniyor; uydurma alanlar reddediliyor |
| A02 | Kritik | Her Writer girişinde draft temizleniyor; son revizyon biçim hatası verirse önceki okunabilir taslak kayboluyor. `writer.py`, `orchestrator.py`. | s.8 kural 10, kısmi/doğrulanmamış taslak | Düzeltildi: önceki taslak korunuyor; başarısız UI araç değerlerini ve açıkça doğrulanmamış taslağı sunuyor, export açılmıyor |
| A03 | Yüksek | Context bütçesi aynı chunk'ı ham ve genişletilmiş metin olarak iki kez sayıyor/gönderiyor; ilk sorgunun sonuçları sonraki sorgunun üst sonuçlarını dışarıda bırakabiliyor. `verification/evidence.py`, `prompts.py`. | s.12–13 kapsam, kısa bağlam | Düzeltildi: genişletilmiş metin bir kez, sorgulara dönüşümlü bütçe, sadeleştirilmiş katalog; Critic yalnız atıf yapılan kaynakları görüyor |
| A04 | Yüksek | Multi-agent Writer/Critic rapor metnini JSON içinde veriyor; tek-rapor akışındaki kaçışlanmış `<filing_excerpt>` sınırları burada yok. | s.8 kural 6 | Düzeltildi: model kopyasında kaçışlanmış filing_excerpt sınırları; asıl trace değişmiyor |
| A05 | Kritik | Qwen Critic, döviz dalgalanmasını doların değer kazanması diye yorumlayan veya gider atlayan taslağı onaylayabiliyor. 29 Ekim kayıtlı canlı denemelerde kanıtlı. | s.7 Critic; s.13 kolay ikna olan judge | AÇIK: canlı uzun cevapta hem yanlış onay hem yanlış ret tekrarlandı; aşağıdaki deneyler |
| A06 | Yüksek | UI başarısız isteğin ayrıntısını yalnız RAM'de tutuyor; yeniden başlatmada son hatanın kanıtı kayboluyor. Modelden gelen token sayaçları client tarafından atılıyor. | s.9/11 trace + token/gecikme | Multi-agent MCP yolunda düzeltildi: yerel JSON çalışma kaydı ve gerçek token sayaçları; bütün baseline/maliyet karşılaştırması henüz yok |
| A07 | Orta | `compare_metric` mevcut fakat `compare_companies` agent/MCP araç listesinde yok. Karşılaştırma modelin birden çok çağrısına bırakılıyor. | s.7 ve Hedef kapsam | Açık kapsam eksiği; Microsoft tek-şirket sorusunun engeli değil |
| A08 | Orta | Retrieval yalnız dense Chroma araması; BM25 + RRF yok. | s.9 Hedef kapsam | Açık kapsam eksiği |
| A09 | Yüksek | Eval 26 soru içeriyor ama yalnız bir narrative ve bir mixed soru var. B1 naif RAG yok; summary kalite metriklerini değil durum/süreleri sayıyor. `review` alanı otomatik doldurulmuyor. | s.10–11 | Açık değerlendirme eksiği; mevcut sayılar başarı oranı değildir |
| A10 | Yüksek | 5 tavsiye talebi ve indeks kopyasında dolaylı injection koşulunu karşılayan güncel canlı sonuç tablosu yok. Golden set'te 3 out_of_scope, 2 direct injection var. Eski teşhis dosyaları güncel regresyon yerine geçmez. | s.8/11–12 | Açık doğrulama eksiği |
| A11 | Orta | Sayı kaydında XBRL tag ve amendment bilgisi var; üretilen notun kaynak kartında tag ve düzeltme açıklaması tam görünmüyor. | s.8 kural 4/7 | Kısmen düzeltildi: XBRL tag ayrıntı kartına ve kısmi veri tablosuna eklendi; amendment açıklaması halen açık |
| A12 | Orta | RAG hazırlama yalnız orijinal 10-K'ları seçiyor; 10-K/A metni için güncelleme politikası yok. Sayısal seçici ise en son filed değerini kullanıyor. | s.8 düzeltme önceliği | Metin tarafı kapsam sınırı |
| A13 | Orta | Embedding boyutları doğrulanıyor ama koleksiyonun model/digest kimliği çalışma anında zorunlu eşleştirilmiyor. İsim/config disiplinine bağlı. | s.5 aynı embedding modeli | Mevcut config eşleşiyor; gelecekte model değişimi riski |
| A14 | Düşük | B0/B1/final kalite tablosu, bağımsız insan-judge uyumu, 10 örnek sorulu kapsamlı README ve yayın/deploy teslimleri tamamlanmış değil. | s.10–14 | Teslim eksiği; hata düzeltmesini engellememeli |

## Canlı doğrulama ve karşı örnekler

Üretim ayarları değişmedi: `qwen3:8b`, `think=false`, sıcaklık 0,
`num_ctx=16384`, `num_predict=4096`. Yeni model, NLI, cloud veya ek agent eklenmedi.

| Deneme | Yol / kapsam | Sonuç |
|---|---|---|
| MCP sözleşmesi | Gerçek subprocess bağlantısı, MSFT üç finansal kayıt ve Item 1A | Direct/MCP değerleri aynı; bool/string years ve ekstra parametre reddedildi |
| Microsoft sorusu | Gerçek MCP + Planner/specialistler + Writer/Critic | Üç taslak biçim kontrolünü geçti; iki revizyon sonunda içerik nedeniyle yanıt verilmedi |
| Thinking deneyi | Aynı 8B, geçici think=true, kaydedilmiş gerçek MCP kanıtı | Critic onayladı fakat “U.S. tariffs” ifadesi “ABD’ye karşı tarifeler” diye değişti. Başarılı sayılmadı, üretime alınmadı |
| Kısa Critic kontrolü | Dört doğru/yanlış FX ve tarife örneği | 4/4 beklenen genel karar; uzun cevap başarısını veya rapordaki 10 insan örnekli kalibrasyonu kanıtlamıyor |
| Yalnız atıflı kaynakla kontrol | Thinking deneyi taslağının tekrar incelenmesi | Yanlış tarife yorumunu yine onayladı |
| Son replay | Üretim ayarı, sadeleştirilmiş prompt, gerçek MCP'den kaydedilmiş aynı kanıt | Üç taslak üretildi, iki revizyon sonunda yine reddedildi. Yeni tam MCP koşusu değildir |

**Açık kök sorun:** Writer kaynaktaki potansiyel riskleri gerçekleşmiş olaya
çevirebiliyor veya kaynak dışı sonuç ekliyor. Critic de doğru ifadeyi reddedip
yanlış ifadeyi onaylayabiliyor. Örneğin kaynak FY2026'da dövizin bildirilen geliri
artırdığını açıkça söylerken son replay'deki Critic bunu yalnızca gelecekteki risk
olarak yorumladı. Bazı Writer taslakları maliyetleri “gelirin parçaları” diye
niteledi ve kaynak dışı AI gelir beklentisi ekledi. Bunlar yalnız stil sorunu değil.
Kaynak kontrolünü kapatmak veya model onayını tek başına başarı saymak çözüm değil.

**Bağlam yükü:** Gerçek koşuda RAG specialist'in son girdisi 15.693 token,
konfigürasyon sınırı 16.384; Writer'ın ilk girdisi 12.052 token oldu.
Bu ölçüm, otomatik truncation yaşandığının kanıtı değildir. Tekrarlı katalog ve
rapor metni azaltıldı; tüm akış için token bazlı bütçe henüz uygulanmış değil.

Kanıt dosyaları:

- `project_audit_data_20261030.json`: veri/index bütünlüğü.
- `project_audit_mcp_20261030.json`: gerçek MCP sözleşme kontrolü.
- `../results/project_audit_microsoft_20261030.json`: tam uygulama koşusu.
- `../results/project_audit_reasoning_20261030.json`: geçici thinking deneyi.
- `../results/project_audit_critic_calibration_20261030.json`: dört kısa kontrol.
- `../results/project_audit_focused_review_20261030.json`: atıflı kaynak deneyi.
- `../results/project_audit_final_replay_20261030.json`: son üretim ayarlı replay.

## Teslim edilen düzeltmelerin sınırı

Veri katmanı yeniden yazılmadı. Sayıların alan ve kaynak bağlama kontrolleri
korundu; gereksiz ikinci etiket zorunluluğu kaldırıldı. Önceki taslak ve araçlardan
alınan finansal değerler başarısızlıkta erişilebilir; bunlar doğrulanmış bir
araştırma notu diye sunulmaz ve dışa aktarılamaz. İki revizyon sınırı korundu.
Her UI/MCP multi-agent isteğinin soru, sonuç, araç/model adımları ve mevcut token
sayaçları `logs/runs/` altında kaydediliyor. Bu kayıtlar yereldir, soruları ve
rapor parçalarını içerir; config kimlik bilgileri kopyalanmaz ve klasör gitignore'dadır.

**Microsoft sorusu için güvenilir, akıcı ve doğrulanmış 2–3 paragraflık cevap
henüz elde edilmedi.** Bu nedenle A05 kapanmadı; test başarısı ürün başarısı diye
raporlanmıyor. İleride A05 için yapılacak değişiklik bu aynı olumlu/olumsuz
örneklerle ve insan incelemesiyle kıyaslanmalı; yeni doğrulama katmanları veya
hedef kapsamdaki bağımsız eksikleri eklemek bu sorunun çözüldüğünü göstermez.

## Son teknik kontroller

- `.venv/bin/python -m unittest discover -s tests`: **453 test geçti**.
  Model çağrıları mock'tur; kaynak bağlama, taslağın korunması, filtreler,
  tanı kayıtları, başarısız UI'da gerçek araç değerleri ve export engeli kapsanır.
- `.venv/bin/python -m eval.run_eval --validate-only`: **26 vaka yapısal olarak geçerli**;
  beklenen cevaplar puanlanmadı, model çağrılmadı.
- `.venv/bin/python -m pip check`: bağımlılık uyumsuzluğu bulunmadı.
- Streamlit `http://127.0.0.1:8501` üzerinde başlatıldı; sağlık uç noktası başarılı.
- Son tag/kısmi tablo değişiklikleri birim/UI testleriyle doğrulandı; bu son
  sunum değişikliğinden sonra yeni bir tam model/MCP cevabı üretilmedi.
