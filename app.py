# -----------------------------------------------------------------------------
# مشروع: OpenScout AI (النسخة الاحترافية 2.0)
# الملف: app.py
# الوظيفة: خادم FastAPI + شات بوت ذكي (RAG) + تقارير كشفية متقدمة
# -----------------------------------------------------------------------------

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import sqlite3
import pandas as pd
import requests
import json
import os
import sys
import data_engine

# Handle encoding issues on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

report_cache = {} # Cache for AI reports (Phase 5)

app = FastAPI(title="OpenScout AI Pro Dashboard")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_DIR = os.path.join(BASE_DIR, 'database')
DB_PATH = os.path.join(DB_DIR, 'openscout_database.db')
LOCAL_LLM_URL = "http://localhost:11434/api/generate" 

def clean_repetitions(text: str) -> str:
    """تحليل النص لمنع التكرار اللانهائي وقطع النص عند بدء التكرار"""
    if not text:
        return text
        
    import re
    # تقسيم النص بناءً على النقاط وعلامات الاستفهام والتعجب والسطور الجديدة
    parts = re.split(r'(\.|\n|؛|!|\?)', text)
    
    seen_phrases = set()
    cleaned_parts = []
    
    for part in parts:
        stripped = part.strip()
        # تخطي الأجزاء الفارغة والقصيرة جداً لضمان عدم حدوث تشخيصات خاطئة
        if len(stripped) < 15:
            cleaned_parts.append(part)
            continue
            
        # رصد تكرار الجمل الطويلة (تطابق تام أو احتواء جزء من الآخر)
        is_duplicate = False
        for seen in seen_phrases:
            if stripped == seen or (len(stripped) > 30 and seen in stripped) or (len(seen) > 30 and stripped in seen):
                is_duplicate = True
                break
                
        if is_duplicate:
            print(f"⚠️ كاشف التكرار (app.py): تم رصد جملة مكررة. قطع النص المتبقي لمنع التكرار.")
            break
            
        seen_phrases.add(stripped)
        cleaned_parts.append(part)
        
    return "".join(cleaned_parts)

def ask_qwen_local(prompt: str) -> str:
    """إرسال الطلب لنموذج Qwen المحلي"""
    try:
        payload = {
            "model": "qwen2.5-coder:1.5b", 
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "repeat_penalty": 1.15,
                "top_p": 0.85,
                "num_predict": 800
            }
        }
        response = requests.post(LOCAL_LLM_URL, json=payload, timeout=300)
        response.raise_for_status()
        raw_response = response.json().get('response', '')
        # تنظيف الرد من التكرار اللانهائي كإجراء أمان إضافي
        return clean_repetitions(raw_response)
    except requests.exceptions.Timeout:
        print("⚠️ خطأ: نفاد وقت الاتصال (Timeout) بالنموذج المحلي.")
        return "عذراً، استغرق الذكاء الاصطناعي وقتاً أطول من المتوقع."
    except Exception as e:
        print(f"⚠️ خطأ في الاتصال بالنموذج المحلي: {e}")
        return "عذراً، لم أتمكن من الاتصال بنموذج Qwen2.5. تأكد من تشغيل qwen_server.py."

# ==========================================
# واجهات برمجة التطبيقات (API)
# ==========================================
class ChatRequest(BaseModel):
    message: str

@app.get("/api/players")
def get_all_players():
    try:
        if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
            print("⚠️ قاعدة البيانات غير موجودة. سيتم بناؤها الآن تلقائياً...")
            data_engine.build_scouting_database()
            
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM players_scouting_data ORDER BY total_xG DESC", conn)
        conn.close()
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat")
def intelligent_chat(req: ChatRequest):
    """شات بوت ذكي يقرأ البيانات أولاً ثم يجيب (RAG)"""
    user_message = req.message.lower()
    
    # 1. استخراج البيانات من القاعدة
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM players_scouting_data", conn)
    conn.close()
    
    # 2. منطق تصفية ذكي بناءً على كلمات المستخدم
    if "سرع" in user_message or "سريع" in user_message:
        top_players = df.sort_values(by='pace', ascending=False).head(3)
        context = "أسرع اللاعبين:\n"
    elif "انهاء" in user_message or "هداف" in user_message or "يسجل" in user_message:
        top_players = df.sort_values(by='finishing', ascending=False).head(3)
        context = "أفضل المنهين للهجمات:\n"
    elif "ضغط" in user_message or "استلام" in user_message:
        top_players = df.sort_values(by='pass_success_under_pressure_pct', ascending=False).head(3)
        context = "أفضل اللاعبين تحت الضغط:\n"
    elif "صناع" in user_message or "تمرير" in user_message:
        top_players = df.sort_values(by='total_xA', ascending=False).head(3)
        context = "أفضل صناع اللعب:\n"
    else:
        top_players = df.head(3)
        context = "أبرز اللاعبين المتاحين:\n"

    # تحويل بيانات اللاعبين لنص ليفهمه النموذج
    for _, p in top_players.iterrows():
        context += f"- {p['player_name']} (مركز {p['position']}): سرعة {p['pace']}، إنهاء {p['finishing']}، أهداف متوقعة {p['total_xG']}\n"

    # 3. صياغة الـ Prompt للذكاء الاصطناعي
    prompt = f"""
    أنت مساعد كشاف رياضي ذكي. لقد سألك المستخدم: "{req.message}"
    
    بناءً على قاعدة البيانات الخاصة بنا، إليك المعلومات الحقيقية للاعبين:
    {context}
    
    قم بالرد على المستخدم باللغة العربية بأسلوب احترافي وودود، ورشح له هؤلاء اللاعبين بناءً على أرقامهم المذكورة أعلاه. 
    لا تخترع أي لاعب أو أرقام من خارج هذه القائمة.
    """
    
    reply = ask_qwen_local(prompt)
    return {"reply": reply}

@app.post("/api/report")
def generate_scout_report(player: dict):
    """توليد تقرير كشفي معقد واحترافي بـ 10 أضعاف قوة النسخة السابقة"""
    player_name = player.get('player_name', '')
    tactic = player.get('tactic', 'غير محدد')
    
    cache_key = f"{player_name}_{tactic}"
    if cache_key in report_cache:
        return {"report": report_cache[cache_key]}

    prompt = f"""
    أنت محلل أداء كرة قدم محترف (Football Analyst). اكتب تقريراً باللغة العربية عن لاعب كرة القدم الحقيقي: {player_name} (مركز: {player.get('position', 'غير محدد')}).
    
    البيانات والإحصائيات الحالية (2025):
    - السرعة والانفجار: {player.get('pace', 0)}/20
    - إنهاء الهجمات (Finishing): {player.get('finishing', 0)}/20
    - الهدوء تحت الضغط (Composure): {player.get('composure', 0)}/20
    - التحرك بدون كرة (Off the ball): {player.get('off_the_ball', 0)}/20
    - دقة التمرير تحت الضغط: {player.get('pass_success_under_pressure_pct', 0)}%
    
    البيانات التاريخية والتطور (السرعة والإنهاء والهدوء):
    - السرعة في 2024: {player.get('pace_2024', 0)}/20 | السرعة في 2025: {player.get('pace_2025', 0)}/20
    - الإنهاء في 2024: {player.get('finishing_2024', 0)}/20 | الإنهاء في 2025: {player.get('finishing_2025', 0)}/20
    - الهدوء في 2024: {player.get('composure_2024', 0)}/20 | الهدوء في 2025: {player.get('composure_2025', 0)}/20
    - معدل تغير السرعة: {player.get('pace_change', 0)}
    - معدل تغير الإنهاء: {player.get('finishing_change', 0)}
    
    تكتيك الفريق المطلوب: {tactic}
    
    اكتب تقريراً رياضياً دقيقاً وقصيراً. استخدم مصطلحات كرة القدم حصراً (مثل: بناء اللعب من الخلف، كسر خطوط الضغط، المساحات، دقة التمرير، المرتدات). إياك واستخدام كلمات غريبة مثل "التعاطف"، "المواطنين"، "التحديات التنفسية".
    
    يجب أن يحتوي التقرير على العناوين التالية (Markdown) فقط وبدون إطالة:
    
    ### ملخص اللاعب والتطور التاريخي
    (جملة رياضية واحدة تلخص جودة اللاعب ومستوى تطوره أو تراجعه التكتيكي بين عامي 2024 و2025 بناءً على الأرقام التاريخية المذكورة)
    
    ### نقاط القوة
    (اذكر نقطتين فقط بناءً على أعلى الأرقام لديه، واربطها بقدراته الهجومية أو الدفاعية في كرة القدم وتطوره التاريخي)
    
    ### التوظيف التكتيكي
    (اشرح في سطرين كيف يخدم هذا اللاعب تكتيك: {tactic}. أعط نسبة مئوية لمدى توافته مع هذا التكتيك)
    """
    report = ask_qwen_local(prompt)
    report_cache[cache_key] = report
    return {"report": report}

# ==========================================
# واجهة المستخدم (HTML / Tailwind CSS / JS)
# ==========================================
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>الكشاف الرقمي PRO</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0b1120; color: #e2e8f0; scroll-behavior: smooth; }
        .glass-panel { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.05); transition: all 0.3s ease; }
        .glass-panel:hover { box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.15); border-color: rgba(16, 185, 129, 0.3); transform: translateY(-2px); }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .chat-bubble-user { background: #059669; color: white; border-radius: 1rem 1rem 0 1rem; }
        .chat-bubble-ai { background: #1e293b; color: #e2e8f0; border-radius: 1rem 1rem 1rem 0; border: 1px solid #334155; }
    </style>
</head>
<body class="h-screen flex flex-col md:flex-row overflow-hidden">

    <!-- القائمة الجانبية (الشات بوت وقائمة اللاعبين) -->
    <div class="w-full md:w-1/3 glass-panel h-full flex flex-col border-l border-slate-800 relative z-10">
        <div class="p-5 border-b border-slate-800 bg-slate-900/50">
            <h1 class="text-2xl font-bold text-emerald-400 tracking-wide"><i class="fa-solid fa-radar flex-shrink-0 mr-2"></i> OpenScout PRO</h1>
            <p class="text-xs text-slate-400 mt-2 flex items-center"><span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse ml-2"></span> متصل بقاعدة البيانات الذكية</p>
        </div>
        
        <!-- منطقة الشات بوت -->
        <div class="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-hide flex flex-col" id="chat-container">
            <div class="chat-bubble-ai p-3 text-sm self-start max-w-[85%] shadow-lg">
                أهلاً بك أيها الكشاف! أنا المساعد الذكي. يمكنك النقر على أي لاعب بالأسفل لاستخراج تقريره، أو سؤالي مباشرة (مثال: من هو أفضل مهاجم تحت الضغط؟).
            </div>
            
            <!-- قائمة اللاعبين (تظهر كبطاقات داخل الشات) -->
            <div id="players-list" class="space-y-2 mt-4"></div>
        </div>

        <!-- مربع إدخال الدردشة -->
        <div class="p-4 border-t border-slate-800 bg-slate-900">
            <div class="flex relative">
                <input type="text" id="chat-input" placeholder="اسأل المساعد الذكي..." 
                    class="w-full bg-slate-800 text-white rounded-xl pl-12 pr-4 py-3 outline-none focus:ring-1 focus:ring-emerald-500 border border-slate-700 shadow-inner">
                <button onclick="sendChatMessage()" class="absolute left-2 top-2 bottom-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg px-4 transition shadow-md">
                    <i class="fa-solid fa-paper-plane"></i>
                </button>
            </div>
        </div>
    </div>

    <!-- لوحة تحكم اللاعب والتقرير الكشفي (اليسار) -->
    <div class="w-full md:w-2/3 h-full flex flex-col bg-gradient-to-br from-slate-900 to-[#0b1120] p-6 overflow-y-auto relative">
        <div id="welcome-screen" class="h-full flex flex-col items-center justify-center text-slate-500">
            <div class="w-32 h-32 rounded-full border-4 border-dashed border-slate-700 flex items-center justify-center mb-6 animate-[spin_10s_linear_infinite]">
                <i class="fa-solid fa-microchip text-4xl text-slate-600 animate-[spin_10s_linear_infinite_reverse]"></i>
            </div>
            <h2 class="text-3xl font-light text-slate-300">النظام الكشفي المتقدم</h2>
            <p class="mt-3 text-sm text-slate-500 max-w-md text-center leading-relaxed">اضغط على بطاقة لاعب ليقوم Qwen2.5 بتحليل 10 متغيرات تكتيكية وتوليد تقرير احترافي شامل.</p>
        </div>

        <div id="player-dashboard" class="hidden h-full flex-col">
            <!-- الهيدر -->
            <div class="flex items-center gap-6 mb-8 bg-slate-800/40 p-6 rounded-2xl border border-slate-700/50 shadow-xl">
                <div class="w-20 h-20 rounded-full bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center text-3xl font-bold text-white shadow-lg" id="pd-initial"></div>
                <div class="flex-1">
                    <h2 class="text-3xl font-bold text-white" id="pd-name">اسم اللاعب</h2>
                    <div class="flex gap-4 mt-2">
                        <span class="bg-slate-700 text-emerald-400 text-xs px-3 py-1 rounded-full border border-slate-600 font-mono" id="pd-position">ST</span>
                        <span class="bg-slate-700 text-blue-400 text-xs px-3 py-1 rounded-full border border-slate-600 font-mono">مباريات محللة: <span id="pd-matches"></span></span>
                        
                        <select id="tactic-selector" onchange="reloadReport()" class="bg-slate-700 text-white text-xs px-3 py-1 rounded-full border border-emerald-600 outline-none hover:bg-slate-600 cursor-pointer transition">
                            <option value="الاستحواذ (Tiki-Taka)">تكتيك: الاستحواذ (Tiki-Taka)</option>
                            <option value="الضغط العالي العكسي (Gegenpressing)">تكتيك: الضغط العالي (Gegenpressing)</option>
                            <option value="الهجمات المرتدة السريعة (Counter Attack)">تكتيك: المرتدات السريعة (Counter Attack)</option>
                            <option value="الدفاع المتأخر والكتلة المنخفضة (Low Block)">تكتيك: دفاع متأخر (Low Block)</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- الأرقام التكتيكية المتقدمة -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div class="glass-panel p-5 rounded-2xl text-center shadow-lg hover:border-emerald-500/50 transition">
                    <div class="text-slate-400 text-xs mb-2 tracking-wide font-bold">السرعة والانفجار</div>
                    <div class="text-3xl font-black text-white" id="pd-pace">0</div>
                </div>
                <div class="glass-panel p-5 rounded-2xl text-center shadow-lg hover:border-emerald-500/50 transition">
                    <div class="text-slate-400 text-xs mb-2 tracking-wide font-bold">الأهداف المتوقعة (xG)</div>
                    <div class="text-3xl font-black text-emerald-400" id="pd-xg">0.0</div>
                </div>
                <div class="glass-panel p-5 rounded-2xl text-center shadow-lg hover:border-emerald-500/50 transition">
                    <div class="text-slate-400 text-xs mb-2 tracking-wide font-bold">الصناعة المتوقعة (xA)</div>
                    <div class="text-3xl font-black text-blue-400" id="pd-xa">0.0</div>
                </div>
                <div class="glass-panel p-5 rounded-2xl text-center shadow-lg hover:border-emerald-500/50 transition">
                    <div class="text-slate-400 text-xs mb-2 tracking-wide font-bold">دقة التمرير تحت الضغط</div>
                    <div class="text-3xl font-black text-amber-400" id="pd-pressure">0%</div>
                </div>
            </div>

            <!-- الرسوم البيانية وتقارير الذكاء الاصطناعي -->
            <div class="flex-1 flex flex-col md:flex-row gap-6 overflow-hidden">
                
                <!-- Radar & Timeline Charts Card -->
                <div class="w-full md:w-1/3 glass-panel rounded-2xl p-6 flex flex-col shadow-2xl">
                    <div class="flex border-b border-slate-700/50 pb-2 mb-4 justify-between items-center">
                        <div class="flex gap-4">
                            <button onclick="switchChartTab('radar')" id="tab-btn-radar" class="text-emerald-400 font-bold text-sm border-b-2 border-emerald-400 pb-1 focus:outline-none transition">
                                <i class="fa-solid fa-chart-pie ml-1"></i> المهارات
                            </button>
                            <button onclick="switchChartTab('timeline')" id="tab-btn-timeline" class="text-slate-400 font-bold text-sm hover:text-white pb-1 focus:outline-none transition">
                                <i class="fa-solid fa-chart-line ml-1"></i> تطور اللاعب
                            </button>
                        </div>
                    </div>
                    <div class="flex-1 flex items-center justify-center relative min-h-[220px]">
                        <div id="radar-container" class="w-full h-full flex items-center justify-center">
                            <canvas id="radarChart"></canvas>
                        </div>
                        <div id="timeline-container" class="w-full h-full hidden flex items-center justify-center">
                            <canvas id="timelineChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- تقرير الذكاء الاصطناعي (Qwen2.5) -->
                <div class="w-full md:w-2/3 glass-panel rounded-2xl p-8 flex flex-col shadow-2xl relative overflow-hidden">
                    <div class="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-full blur-3xl"></div>
                    <h3 class="text-xl font-bold text-emerald-400 mb-6 flex items-center border-b border-slate-700/50 pb-4">
                        <i class="fa-solid fa-file-signature mr-3 ml-3 text-2xl"></i> التقرير الكشفي الاحترافي (Qwen2.5)
                    </h3>
                    <div id="ai-report-content" class="text-slate-300 leading-8 overflow-y-auto pr-2 text-justify flex-1">
                    </div>
                </div>
                
            </div>
        </div>
    </div>

    <script>
        let allPlayers = [];

        async function loadPlayers() {
            try {
                const response = await fetch('/api/players');
                if (!response.ok) throw new Error();
                allPlayers = await response.json();
                renderPlayers(allPlayers);
            } catch (error) {
                document.getElementById('players-list').innerHTML = '<div class="text-red-400 text-center mt-5 text-sm">خطأ في جلب البيانات.<br>تأكد من تشغيل محرك البيانات.</div>';
            }
        }

        function renderPlayers(players) {
            const list = document.getElementById('players-list');
            list.innerHTML = '<div class="text-xs text-slate-500 font-bold mb-2 pr-2">قاعدة بيانات اللاعبين ('+players.length+')</div>';
            
            players.forEach(p => {
                const card = document.createElement('div');
                card.className = "p-3 bg-slate-800/80 hover:bg-slate-700 rounded-xl cursor-pointer transition border border-slate-700 hover:border-emerald-500 flex items-center justify-between mb-2 shadow-sm";
                card.onclick = () => openPlayerDashboard(p);
                
                card.innerHTML = `
                    <div>
                        <div class="font-bold text-white text-sm">${p.player_name}</div>
                        <div class="text-[10px] text-slate-400 mt-1 flex gap-2">
                            <span class="bg-slate-900 px-2 py-0.5 rounded">${p.position}</span>
                            <span class="text-emerald-500">xG: ${p.total_xG.toFixed(2)}</span>
                        </div>
                    </div>
                    <div class="text-slate-500 text-xs"><i class="fa-solid fa-chart-simple"></i></div>
                `;
                list.appendChild(card);
            });
        }

        // --- نظام الشات بوت الذكي ---
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            if(!message) return;
            
            const chatContainer = document.getElementById('chat-container');
            
            // إضافة رسالة المستخدم
            chatContainer.innerHTML += `<div class="chat-bubble-user p-3 text-sm self-end max-w-[85%] shadow-lg mt-4 mb-2">${message}</div>`;
            input.value = '';
            
            // إضافة مؤشر التحميل للذكاء الاصطناعي
            const loadingId = 'loading-' + Date.now();
            chatContainer.innerHTML += `<div id="${loadingId}" class="chat-bubble-ai p-3 text-sm self-start max-w-[85%] shadow-lg mb-4 text-emerald-400"><i class="fa-solid fa-circle-notch fa-spin"></i> المساعد يبحث ويحلل...</div>`;
            chatContainer.scrollTop = chatContainer.scrollHeight;

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                const data = await response.json();
                
                // استبدال مؤشر التحميل بالرد الحقيقي
                document.getElementById(loadingId).innerHTML = data.reply.replace(/\n/g, '<br>');
            } catch (error) {
                document.getElementById(loadingId).innerHTML = '<span class="text-red-400">خطأ في الاتصال بالنموذج.</span>';
            }
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        // تفعيل الإرسال بـ Enter
        document.getElementById('chat-input').addEventListener('keypress', function (e) {
            if (e.key === 'Enter') sendChatMessage();
        });

        // --- نظام التقارير ---
        let currentAbortController = null;
        let radarChartInstance = null;
        let timelineChartInstance = null;
        let currentPlayer = null;

        function reloadReport() {
            if(currentPlayer) openPlayerDashboard(currentPlayer);
        }

        function switchChartTab(tab) {
            const radarTab = document.getElementById('tab-btn-radar');
            const timelineTab = document.getElementById('tab-btn-timeline');
            const radarCont = document.getElementById('radar-container');
            const timelineCont = document.getElementById('timeline-container');
            
            if (tab === 'radar') {
                radarTab.className = "text-emerald-400 font-bold text-sm border-b-2 border-emerald-400 pb-1 focus:outline-none transition";
                timelineTab.className = "text-slate-400 font-bold text-sm hover:text-white pb-1 focus:outline-none transition";
                radarCont.classList.remove('hidden');
                timelineCont.classList.add('hidden');
            } else {
                timelineTab.className = "text-emerald-400 font-bold text-sm border-b-2 border-emerald-400 pb-1 focus:outline-none transition";
                radarTab.className = "text-slate-400 font-bold text-sm hover:text-white pb-1 focus:outline-none transition";
                radarCont.classList.add('hidden');
                timelineCont.classList.remove('hidden');
                
                if (timelineChartInstance) {
                    timelineChartInstance.resize();
                }
            }
        }

        async function openPlayerDashboard(player) {
            currentPlayer = player;
            if (currentAbortController) {
                currentAbortController.abort();
            }
            currentAbortController = new AbortController();

            document.getElementById('welcome-screen').classList.add('hidden');
            document.getElementById('player-dashboard').classList.remove('hidden');
            document.getElementById('player-dashboard').classList.add('flex');

            document.getElementById('pd-initial').innerText = (player.player_name || '؟').substring(0, 2).toUpperCase();
            document.getElementById('pd-name').innerText = player.player_name || 'غير متوفر';
            document.getElementById('pd-position').innerText = player.position || 'N/A';
            document.getElementById('pd-matches').innerText = player.matches_analyzed || 0;
            document.getElementById('pd-pace').innerText = player.pace || 0;
            document.getElementById('pd-xg').innerText = (player.total_xG || 0).toFixed(2);
            document.getElementById('pd-xa').innerText = (player.total_xA || 0).toFixed(2);
            document.getElementById('pd-pressure').innerText = (player.pass_success_under_pressure_pct || 0).toFixed(1) + '%';

            // تحديث شارة مؤشر التطور والاتجاه (Trend Indicator)
            const trendSpan = document.getElementById('pd-trend');
            if (player.pace_change > 0 || player.finishing_change > 0) {
                const paceDiff = player.pace_change > 0 ? `+${player.pace_change} سرعة` : '';
                const finDiff = player.finishing_change > 0 ? `+${player.finishing_change} إنهاء` : '';
                trendSpan.className = "bg-emerald-500/20 text-emerald-400 text-xs px-3 py-1 rounded-full border border-emerald-500/30 font-bold block";
                trendSpan.innerText = `📈 تطور: ${[paceDiff, finDiff].filter(Boolean).join('، ')}`;
            } else if (player.pace_change < 0 || player.finishing_change < 0) {
                const paceDiff = player.pace_change < 0 ? `${player.pace_change} سرعة` : '';
                const finDiff = player.finishing_change < 0 ? `${player.finishing_change} إنهاء` : '';
                trendSpan.className = "bg-red-500/20 text-red-400 text-xs px-3 py-1 rounded-full border border-red-500/30 font-bold block";
                trendSpan.innerText = `📉 تراجع: ${[paceDiff, finDiff].filter(Boolean).join('، ')}`;
            } else {
                trendSpan.className = "hidden";
            }

            // Draw Radar Chart
            const ctx = document.getElementById('radarChart').getContext('2d');
            if(radarChartInstance) radarChartInstance.destroy();
            radarChartInstance = new Chart(ctx, {
                type: 'radar',
                data: {
                    labels: ['السرعة', 'الإنهاء', 'الهدوء', 'التحرك', 'الرؤية'],
                    datasets: [{
                        label: player.player_name,
                        data: [
                            player.pace || 0,
                            player.finishing || 0,
                            player.composure || 0,
                            player.off_the_ball || 0,
                            player.vision || 0
                        ],
                        backgroundColor: 'rgba(16, 185, 129, 0.2)',
                        borderColor: 'rgba(16, 185, 129, 1)',
                        pointBackgroundColor: 'rgba(16, 185, 129, 1)',
                        pointBorderColor: '#fff',
                        pointHoverBackgroundColor: '#fff',
                        pointHoverBorderColor: 'rgba(16, 185, 129, 1)'
                    }]
                },
                options: {
                    scales: {
                        r: {
                            angleLines: { color: 'rgba(255, 255, 255, 0.1)' },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' },
                            pointLabels: { color: '#94a3b8', font: { family: 'Segoe UI', size: 11 } },
                            ticks: { display: false, min: 0, max: 20 }
                        }
                    },
                    plugins: { legend: { display: false } }
                }
            });

            // Draw Timeline Chart
            const ctxTimeline = document.getElementById('timelineChart').getContext('2d');
            if(timelineChartInstance) timelineChartInstance.destroy();
            timelineChartInstance = new Chart(ctxTimeline, {
                type: 'line',
                data: {
                    labels: ['2024', '2025'],
                    datasets: [
                        {
                            label: 'السرعة (Pace)',
                            data: [player.pace_2024 || 0, player.pace_2025 || 0],
                            borderColor: 'rgba(16, 185, 129, 1)',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            tension: 0.1,
                            fill: true
                        },
                        {
                            label: 'الإنهاء (Finishing)',
                            data: [player.finishing_2024 || 0, player.finishing_2025 || 0],
                            borderColor: 'rgba(59, 130, 246, 1)',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.1,
                            fill: true
                        }
                    ]
                },
                options: {
                    scales: {
                        y: {
                            min: 0,
                            max: 20,
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.05)' },
                            ticks: { color: '#94a3b8' }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: { color: '#94a3b8', font: { family: 'Segoe UI', size: 10 } }
                        }
                    }
                }
            });

            const reportDiv = document.getElementById('ai-report-content');
            reportDiv.innerHTML = '<div class="text-emerald-400 animate-pulse flex flex-col items-center justify-center py-10"><i class="fa-solid fa-brain text-5xl mb-4 opacity-50"></i><span>Qwen2.5 يقوم بتحليل البيانات وكتابة التقرير التكتيكي...</span></div>';

            const tactic = document.getElementById('tactic-selector').value;
            const payload = { ...player, tactic: tactic };

            try {
                const response = await fetch('/api/report', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                    signal: currentAbortController.signal
                });
                if (!response.ok) throw new Error("فشل الاستجابة من الخادم");
                const data = await response.json();
                
                // تنسيق التقرير الماركدون ليظهر بشكل احترافي
                let formattedReport = data.report.replace(/\n/g, '<br>');
                // تحويل عناوين الماركدون (### Title)
                formattedReport = formattedReport.replace(/###\s*(.*?)(<br>|$)/g, '<br><span class="text-emerald-400 font-bold text-lg border-b border-emerald-900 pb-1 mb-2 inline-block"><i class="fa-solid fa-caret-left ml-2"></i>$1</span><br>');
                // تحويل النص العريض (**text**)
                formattedReport = formattedReport.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
                
                reportDiv.innerHTML = formattedReport;
            } catch (error) {
                if (error.name === 'AbortError') {
                    // تم الإلغاء بسبب اختيار لاعب آخر، لا تفعل شيئاً
                } else {
                    reportDiv.innerHTML = `<div class="text-red-400 mt-4">فشل جلب التقرير: ${error.message}</div>`;
                }
            }
        }

        loadPlayers();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def read_root():
    return HTML_CONTENT

if __name__ == "__main__":
    import uvicorn
    print("🚀 جاري تشغيل خادم OpenScout AI PRO...")
    uvicorn.run(app, host="127.0.0.1", port=8000)