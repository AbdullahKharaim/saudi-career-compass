"""مسارات المشروع وسجل المصادر المثبتة (كما تحقق منها Claude في 2026-10-04)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "data" / "sources"
WEB_DIR = ROOT / "web"
WEB_DATA_DIR = WEB_DIR / "data"
CURATED_FILE = Path(__file__).resolve().parent / "curated" / "digital_paths.json"

# معرّف صريح؛ لا ننتحل متصفحًا ولا نتجاوز أي حماية من الروبوتات.
USER_AGENT = "SaudiCareerCompass/0.1 (local research prototype; personal non-profit use)"
TIMEOUT = 60

HRSD_FILES = "https://hrsd.gov.sa/sites/default/files/2025-02/"
HRSD_SKILLS_PAGE = "https://www.hrsd.gov.sa/care-about-you/skillsandtrain"
HRSD_TERMS = "https://www.hrsd.gov.sa/how-use"
HRSD_OPEN_DATA_INDEX = "https://www.hrsd.gov.sa/knowledge-centre/data-and-statistics/open-data/758917"
ODP_API = "https://open.data.gov.sa/api/datasets/"
ODP_FILES = "https://open.data.gov.sa/odp-public/"
ODP_DATASET_PAGE = "https://open.data.gov.sa/ar/datasets/view/"
ODP_LICENSE = "https://open.data.gov.sa/ar/pages/policies/license"
SOBOL_PAGE = "https://www.hrdf.org.sa/products-and-services/programs/individuals/guidance/career-guidance-sobol/"

HRSD_OPEN_DATA_POLICY = "https://www.hrsd.gov.sa/knowledge-centre/data-and-statistics/open-data/69741"
TERMS_CHECKED_ON = "2026-10-04"

# دليل الشروط مسجل لكل مصدر على حدة، ويفصل ما ثبت عما بقي غير محسوم (فحص Claude المباشر في
# TERMS_CHECKED_ON). ليس رأيًا قانونيًا ولا إذن نشر؛ إتاحة الملف للتنزيل لا تعني إذنًا بإعادة نشره.
_PORTAL_TERMS = ("الملف منشور في صفحة «المهارات والتدريب» ببوابة الوزارة، وشروط البوابة العامة تسمح للمستخدم الشخصي "
                 "وللاستخدام غير الربحي بالاستفادة من المحتوى مع ذكر المصدر، وتقيّد العرض العلني والتوزيع والأعمال "
                 "المشتقة للجمهور بموافقة خطية مسبقة.")
_UNRESOLVED_OPEN = ("غير محسوم: هل يُعد هذا الملف من «البيانات المفتوحة» التي تنظمها سياسة الوزارة، أو له إذن مستقل "
                    "بإعادة الاستخدام العام. صفحة الملف لا تذكر رخصة.")
SKILLS_DB_TERMS = (f"ما ثبت: {_PORTAL_TERMS} لم نجد رخصة أو إشعار حقوق في نصوص خلايا الملف (فُحص النص فقط، لا الصور "
                   f"ولا الخصائص). {_UNRESOLVED_OPEN}")
SKILLS_DICTIONARY_TERMS = (f"ما ثبت: {_PORTAL_TERMS} وصفحة 2 من هذا الملف تنص على أن محتواه ملكية خاصة لمجلس مهارات "
                           f"القطاع الرقمي وأنه لأغراض المعلومات العامة، دون منح صريح لإعادة الاستخدام. {_UNRESOLVED_OPEN}")
GROUPS_PATHS_TERMS = (f"ما ثبت: {_PORTAL_TERMS} وصفحة 2 من هذا الملف نفسه (فُحصت مستقلة عن القاموس) تنص على أن "
                      f"محتواه ملكية خاصة لمجلس مهارات القطاع الرقمي، دون منح صريح لإعادة الاستخدام. {_UNRESOLVED_OPEN}")


def odp_terms(dataset_id: str) -> str:
    """دليل رخصة مجموعة بيانات بعينها؛ لا يُعمم من مجموعة إلى أخرى."""
    if dataset_id not in ODP_LICENSE_CHECKED:
        return "لم تُفحص خانة الرخصة في صفحة هذه المجموعة بعد؛ لا يُفترض أنها مرخصة."
    return ("ما ثبت: صفحة هذه المجموعة على منصة البيانات المفتوحة تعرض في خانة «الرخصة» رابط «رخصة البيانات المفتوحة» "
            f"(فُحصت في {ODP_LICENSE_CHECKED[dataset_id]})، وملخص الرخصة يتيح الاستخدام وإعادة الاستخدام والبناء عليها "
            "بشرط ذكر المصدر بالطريقة المحددة فيها. غير محسوم: الاستثناءات التفصيلية في نص الرخصة الكامل لأي استخدام "
            "علني فعلي؛ هذا ليس رأيًا قانونيًا.")


@dataclass(frozen=True)
class FileSource:
    id: str
    title: str
    publisher: str
    url: str
    page_url: str
    kind: str          # xlsx | pdf | csv
    terms: str
    terms_url: str
    edition: str = ""
    terms_status: str = "unresolved"   # proven | unresolved: هل ثبت إذن صريح بإعادة الاستخدام العام


SKILLS_DB = FileSource(
    id="hrsd-digital-skills-db",
    title="قاعدة بيانات المهارات للقطاع الرقمي",
    publisher="وزارة الموارد البشرية والتنمية الاجتماعية — المجلس القطاعي للمهارات للقطاع الرقمي",
    url=HRSD_FILES + quote("قاعدة بيانات المهارات للقطاع الرقمي.xlsx"),
    page_url=HRSD_SKILLS_PAGE, kind="xlsx", terms=SKILLS_DB_TERMS, terms_url=HRSD_TERMS, edition="إصدار 2025",
)
SKILLS_DICTIONARY = FileSource(
    id="hrsd-digital-skills-dictionary",
    title="قاموس المهارات للقطاع الرقمي",
    publisher=SKILLS_DB.publisher,
    url="https://www.hrsd.gov.sa/sites/default/files/2025-02/" + quote("قاموس المهارات للقطاع الرقمي.pdf"),
    page_url=HRSD_SKILLS_PAGE, kind="pdf", terms=SKILLS_DICTIONARY_TERMS, terms_url=HRSD_TERMS, edition="إصدار 2025",
)
GROUPS_PATHS = FileSource(
    id="hrsd-digital-groups-paths",
    title="نظرة عامة على القطاع والمجموعات الوظيفية والمسارات الوظيفية للقطاع الرقمي",
    publisher=SKILLS_DB.publisher,
    url=HRSD_FILES + quote("نظرة عامة على القطاع والمجموعات الوظيفية والمسارات الوظيفية للقطاع الرقمي.pdf"),
    page_url=HRSD_SKILLS_PAGE, kind="pdf", terms=GROUPS_PATHS_TERMS, terms_url=HRSD_TERMS, edition="إصدار 2025",
)
HRSD_SOURCES = (SKILLS_DB, SKILLS_DICTIONARY, GROUPS_PATHS)


@dataclass(frozen=True)
class OdpDataset:
    """مجموعة بيانات على منصة البيانات المفتوحة؛ الفترة مثبتة هنا بعد مراجعة بشرية."""
    dataset_id: str
    year: int
    quarter: int
    raw_file: str      # الملف المقابل في data/raw المعتمد للتحليل

    @property
    def source_id(self):
        return f"odp-workers-activity-region-{self.year}q{self.quarter}"


WORKERS_DATASETS = (
    OdpDataset("3f25d48e-f3c4-4c02-847e-0ce6e14b6d5b", 2026, 1, "Workers in the private sector Q12026CSV.csv"),
    OdpDataset("11d328f2-7c11-4a26-8bcd-e8f6bef5f706", 2026, 2, "Employees private sector Q22026CSV.csv"),
)
# خانة «الرخصة» فُحصت في صفحة كل مجموعة على حدة.
ODP_LICENSE_CHECKED = {"3f25d48e-f3c4-4c02-847e-0ce6e14b6d5b": "2026-10-04", "11d328f2-7c11-4a26-8bcd-e8f6bef5f706": "2026-10-04"}
WORKERS_TITLE_MARKER = "في القطاع الخاص حسب النشاط الاقتصادي والمنطقة الادارية"

# المساران المختاران للرحلة الأولى (اسم القطاع الفرعي، اسم المجموعة كما في قاعدة البيانات).
FEATURED_PATHS = (("تقنية المعلومات", "البرمجيات"), ("تقنية المعلومات", "البيانات والذكاء الاصطناعي"))
MARKET_ACTIVITY = "المعلومات والاتصالات"
