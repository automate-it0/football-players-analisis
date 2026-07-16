<div align="center">

# ⚽ OpenScout AI Pro

**النظام التكتيكي الكشفي المتقدم للاعبي كرة القدم المدعوم بالذكاء الاصطناعي**

منصة ويب متكاملة مبنية بـ FastAPI وشات بوت ذكي (RAG) لتحليل وتقييم أداء لاعبي كرة القدم باستخدام البيانات الرياضية العميقة والنماذج اللغوية المحلية.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-blue?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-orange?logo=ollama)](https://ollama.com/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite)](https://www.sqlite.org/)

</div>

---

## 📋 English Overview

**OpenScout AI** is an advanced scouting dashboard and RAG (Retrieval-Augmented Generation) assistant designed for football scouts and club analysts. By combining static scout attributes (e.g., Football Manager metrics, EA Sports FC ratings) with deep match-event metrics (from StatsBomb Open Data), it provides automated scout reports and an interactive chatbot helper powered by **Qwen2.5-Coder**.

### Key Features
- **📊 Unified Scouting Database**: Processes and aggregates player attributes from FIFA, FC25, and historical datasets using a custom Pandas data engine.
- **⚡ StatsBomb Deep Metrics Integration**: Connects to StatsBomb APIs to calculate advanced tactical indicators like Expected Goals (xG), Expected Assists (xA), and retention under pressure.
- **🤖 Local AI Scout Reports**: Uses Ollama with `qwen2.5-coder:1.5b` to generate contextual scout reports based on tactical team instructions.
- **💬 Smart RAG Chatbot**: Real-time Q&A assistant that queries the SQLite database to answer custom scout queries (e.g., "Recommend a fast striker who excels under pressure").
- **🎨 Glassmorphism UI**: Beautiful, interactive front-end dashboard featuring Chart.js radar charts and evolution timeline analytics.

---

## 📋 نظرة عامة (Arabic Overview)

**OpenScout AI** هي منصة متقدمة لمساعدة كشافي ومحللي كرة القدم في تقييم اللاعبين وتوليد التقارير التكتيكية التلقائية. يدمج النظام بين البيانات العامة للاعبين والبيانات التكتيكية العميقة للمباريات (من خوادم StatsBomb المفتوحة)، مما يتيح توليد تقارير كشفية متقدمة ودقيقة بنقرة زر واحدة.

### المميزات الرئيسية:
- **📊 محرك معالجة البيانات (Pandas Engine)**: تجميع وتوحيد خصائص اللاعبين من قواعد بيانات FIFA و Football Manager وتصحيح الأسماء تلقائياً.
- **⚡ مقاييس StatsBomb العميقة**: احتساب الأهداف المتوقعة (xG)، الصناعة المتوقعة (xA)، ودقة التمريرات وتأثير الضغط.
- **🤖 تقارير الذكاء الاصطناعي المحلية**: توليد تقارير كشفية ذكية ومتخصصة باستخدام نموذج `qwen2.5-coder` المحلي بالتوافق مع التكتيكات المختلفة (تيكي تاكا، ضغط عالي، مرتدات).
- **💬 مساعد الكشاف الذكي (RAG Chat)**: شات بوت يستند إلى قاعدة بيانات اللاعبين للإجابة عن أسئلتك الكشفية وترشيح اللاعبين بالأرقام.
- **🎨 واجهة مستخدم تكتيكية**: تصميم عصري (Glassmorphism) مع رسوم بيانية تفاعلية (Radar Charts & Line Charts) لمتابعة مهارات وتطور اللاعبين.

---

## 🛠️ التقنيات المستخدمة (Tech Stack)

| التقنية | الاستخدام |
|---------|-----------|
| **FastAPI** | خادم الويب الأساسي والـ API Endpoints |
| **Python / Pandas** | معالجة وتنظيف ودمج قواعد البيانات الضخمة |
| **SQLite** | قاعدة البيانات المحلية لحفظ أرقام اللاعبين النهائية |
| **Ollama (Qwen2.5-Coder)** | توليد تقارير كشفية ذكية والإجابة عن شات بوت الـ RAG محلياً |
| **Chart.js** | الرسوم البيانية التفاعلية للواجهة |
| **Tailwind CSS** | تصميم وتنسيق الواجهات مع واجهة داكنة متطورة |

---

## 📁 هيكل المشروع (Project Layout)

```
football-players-analysis/
├── app.py                  # خادم FastAPI المطور والواجهات والـ API
├── data_engine.py          # محرك معالجة البيانات وسحب إحصائيات StatsBomb وبناء SQLite
├── harsh_tests.py          # اختبارات الجودة وحالات الحافة
├── qwen_server.py          # واجهة الاتصال وتشغيل النموذج المحلي
├── README.md               # هذا الملف
├── .gitignore              # ملفات Git المتجاهلة
├── *.csv                   # ملفات البيانات الخام للاعبين (EA FC, Goalkeepers, players)
└── openscout_database.db   # قاعدة البيانات النهائية (⚠️ يتم توليدها محلياً)
```

---

## 🚀 التشغيل المحلي (Quick Start)

### المتطلبات الأساسية
- **Python 3.10+**
- **Ollama** مثبت ومفعّل على جهازك.

### 1. تثبيت النموذج المحلي (Ollama)
قم بتحميل نموذج Qwen المخصص للأكواد البرمجية والمهمات التحليلية:
```bash
ollama pull qwen2.5-coder:1.5b
```

### 2. تثبيت المكتبات المطلوبة
```bash
pip install fastapi uvicorn pandas numpy statsbombpy requests striprtf pydantic
```

### 3. بناء قاعدة البيانات
قم بتشغيل محرك البيانات لسحب مباريات بطولة أمم إفريقيا ودمجها مع أرقام اللاعبين وبناء قاعدة البيانات المحلية:
```bash
python data_engine.py
```

### 4. تشغيل خادم الويب
```bash
python app.py
```
افتح المتصفح على: `http://127.0.0.1:8000`

---

## 📄 الترخيص
هذا المشروع مخصص لعرض المهارات التحليلية والبرمجية (Portfolio Project) — جميع الحقوق محفوظة.