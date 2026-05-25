# -----------------------------------------------------------------------------
# الملف: qwen_server.py
# الوظيفة: تشغيل نموذج Qwen2.5 (OpenVINO) كخادم API محلي ليتصل به app.py
# -----------------------------------------------------------------------------

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
import sys

# Handle encoding issues on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

# حاول استيراد مكتبة openvino_genai (الحديثة والأسرع لتشغيل النماذج)
try:
    import openvino_genai as ov_genai
    OPENVINO_AVAILABLE = True
except ImportError:
    OPENVINO_AVAILABLE = False
    print("⚠️ تحذير: مكتبة 'openvino_genai' غير مثبتة. لن يتمكن الخادم من تشغيل النموذج الفعلي.")

app = FastAPI(title="Qwen2.5 Local API Server")

# ==========================================
# 1. إعداد مسار النموذج (تم التحديث بمسارك الدقيق)
# ==========================================
MODEL_PATH = r"C:\Users\ziad\Downloads\ana alfager\qwen_model_ov"

# تحميل النموذج في الذاكرة عند بدء تشغيل السيرفر (لكي يكون الرد سريعاً جداً)
pipe = None
if OPENVINO_AVAILABLE and os.path.exists(MODEL_PATH):
    print("⏳ جاري تحميل نموذج Qwen2.5 في الذاكرة (CPU)... يرجى الانتظار...")
    try:
        pipe = ov_genai.LLMPipeline(MODEL_PATH, "CPU")
        print("✅ تم تحميل النموذج بنجاح وهو جاهز لاستقبال الطلبات!")
    except Exception as e:
        print(f"❌ خطأ أثناء تحميل النموذج: {e}")
else:
    print(f"⚠️ النموذج لم يتم تحميله. يرجى التأكد من وجود الملفات في المسار: {MODEL_PATH}")


# ==========================================
# 2. هيكل البيانات (يطابق ما يرسله app.py)
# ==========================================
class GenerateRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = False
    options: dict = None

# ==========================================
# 3. نقطة الاتصال (Endpoint)
# ==========================================
@app.post("/api/generate")
async def generate_text(req: GenerateRequest):
    print(f"\n📥 استقبلت طلباً جديداً لكتابة تقرير كشفي...")
    
    if pipe is None:
        # رد وهمي في حال فشل التحميل
        return {
            "model": req.model,
            "response": "عذراً، خادم Qwen يعمل، ولكن لم يتم تحميل ملفات OpenVINO بنجاح.",
            "done": True
        }
    
    try:
        # إعداد خصائص التوليد
        config = ov_genai.GenerationConfig()
        config.temperature = 0.7
        
        # قيم افتراضية آمنة لمنع التكرار اللانهائي
        max_tokens = 500
        rep_penalty = 1.15
        
        # قراءة وتحديث الخصائص من الطلب إذا أُرسلت
        if req.options:
            if "repeat_penalty" in req.options:
                rep_penalty = float(req.options["repeat_penalty"])
            elif "repetition_penalty" in req.options:
                rep_penalty = float(req.options["repetition_penalty"])
                
            if "num_predict" in req.options:
                max_tokens = int(req.options["num_predict"])
            elif "max_tokens" in req.options:
                max_tokens = int(req.options["max_tokens"])
                
        config.max_new_tokens = max_tokens
        config.repetition_penalty = rep_penalty
        
        print(f"⚙️ إعدادات التوليد النشطة: max_new_tokens={max_tokens}, repetition_penalty={rep_penalty}")
        
        # تشغيل النموذج لتوليد التقرير
        print("🤖 Qwen يفكر الآن...")
        generated_text = pipe.generate(req.prompt, config)
        print("✅ تم توليد التقرير بنجاح.")
        
        # إرجاع الرد بصيغة JSON متوافقة مع واجهة app.py
        return {
            "model": req.model,
            "response": generated_text,
            "done": True
        }
    except Exception as e:
        print(f"❌ حدث خطأ أثناء التوليد: {e}")
        return {"model": req.model, "response": "حدث خطأ داخلي أثناء محاولة التوليد.", "done": True}

# ==========================================
# 4. تشغيل الخادم
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء تشغيل خادم الذكاء الاصطناعي الوسيط...")
    print("الخادم سيعمل على المنفذ 11434 (متوافق مع app.py)")
    uvicorn.run(app, host="127.0.0.1", port=11434)