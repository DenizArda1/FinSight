# FinSight — birleşik düzeltme ve tamamlama planı

**6 Kasım güncellemesi:** Temel + Hedef kod gereksinimlerinin güncel eşlemesi
[kod tamamlama raporunda](code_completion_20261106.md). A07, A08, A11–A13 için
kod tamamlandı; A06 maliyet kayıtları, B1, puanlama, karşılaştırma tablosu ve
izole injection araçları eklendi. A05/A09/A10'un kalite ve güvenlik sonuçları
son değerlendirme aşamasında ölçülecek. A14'ün yayın/deploy teslimleri açık.
Aşağıdaki tablolar 31 Ekim deneyinin tarihsel kaydıdır.

Başlangıç: 31 Ekim 2026. Bu belge, aşağıdaki iki çalışmanın **tek ilerleme
listesidir**; önceki belgeler kanıt ve geçmiş sonuç kaydı olarak korunur:

- [Denetim](project_audit_20261030.md)
- [Dış araştırma ve önerilen deney](writer_critic_research_20261031.md)

Ana kapsam kaynağı kullanıcının proje PDF'sidir. Yerel Qwen/BGE-M3,
Writer/Critic rolleri, kaynaklı sayılar, iki revizyon sınırı ve yatırım tavsiyesi
sınırı korunur. Yeni NLI/agent/framework/model eklemek bu planın parçası değildir.

## Öncelik, iş ve kapanış koşulu

| Sıra | Denetim maddesi | Yapılacak iş | Kapanış kanıtı | Durum |
|---|---|---|---|---|
| 1 | A05 | Tam cevap revizyonu ile yalnız hatalı paragraf revizyonunu aynı ilk taslak ve kanıtta karşılaştır | İlk taslak ve her revizyon ayrı incelenir; yanlış kabul, yanlış ret, cevap bozulması, süre ve token raporlanır | İlk karşılaştırma tamamlandı; semantik sorun açık, hedefli yol varsayılan yapılmadı |
| 2 | A09 | Türkçe/İngilizce ve farklı şirketlerle kontrol setini genişlet; doğru/yanlış iddia çiftleri ve kaynaklı beklenen sonuçlar ekle | Model kararı bağımsız inceleme etiketinden ayrı; biçim/bağlantı hatası doğru ret sayılmaz | Dört kısa kontrol + MSFT/NVDA kayıtlı taslakları ölçüldü; geniş benchmark açık |
| 3 | A10 | Beş yatırım tavsiyesi isteği; doğrudan ve kopya indekste dolaylı injection testleri | Güncel MCP yolunda sonuç tablosu ve kaynak izleri | Bekliyor |
| 4 | A12 + A11 | 10-K/A metin güncelleme/seçim politikası; düzeltme açıklamasını kaynaklara taşı | Eski metin ile düzeltilmiş dosyanın karışmadığı test; kullanıcıya açık provenance | Bekliyor; tag sunumu önceki turda düzeltildi |
| 5 | A13 | Embedding model/digest kimliğini indeks metadata'sıyla eşleştir | Uyumsuz modelle arama reddedilir; mevcut indeks için açık geçiş yolu | Bekliyor |
| 6 | A07 | compare_companies aracını mevcut hesaplama fonksiyonları üzerinden sun | Doğrudan/MCP eşdeğerliği, birim/dönem ve eksik veri testleri | Bekliyor |
| 7 | A08 | BM25 + dense aramayı RRF ile birleştir | Sabit sorularda kaynak bulma karşılaştırması; şirket/yıl/bölüm filtreleri korunur | Bekliyor |
| 8 | A06 + A09 + A14 | B0/B1/final kalite-süre-token karşılaştırması, insan incelemesi ve teslim belgeleri | Sonuç tablosu, örnek sorular, README ve yayın/deploy teslimi | Bekliyor; multi-agent çalışma kayıtları mevcut |

A01–A04 kapalıdır; ilgili regresyon testleri korunur. A06'nın uygulama çalışma
kaydı kısmı kapalı, bütün baseline'ların gözlemlenebilirliği kısmı açıktır.
Finansal verinin bulunmaması sıfırla veya LLM tahminiyle tamamlanacak bir kod
hatası sayılmaz. Yeni hesap eklemek ayrı metrik sözleşmesi gerektirir.

## İlk deneyde tamamlanan kod eksikleri

- `src/agents/revisions.py`: numaralı paragraf sözleşmesi, hedef ve patch şeması;
  yalnız seçili paragrafları değiştiren birleştirme. Diğer metin, boş satırlar,
  `kind` ve `facts` korunur. Tekrarlı/bilinmeyen hedefler ve boş patch reddedilir.
- `src/agents/critic.py`: isteğe bağlı, mevcut tek çağrıda `repair_targets` üretimi;
  onayla çelişen hedef listesi hata olur. Üretim varsayılanı değiştirilmedi.
- `src/agents/writer.py`: hedefli patch çıktısını önceki composition ile birleştirir;
  birleşik cevap aynı schema ve deterministik kaynak kontrollerinden geçer.
- `eval/diagnostics/run_revision_comparison.py`: sabit ilk taslaktan iki yöntem,
  kanıt/code hash'leri, ara kayıtlar, token/süre ve bağımsız `review` alanı.
- `tests/test_revisions.py`: korunması gereken metin, patch sınırı, kaynak
  kontrollerinin atlanamaması ve onay/onarım çelişkisi testleri.
- `src/tools/financial_metrics.py`: `get_company_facts` sonucuna mevcut
  `metrics.yaml` tanımı eklendi. Writer/Critic aynı açıklama, birim, taxonomy ve
  etiket sözleşmesini görür. Sayılar ve seçim kuralları değişmedi. Bu eksik,
  Critic'in ayrı gider kalemleri açıklamasını reddettiği kontrolde saptandı.
- `eval/diagnostics/run_revision_controls.py`: iki doğru/yanlış iddia çifti,
  kaynak kanıtı ve modele gönderilmeyen beklenen kararlar. Doğru/yanlış kabul,
  ret ve teknik hata ayrı sayılır; model hata verirse doğru ret sayılmaz.

Çalıştırma:

```sh
.venv/bin/python -m eval.diagnostics.run_revision_comparison --validate-only
.venv/bin/python -m eval.diagnostics.run_revision_comparison
.venv/bin/python -m eval.diagnostics.run_revision_controls
.venv/bin/python -m eval.diagnostics.run_revision_comparison --case msft_mixed_tr --max-revisions 1 --fixed-feedback
```

Bu karşılaştırma yeni bir MCP sorgusu değildir; geçmiş başarılı araç çağrılarının
kaydedilmiş kanıtlarını kullanır. İlk taslak üretimi sabittir. Kontrolün hedef
bulma şeması ve revizyon çıktısı birlikte değiştiğinden sonuç, tek başına patch
birleştirme algoritmasının etkisi olarak yorumlanmaz. İki küçük geliştirme örneği
genel doğruluk oranı veya bağımsız test kümesi değildir.

## Karar kuralı

Yeni yol daha çok cevap veriyor diye üretime alınmaz. Doğru cevapların kabulünü,
yanlış cevapların reddini ve korunması gereken paragrafları birlikte incele.
Hatalı iddia kabulü sürüyorsa A05 açık kalır. Hedefli revizyon fayda sağlamazsa
UI varsayılanını değiştirme; sonucu başarısız/sonuçsuz deney olarak kaydet.
Modelin hata yapmasını yeni prompt koşullarıyla süresiz kovalamak yerine ölçümü
ve kalan engeli açıkça raporla.

## 31 Ekim ilk deney sonucu

Model üretim ayarlarında `qwen3:8b`, `think=false`. Yeni model/API yok.

| Kontrol | Tam revizyon / mevcut Critic | Paragraf revizyonu / hedef belirleyen Critic | İnceleme |
|---|---|---|---|
| MSFT kayıtlı ilk taslak | İlk taslak onaylandı | İlk taslak onaylandı | İkisi de doların değer kazanması ve iş gücü zorlukları gibi desteklenmeyen iddiaları kaçırdı; revizyon başlamadı |
| NVDA kayıtlı ilk taslak | İki revizyon sonrası ret | İlk taslak onaylandı | Kaynak anlamı/atıf sorunları kaldı; mevcut Critic doğru ifadeleri de yanlış reddetti |
| Dört kısa doğru/yanlış kontrol | 3 doğru karar, 1 yanlış ret, 0 teknik hata | 3 doğru karar, 1 yanlış ret, 0 teknik hata | Desteklenen Türkçe FX açıklaması iki biçimde de reddedildi; bu set genel doğruluk oranı değildir |
| Kaynakla önceden belirlenmiş FX hatası | Writer hatayı düzeltti; Critic reddetti | Writer hatayı düzeltti, ilk paragraf tam korundu; Critic reddetti | Tam revizyon da bu örnekte ilk paragrafı korudu. Hedefli yöntemin kalite üstünlüğü gösterilmedi |

Son kontrol **yapay olarak hazırlanmış** iki paragraflık bir örnektir. Başlangıç
geri bildirimi kaynak incelemesinden verilmiştir; otomatik Critic başarısı olarak
sayılmaz. Tam yöntem 53,8 sn ve 13.028/474 giriş/çıkış token; hedefli yöntem
59,6 sn ve 13.676/483 token kullandı. Bu tek ölçümden genel hız sonucu çıkarılamaz.

Ara kayıtlar:

- `../results/revision_comparison_20261031T091939_b241de99.json`
- `../results/revision_controls_20261031T092207_3f0b4fb9.json`
- `../results/revision_comparison_20261031T092340_e24f75a3.json`

İlk başlatma denemesinde Ollama kapalıydı; bağlantı hataları
`revision_comparison_20261031T091919_5ed20797.json` içinde saklandı ve model
kalitesi hesabına alınmadı. Ardından mevcut yerel Ollama servisi başlatıldı.

**Karar:** Paragraf birleştirme kodu çalışıyor, fakat Critic'in yanlış onay/ret
sorunu çözülmedi. Deney yolu üretimin varsayılanı yapılmadı. Eklediğimiz metrik
tanımı aktarımı, somut sözleşme eksikliğini kapatır; tek başına semantik güvenilirlik
iddiası değildir.

## Güncel kodla gerçek MCP sonucu ve kapanış

`../results/revision_live_mcp_20261031T092647_36283ce0.json`: aynı Microsoft
sorusu yeniden Planner → specialist → MCP → Writer → Critic akışından geçti.
Üç finansal tool çıktısında yeni metrik tanımları mevcut; veriler ve rapor
kaynakları getirildi. İki revizyon sonunda cevap yine verilmedi.

İlk Writer taslağı hem alan referansı hem ham sayısal tutar yazdığı için
deterministik kontrolde reddedildi; sonraki taslaklarda bu biçim hatası düzeldi.
Son taslak tek ve tekrarlı paragraftı, eldeki kaynakta bulunan gerçekleşmiş FX
etkisini atladı ve kaynakta doğrudan kurulmayan bir risk-yönetimi sonucu ekledi.
Critic ayrıca Türkçedeki “olumsuz etkileyebilir” olasılık ifadesini gerçekleşmiş
zarar gibi yorumlayarak yanlış gerekçe sundu. Bu sonuç başarılı sayılmadı.

- **461 test geçti.** Yeni testler paragraf koruması, patch sınırları, kaynak
  kontrolleri, çelişkili Critic çıktısı, boş kaynak şeması ve eval hata sayımını kapsar.
- Kayıtlı iki karşılaştırma vakasının kaynak/schema ön kontrolü geçti.
- Mevcut 26 soruluk eval dosyasının yapısal kontrolü geçti; genel kalite skoru değildir.
- `git diff --check` temiz.
- Üretim Writer/Critic varsayılanı tam revizyon olarak kaldı. Paragraf yolu yalnız
  deney aracından kullanılıyor; yeni model veya NLI eklenmedi.

**Bu turun kapanışı:** birleşik plan, hedefli revizyon deneyi, kısa kontroller ve
ortaya çıkan metrik tanımı aktarım eksiği tamamlandı. **A05 kapanmadı; diğer
kod/kapsam maddeleri tablodaki durumlarıyla açıktır.** Bir sonraki iş, A09'daki
kontrol kümesini ve bağımsız değerlendirmeyi genişletmek; aynı Microsoft sorusuna
süresiz prompt eklemek veya bu başarısız deneyi varsayılan yapmak değildir.
