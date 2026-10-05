# اتفاق جداول التحليل

هذا الاتفاق بين حسابات التحليل (`labor_market/analyze.py`) والرسوم. أي تغيير في الأعمدة أو المعاني يتفق عليه صراحة قبل التنفيذ، ولا يغيّره طرف منفردًا.

## الدالة

```python
from labor_market.analyze import build_analysis
tables = build_analysis(workers, source_totals)
```

- المدخلات: `pandas.DataFrame` بمخطط مخرجات التجهيز:
  - `workers`: `year, quarter, region, economic_activity, workers, source_file`.
  - `source_totals`: `year, quarter, total_type, name, value, source_file`، حيث `total_type` أحد `region` أو `economic_activity` أو `grand_total` (واسم الإجمالي العام `Grand Total`).
- المخرج: قاموس بأربعة مفاتيح هي `national` و`regions` و`activities` و`region_activities`، قيمة كل منها `DataFrame`.
- لا تعدّل الدالة المدخلات.
- قراءة `data/processed` بدقة: `pd.read_csv(..., keep_default_na=False, na_values=[""], dtype={"workers": "Int64"})` (والعمود `value` في الإجماليات `Int64`)؛ الدالة `labor_market.analyze.read_processed()` تفعل ذلك.

## الجداول

| الجدول | الأعمدة بالترتيب | السجلات |
|---|---|---|
| `national` | `year, workers_q1, workers_q2, change, change_rate` | 1 |
| `regions` | `year, region, workers_q1, workers_q2, change, change_rate, share_q1, share_q2` | 13 |
| `activities` | `year, economic_activity, workers_q1, workers_q2, change, change_rate, share_q1, share_q2, is_pending` | 20 |
| `region_activities` | `year, region, economic_activity, workers_q1, workers_q2, change, change_rate, share_q1, share_q2, is_pending` | 260 |

### الأنواع

- `year`: عدد صحيح. `workers_q1` و`workers_q2` و`change`: `Int64` (يقبل المفقود `<NA>`).
- `change_rate` و`share_q1` و`share_q2`: `float64`، والمفقود `NaN`. هي **كسور** وليست أرقامًا مضروبة في 100 (0.003 تعني 0.3%).
- `is_pending`: منطقية؛ تساوي `True` للتصنيف «تحت المعالجة» فقط.
- ترتيب السجلات يتبع ترتيب المصدر ولا يُعدّ جزءًا من الاتفاق؛ تتعامل الرسوم مع الأعمدة بأسمائها وتُرتّب بنفسها.

## قواعد الحساب

- `national` من `grand_total` في `source_totals`؛ و`regions` و`activities` من إجماليات `region` و`economic_activity` في `source_totals`؛ و`region_activities` من `workers`.
- `workers_q1` و`workers_q2` قيمة الفترة، و`change = workers_q2 - workers_q1`.
- `change_rate = change / workers_q1`؛ غير متاحة (`NaN`) عند فقد أي قيمة أو عندما `workers_q1 = 0`.
- حصص `regions` و`activities`: `workers_qN ÷ الإجمالي الوطني للفترة N`.
- حصص `region_activities`: `workers_qN ÷ إجمالي المنطقة للفترة N` (من `source_totals`).
- المقامات تشمل «تحت المعالجة». الحصة غير متاحة عند فقد البسط أو المقام أو عندما يكون المقام صفرًا.
- المفقودات تبقى مفقودة ولا تتحول إلى صفر في أي جدول.
- لا تُجمع أعداد الربعين، ولا تُحسب اتجاهات أبعد من مقارنة الربعين.
- «تحت المعالجة» صف عادي في `activities` و`region_activities` مع `is_pending = True`، وتفسيره غير محسوم؛ استبعاده من ترتيب الأنشطة المسماة قرار عرض تتخذه الرسوم مع توضيحه.

## ما ترفضه الدالة (`AnalysisError` برسالة مفهومة)

- أعمدة ناقصة: كل أعمدة المخطط الموثق للمدخلين مطلوبة، ومنها `source_file` في `workers` و`source_totals`. الأعمدة الإضافية تُتجاهل.
- `year` و`quarter`: تُرفض القيم الكسرية (مثل الربع 1.9 أو السنة 2026.1)، وغير المنتهية (`inf`)، والمفقودة، والمنطقية، وغير الرقمية. يُتحقق من أنها أعداد صحيحة **قبل** أي تحويل، فلا يُقطع كسر ولا تُغيَّر قيمة بصمت. الأعداد الصحيحة المخزنة كـ`float` (مثل 2026.0) مقبولة.
- `workers`/`value`: تُرفض القيم الكسرية وغير المنتهية وغير الرقمية والمنطقية والسالبة. القيمة المفقودة مسموحة وتبقى مفقودة.
- أسماء المفاتيح: `region` و`economic_activity` في `workers`، و`total_type` و`name` في `source_totals`، تُرفض إن كانت مفقودة (`None`/`NaN`) أو فارغة أو مسافات فقط. تذكر الرسالة رقم الصف بترتيبه في الجدول، ويحدث الرفض قبل الربط والحساب؛ لا تُملأ الأسماء ولا تُحذف سجلاتها.
- أرباع غير `{1, 2}`، أو أكثر من سنة.
- مفاتيح مكررة في `workers` أو `source_totals`.
- ربط غير مكتمل: اختلاف المناطق أو التصنيفات بين الربعين، أو نقص في تركيبات المنطقة والتصنيف، أو عدم تطابق إجماليات المصدر مع أسماء `workers`، أو غياب الإجمالي العام.

## التشغيل والمخرجات

```powershell
.venv\Scripts\python.exe -m labor_market.analyze
```

يقرأ `data/processed` ويكتب `national.csv` و`regions.csv` و`activities.csv` و`region_activities.csv` في `data/analysis` (UTF-8، نهاية سطر `\n`، المفقود فراغ)، ولا يغيّر مخرجات التجهيز.
