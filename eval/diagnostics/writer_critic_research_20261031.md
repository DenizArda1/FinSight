# Writer–Critic: dış araştırma ve FinSight için karar notu

Bu önerilerin uygulama sırası ve sonuçları: [Birleşik uygulama planı](implementation_plan_20261031.md).

Tarih: 31 Ekim 2026. Bu çalışma kaynak incelemesidir; uygulama kodu, model
ayarları veya veri değiştirilmedi. Dış projeler yerelde çalıştırılmadı ve başarı
iddiaları bağımsız olarak yeniden ölçülmedi.

## Birincil kaynaklardan bulgular

1. [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot): belgelenen tasarım
   hesaplamayı deterministik kodda, açıklamayı LLM'de tutuyor. Bizde bu ayrım zaten
   mevcut. Daha büyük mimarisini, değerleme/tavsiye kapsamını taşımak gerekmiyor.
2. [Mish926/finsight](https://github.com/Mish926/finsight): bizim projeden ayrı,
   aynı adlı portföy projesi. Critic sentezden önce bağlam yeterliliğine bakıyor;
   sonrasında sayılar tabloyla kontrol ediliyor. Yazımda 70B, Planner/Critic'te
   8B kullanıldığını belgeliyor. Kendi başarı sinyalinin bağımsız doğruluk
   ölçüsü olmadığını da belirtiyor. Bu, Qwen 8B ile aynı koşullarda başarı kanıtı
   değildir. Atıf bulunması veya temkinli dil kullanılmaması doğruluk garantisi
   sayılmamalı; bu güven puanlama yaklaşımını aktarmayı önermiyoruz.
3. [CRITIC, ICLR 2024](https://arxiv.org/abs/2305.11738): düzeltme geri bildirimi
   araçlarla yapılan kontrole dayanıyor. Bizde araç kanıtı var, fakat sonraki
   revizyonda aynı kanıtın serbest metinle yorumlanması yine hata üretebiliyor.
4. [RARR, ACL 2023](https://arxiv.org/abs/2210.08726) ve
   [yazarların uygulaması](https://github.com/anthonywchen/RARR): araştırılan
   kanıta göre desteklenmeyen içeriği düzenlerken özgün cevabı mümkün olduğunca
   koruma yaklaşımı. Bize uygun fikir, tüm cevabı tekrar üretmek yerine hatalı
   bölümü hedeflemek. Eski API/model kurulumunu kopyalamak gerekmiyor.
5. [TACL 2024 öz-düzeltme incelemesi](https://arxiv.org/abs/2406.01297): güvenilir
   dış geri bildirim ile yalnız modelin kendi değerlendirmesine dayalı düzeltmeyi
   ayırıyor. FinSight kaynak aldığı için tamamen içsel öz-düzeltme örneği değildir;
   çalışma bizim Qwen akışının başarısızlığını tek başına kanıtlamaz.

## Mevcut kod ve geçmiş deneylerle karşılaştırma

- `src/agents/critic.py`: sayılar/kaynak alanları önce kodla doğrulanıyor. Sonra
  anlam, dil ve kapsam için tek LLM kararı alınıyor.
- `src/llm/prompts.py`: Critic zaten atıf yapılan kaynakları görüyor ve somut hata
  açıklaması isteniyor. Bunları yeni çözüm olarak tekrar önermek yanlış olur.
- Revizyon sözleşmesi genel `issues` ve önceki composition üzerinden ilerliyor;
  hatalı paragrafı değiştirip diğer paragrafları koruma zorunluluğu yok.
- 24 Ekim'deki alıntı/iddia doğrulaması deneyi yanlış ret ve biçim hataları üretti.
  Kaynakta alıntının bulunması anlamsal desteği kanıtlamadı. Aynı ek kontrol
  katmanını geri getirmeyi önermiyoruz.
- 30 Ekim'de sınırlı kaynak ve thinking denemeleri de semantik sorunu kapatmadı.
  Birkaç başarılı kısa örnek uzun cevabın doğruluğu için yeterli değil.

## Önerilen sınırlı deney — henüz uygulanmadı

Mevcut Writer/Critic rollerini, deterministik hesapları ve iki revizyon sınırını
koru. NLI, yeni agent veya sürekli ek LLM kontrolü ekleme.

1. Aynı kaydedilmiş kanıtla mevcut akışın ilk taslağını ve her revizyonunu ayrı
   değerlendir. Doğru cevabın revizyonda bozulması, yanlış kabul ve yanlış ret
   ayrı sayılsın. Küçük Türkçe/İngilizce kontrol kümesinde Microsoft dışı örnekler
   de bulunsun; beklenen kararlar model prompt'una verilmesin.
2. Tek değişken olarak revizyonu hedefle: Critic mevcut çağrısında hata konumunu,
   ilgili kaynak kimliğini ve sorunu açıkça belirtir; Writer yalnız işaretlenen
   paragrafı düzeltir. Değişmeyen metin program tarafından korunur; son birleşik
   taslak mevcut kontrollerden geçer. Bu yaklaşım yanlış Critic kararını çözmez,
   doğru bölümlerin gereksiz yere bozulmasını azaltmayı amaçlar.
3. İlk taslak da kötü ise ayrı deneyde Writer'ın bağlamını ilgili, bütünlüğü
   korunmuş kanıt parçalarıyla sadeleştir. Bu bir başka genel kısaltma turu değil;
   görevle ilgisiz metnin etkisini sabit kanıt ve aynı sorularla ölçme deneyi olsun.
   Olumsuzlama, özne ve dönem bağlamını koparan kesmeler yapılmasın.

Başarı: yalnız daha çok cevap yayımlanması değil; doğru cevapların kabulü artarken
yanlış iddiaların kabulünün artmaması, istenen kapsam ve akıcılığın korunması.
İyileşme yoksa deney geri alınmalı; aynı soruya yeni prompt eklemeye devam
edilmemeli. Daha güçlü model ancak ayrı ve kullanıcı tarafından yetkilendirilmiş
karşılaştırma olur; bu araştırmada model değiştirilmedi.

Önerilen değişiklikler araştırmadan çıkarılan mühendislik hipotezleridir.
Bu kaynaklar Qwen 8B'nin bizim Türkçe finansal anlatımımızı güvenilir biçimde
üreteceğini veya bu küçük deneyin sorunu kesin çözeceğini göstermiyor.
