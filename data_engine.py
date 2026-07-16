# -----------------------------------------------------------------------------
# مشروع: OpenScout AI (الكشاف الرقمي المفتوح)
# الملف: data_engine.py
# الوظيفة: سحب البيانات، تنظيفها، حساب المقاييس الرياضية، وتخزينها في SQLite
# -----------------------------------------------------------------------------

import pandas as pd
import numpy as np
import sqlite3
import os
import warnings
import sys
import socket

# ضبط مهلة الاتصال بالشبكة لضمان عدم التعليق اللانهائي في البيئات المحلية
socket.setdefaulttimeout(5.0)

# Handle encoding issues on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

# إخفاء تحذيرات StatsBomb المزعجة (NoAuthWarning) لتنظيف الشاشة
warnings.filterwarnings("ignore")

# تأكد من تثبيت المكتبة عبر: pip install statsbombpy
from statsbombpy import sb 

# ==========================================
# 0. وظائف تنظيف وتوحيد البيانات (Name Normalization & Schema Mapping)
# ==========================================
def normalize_player_name(name):
    """
    وظيفة لتنظيف وتوحيد أسماء اللاعبين لربطها عبر مصادر البيانات المختلفة.
    تقوم بإزالة الحركات والرموز وتوحيد حالة الأحرف والمسافات.
    """
    if not isinstance(name, str):
        return ""
    import unicodedata
    import re
    # إزالة التشكيل والعلامات الخاصة بالحروف اللاتينية
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    # تحويل الأحرف إلى حالة صغيرة وإزالة الفراغات الجانبية
    name = name.lower().strip()
    # إزالة الرموز الخاصة وعلامات الترقيم
    name = re.sub(r'[^a-z0-9\s]', '', name)
    # تقليص المسافات المتعددة
    name = re.sub(r'\s+', ' ', name)
    
    # خريطة لتوحيد بعض الاختلافات الشائعة في الأسماء
    aliases = {
        'vini jr': 'vinicius junior',
        'vinicius jr': 'vinicius junior',
        'achraf hakimi': 'achraf hakimi mouh',
        'mostafa mohamed': 'mostafa mohamed ahmed abdallah',
    }
    return aliases.get(name, name)

def map_column_names(df, rename_dict):
    """
    وظيفة لتوحيد أسماء الأعمدة في جداول البيانات المختلفة.
    """
    return df.rename(columns=rename_dict)

# ==========================================
# 1. طبقة البيانات العامة (بيانات FM الحقيقية أو المحاكاة كبديل)
# ==========================================
def get_fm_public_data(file_path='fm_data.rtf'):
    """
    تقوم هذه الدالة بقراءة وتحليل ملف تصدير Football Manager (RTF أو نصي).
    إذا لم يكن الملف موجوداً، يتم استخدام البيانات الافتراضية كبديل لضمان عدم توقف النظام.
    """
    import os
    if not os.path.exists(file_path):
        print(f"⚠️ ملف بيانات FM غير موجود في المسار: {file_path}. سيتم استخدام البيانات الافتراضية للاعبي إفريقيا العرب.")
        fm_data = {
            'player_name': [
                'Mohamed Salah', 'Omar Marmoush', 'Mostafa Mohamed Ahmed Abdallah',
                'Victor James Osimhen', 'Yoane Wissa', 'Teboho Mokoena', 'Percy Tau',
                'Franck Yannick Kessié', 'Cédric Bakambu', 'William Troost-Ekong',
                'Emilio Nsue López', 'Sadio Mané', 'Riyad Mahrez', 'Achraf Hakimi Mouh'
            ],
            'position': ['RW', 'ST', 'ST', 'ST', 'ST', 'CM', 'RW', 'CM', 'ST', 'CB', 'ST', 'LW', 'RW', 'RB'],
            'pace': [18, 17, 14, 18, 16, 13, 15, 13, 15, 13, 14, 17, 15, 19],             # السرعة
            'finishing': [18, 14, 16, 17, 15, 12, 14, 12, 15, 8, 15, 16, 15, 12],         # الإنهاء
            'composure': [18, 15, 15, 16, 14, 15, 14, 16, 14, 15, 14, 16, 17, 14],         # الهدوء
            'off_the_ball': [19, 15, 16, 18, 15, 13, 15, 14, 16, 8, 15, 17, 16, 15],       # التحرك بدون كرة
            'vision': [18, 14, 12, 12, 13, 16, 15, 14, 12, 10, 11, 16, 18, 15]            # الرؤية
        }
        df_fm = pd.DataFrame(fm_data)
        print("✅ تم تجهيز بيانات الكشافين الافتراضية بنجاح.")
        return df_fm

    print(f"⏳ جاري قراءة وتحليل ملف تصدير FM من: {file_path}...")
    try:
        from striprtf.striprtf import rtf_to_text
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            rtf_content = f.read()
        
        # التحقق مما إذا كان الملف RTF فعلي أم مجرد نص عادي
        if rtf_content.strip().startswith('{'):
            text = rtf_to_text(rtf_content)
        else:
            text = rtf_content
            
        lines = [line.strip() for line in text.split('\n') if '|' in line]
        if not lines:
            print("⚠️ لم يتم العثور على جداول بيانات صالحة داخل ملف FM.")
            return None
            
        # استخراج العناوين
        headers = [h.strip() for h in lines[0].split('|')[1:-1]]
        
        # استخراج البيانات
        data = []
        for line in lines[1:]:
            # تخطي السطور الفاصلة مثل |----|
            if all(c in '-=_ ' for c in line.replace('|', '')):
                continue
            row = [val.strip() for val in line.split('|')[1:-1]]
            if len(row) == len(headers):
                data.append(row)
                
        df = pd.DataFrame(data, columns=headers)
        
        # خرائط أسماء الأعمدة لتوحيدها
        column_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'name' in col_lower or 'الاسم' in col_lower:
                column_mapping[col] = 'player_name'
            elif 'position' in col_lower or 'المركز' in col_lower or 'pos' == col_lower:
                column_mapping[col] = 'position'
            elif 'pace' in col_lower or 'السرعة' in col_lower or 'pac' == col_lower:
                column_mapping[col] = 'pace'
            elif 'finishing' in col_lower or 'الإنهاء' in col_lower or 'fin' == col_lower:
                column_mapping[col] = 'finishing'
            elif 'composure' in col_lower or 'الهدوء' in col_lower or 'cmp' == col_lower:
                column_mapping[col] = 'composure'
            elif 'off the ball' in col_lower or 'التحرك بدون كرة' in col_lower or 'otb' == col_lower:
                column_mapping[col] = 'off_the_ball'
            elif 'vision' in col_lower or 'الرؤية' in col_lower or 'vis' == col_lower:
                column_mapping[col] = 'vision'
                
        df = df.rename(columns=column_mapping)
        
        # التأكد من وجود الأعمدة الحساسة
        required_cols = ['player_name', 'position', 'pace', 'finishing', 'composure', 'off_the_ball', 'vision']
        for col in required_cols:
            if col not in df.columns:
                df[col] = 0 if col not in ['player_name', 'position'] else 'Unknown'
                
        # تحويل الأعمدة الرقمية
        for col in ['pace', 'finishing', 'composure', 'off_the_ball', 'vision']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
        print(f"✅ تم استيراد {len(df)} لاعب بنجاح من ملف FM.")
        return df[required_cols]
    except Exception as e:
        print(f"❌ خطأ أثناء قراءة ملف FM: {e}")
        return None

# ==========================================
# 2. طبقة البيانات العميقة (بيانات StatsBomb)
# ==========================================
def fetch_and_process_statsbomb_data():
    """
    تتصل بمستودع StatsBomb المفتوح لسحب مباريات بطولة أمم إفريقيا 2023
    وتحسب المقاييس التكتيكية المعقدة بما في ذلك xA.
    """
    print("⏳ جاري الاتصال بخوادم StatsBomb لسحب بيانات المباريات...")
    
    try:
        # 1. جلب قائمة المباريات المتاحة مجاناً لبطولة أمم إفريقيا (competition_id=1267, season_id=107)
        matches = sb.matches(competition_id=1267, season_id=107)
        
        print(f"✅ تم العثور على {len(matches)} مباراة مجانية لبطولة كأس الأمم الأفريقية. جاري سحب البيانات...")
        
        all_events = []
        for match_id in matches['match_id']:
            events = sb.events(match_id=match_id)
            if 'match_id' not in events.columns:
                events['match_id'] = match_id
            all_events.append(events)
            
        # دمج كل الأحداث في جدول واحد
        events = pd.concat(all_events, ignore_index=True)
    except Exception as e:
        print(f"❌ خطأ في الاتصال بـ StatsBomb: {e}")
        return pd.DataFrame()

    print("✅ تم سحب بيانات الأحداث بنجاح. جاري حساب المقاييس التكتيكية...")

    # حساب الـ Expected Assists (xA) بربط التمريرات بالـ xG للتسديدة الموالية
    if 'type' in events.columns:
        # 1. استخراج التسديدات وقيم الـ xG الخاصة بها
        shots = events[events['type'] == 'Shot'].copy()
        if 'shot_statsbomb_xg' in shots.columns and 'id' in shots.columns:
            shots_xg = shots[['id', 'shot_statsbomb_xg']].rename(
                columns={'id': 'pass_assisted_shot_id', 'shot_statsbomb_xg': 'xA'}
            )
            # 2. دمج الـ xA في جدول الأحداث الرئيسي
            if 'pass_assisted_shot_id' in events.columns:
                events = pd.merge(events, shots_xg, on='pass_assisted_shot_id', how='left')
                events['xA'] = events['xA'].fillna(0)
            else:
                events['xA'] = 0.0
        else:
            events['xA'] = 0.0
    else:
        events['xA'] = 0.0

    # فلترة الأحداث للاعبين فقط
    player_events = events.dropna(subset=['player'])
    
    # قائمة لتخزين إحصائيات كل لاعب
    player_stats = []
    
    # تجميع الأحداث لكل لاعب
    grouped = player_events.groupby('player')
    
    for player_name, data in grouped:
        # 1. حساب التسديدات والأهداف المتوقعة (xG)
        shots = data[data['type'] == 'Shot']
        total_xg = shots['shot_statsbomb_xg'].sum() if 'shot_statsbomb_xg' in shots.columns else 0
        
        # 2. حساب الصناعة المتوقعة (xA)
        total_xa = data['xA'].sum() if 'xA' in data.columns else 0
        
        # 3. حساب اللعب تحت الضغط (Tight Spaces)
        actions_under_pressure = data[data['under_pressure'] == True]
        total_actions = len(data)
        retention_under_pressure_pct = (len(actions_under_pressure) / total_actions) * 100 if total_actions > 0 else 0
        
        # 4. حساب التمريرات الناجحة تحت الضغط
        passes = data[data['type'] == 'Pass']
        passes_under_pressure = passes[passes['under_pressure'] == True]
        successful_passes_under_pressure = passes_under_pressure[passes_under_pressure['pass_outcome'].isna()]
        
        pass_success_pressure_pct = (len(successful_passes_under_pressure) / len(passes_under_pressure)) * 100 if len(passes_under_pressure) > 0 else 0

        matches_analyzed = data['match_id'].nunique() if 'match_id' in data.columns else 1

        player_stats.append({
            'player_name': player_name,
            'matches_analyzed': matches_analyzed,
            'total_xG': round(total_xg, 2),
            'total_xA': round(total_xa, 2),
            'actions_under_pressure': len(actions_under_pressure),
            'pressure_retention_pct': round(retention_under_pressure_pct, 1),
            'pass_success_under_pressure_pct': round(pass_success_pressure_pct, 1)
        })

    df_sb = pd.DataFrame(player_stats)
    print("✅ تم حساب المقاييس العميقة بنجاح.")
    return df_sb

# ==========================================
# 3. دوال استيراد ملفات CSV ودمج البيانات وتخزينها (CSV Ingestion & Merging)
# ==========================================
def ingest_all_players(file_path):
    """
    T005: استيراد وتجهيز بيانات all_players.csv لعام 2024
    """
    if not os.path.exists(file_path):
        print(f"⚠️ الملف غير موجود: {file_path}")
        return pd.DataFrame()
    df = pd.read_csv(file_path, encoding='latin-1')
    df = df[['Name', 'Position', 'PAC', 'Finishing', 'Composure', 'OVR', 'Positioning', 'Vision']]
    df = map_column_names(df, {
        'Name': 'player_name_raw',
        'Position': 'position_2024',
        'PAC': 'pace_2024',
        'Finishing': 'finishing_2024',
        'Composure': 'composure_2024',
        'OVR': 'overall_rating_2024',
        'Positioning': 'off_the_ball_2024',
        'Vision': 'vision_2024'
    })
    df['norm_name'] = df['player_name_raw'].apply(normalize_player_name)
    df = df.drop_duplicates(subset=['norm_name'])
    return df

def ingest_fc25(file_path):
    """
    T006: استيراد وتجهيز بيانات ea_sports_fc25_full.csv لعام 2025
    """
    if not os.path.exists(file_path):
        print(f"⚠️ الملف غير موجود: {file_path}")
        return pd.DataFrame()
    df = pd.read_csv(file_path, encoding='latin-1')
    df = df[['Name', 'Position', 'Pace', 'Finishing', 'Composure', 'Overall', 'Vision']]
    df = map_column_names(df, {
        'Name': 'player_name_raw',
        'Position': 'position_2025',
        'Pace': 'pace_2025',
        'Finishing': 'finishing_2025',
        'Composure': 'composure_2025',
        'Overall': 'overall_rating_2025',
        'Vision': 'vision_2025'
    })
    df['off_the_ball_2025'] = np.nan
    df['norm_name'] = df['player_name_raw'].apply(normalize_player_name)
    df = df.drop_duplicates(subset=['norm_name'])
    return df

def ingest_oyuncular(file_path):
    """
    T007: استيراد وتجهيز بيانات oyuncular.csv
    """
    if not os.path.exists(file_path):
        print(f"⚠️ الملف غير موجود: {file_path}")
        return pd.DataFrame()
    df = pd.read_csv(file_path, encoding='latin-1')
    df = df[['Name', 'Position', 'Pace']]
    df = map_column_names(df, {
        'Name': 'player_name_raw',
        'Position': 'position_oyuncular',
        'Pace': 'pace_oyuncular'
    })
    df['norm_name'] = df['player_name_raw'].apply(normalize_player_name)
    df = df.drop_duplicates(subset=['norm_name'])
    return df

def ingest_goalkeepers(file_path):
    """
    T007: استيراد وتجهيز بيانات ea_fc26_goalkeepers.csv
    """
    if not os.path.exists(file_path):
        print(f"⚠️ الملف غير موجود: {file_path}")
        return pd.DataFrame()
    df = pd.read_csv(file_path, encoding='latin-1')
    def build_gk_name(row):
        common = row.get('commonName')
        if pd.notna(common) and str(common).strip() != "":
            return str(common).strip()
        first = row.get('firstName', '')
        last = row.get('lastName', '')
        return f"{first} {last}".strip()
        
    df['player_name_raw'] = df.apply(build_gk_name, axis=1)
    df = df[['player_name_raw', 'position', 'overallRating']]
    df = map_column_names(df, {
        'position': 'position_gk',
        'overallRating': 'overall_rating_gk'
    })
    df['norm_name'] = df['player_name_raw'].apply(normalize_player_name)
    df = df.drop_duplicates(subset=['norm_name'])
    return df

def merge_csv_datasets(dir_path):
    """
    T008: دمج جداول البيانات باستخدام Pandas outer merge
    """
    df24 = ingest_all_players(os.path.join(dir_path, "all_players.csv"))
    df25 = ingest_fc25(os.path.join(dir_path, "ea_sports_fc25_full.csv"))
    dfoy = ingest_oyuncular(os.path.join(dir_path, "oyuncular.csv"))
    dfgk = ingest_goalkeepers(os.path.join(dir_path, "ea_fc26_goalkeepers.csv"))
    
    # دمج متسلسل
    merged = df24
    if not df25.empty:
        merged = pd.merge(merged, df25, on='norm_name', how='outer', suffixes=('', '_25'))
    if not dfoy.empty:
        merged = pd.merge(merged, dfoy, on='norm_name', how='outer', suffixes=('', '_oy'))
    if not dfgk.empty:
        merged = pd.merge(merged, dfgk, on='norm_name', how='outer', suffixes=('', '_gk'))
        
    # حل اسم اللاعب
    merged['player_name'] = merged['player_name_raw']
    if 'player_name_raw_25' in merged.columns:
        merged['player_name'] = merged['player_name'].fillna(merged['player_name_raw_25'])
    if 'player_name_raw_oy' in merged.columns:
        merged['player_name'] = merged['player_name'].fillna(merged['player_name_raw_oy'])
    if 'player_name_raw_gk' in merged.columns:
        merged['player_name'] = merged['player_name'].fillna(merged['player_name_raw_gk'])
        
    # حل مركز اللاعب
    pos_col = merged['position_2024'] if 'position_2024' in merged.columns else pd.Series(dtype=str)
    if 'position_2025' in merged.columns:
        pos_col = pos_col.fillna(merged['position_2025'])
    if 'position_oyuncular' in merged.columns:
        pos_col = pos_col.fillna(merged['position_oyuncular'])
    if 'position_gk' in merged.columns:
        pos_col = pos_col.fillna(merged['position_gk'])
    merged['position'] = pos_col.fillna('Unknown')
    
    # T009: هندسة الميزات وحساب overall_rating والخصائص الأساسية والتاريخية
    ovr_col = merged['overall_rating_2024'] if 'overall_rating_2024' in merged.columns else pd.Series(dtype=float)
    if 'overall_rating_2025' in merged.columns:
        ovr_col = merged['overall_rating_2025'].fillna(ovr_col)
    if 'overall_rating_gk' in merged.columns:
        ovr_col = ovr_col.fillna(merged['overall_rating_gk'])
    merged['overall_rating'] = ovr_col.fillna(60).astype(int)
    
    # حل الخصائص
    # السرعة
    pace_col = merged['pace_2025'] if 'pace_2025' in merged.columns else pd.Series(dtype=float)
    if 'pace_2024' in merged.columns:
        pace_col = pace_col.fillna(merged['pace_2024'])
    if 'pace_oyuncular' in merged.columns:
        pace_col = pace_col.fillna(merged['pace_oyuncular'])
    merged['pace'] = pace_col.fillna(0).astype(int)
    
    # الإنهاء
    fin_col = merged['finishing_2025'] if 'finishing_2025' in merged.columns else pd.Series(dtype=float)
    if 'finishing_2024' in merged.columns:
        fin_col = fin_col.fillna(merged['finishing_2024'])
    merged['finishing'] = fin_col.fillna(0).astype(int)
    
    # الهدوء
    comp_col = merged['composure_2025'] if 'composure_2025' in merged.columns else pd.Series(dtype=float)
    if 'composure_2024' in merged.columns:
        comp_col = comp_col.fillna(merged['composure_2024'])
    merged['composure'] = comp_col.fillna(0).astype(int)
    
    # التحرك بدون كرة
    otb_col = merged['off_the_ball_2025'] if 'off_the_ball_2025' in merged.columns else pd.Series(dtype=float)
    if 'off_the_ball_2024' in merged.columns:
        otb_col = otb_col.fillna(merged['off_the_ball_2024'])
    merged['off_the_ball'] = otb_col.fillna(0).astype(int)
    
    # الرؤية
    vis_col = merged['vision_2025'] if 'vision_2025' in merged.columns else pd.Series(dtype=float)
    if 'vision_2024' in merged.columns:
        vis_col = vis_col.fillna(merged['vision_2024'])
    merged['vision'] = vis_col.fillna(0).astype(int)
    
    # ملء فراغات الخصائص التاريخية بالقيم 0
    for col in ['pace_2024', 'pace_2025', 'finishing_2024', 'finishing_2025', 'composure_2024', 'composure_2025']:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0).astype(int)
        else:
            merged[col] = 0
            
    # حساب نسبة النمو والتطور (النمو السنوي من 2024 إلى 2025)
    def calculate_change(val_prev, val_curr):
        if val_prev > 0 and val_curr > 0:
            return int(val_curr - val_prev)
        return 0
        
    merged['pace_change'] = merged.apply(lambda r: calculate_change(r['pace_2024'], r['pace_2025']), axis=1)
    merged['finishing_change'] = merged.apply(lambda r: calculate_change(r['finishing_2024'], r['finishing_2025']), axis=1)
    
    keep_cols = ['player_name', 'norm_name', 'position', 'overall_rating',
                 'pace', 'pace_2024', 'pace_2025',
                 'finishing', 'finishing_2024', 'finishing_2025',
                 'composure', 'composure_2024', 'composure_2025',
                 'off_the_ball', 'vision', 'pace_change', 'finishing_change']
                 
    return merged[keep_cols]

def build_scouting_database():
    """
    T010: دمج البيانات بالكامل وتخزينها في جدول SQLite
    """
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    DB_DIR = os.path.join(BASE_DIR, 'database')
    
    # 1. جلب البيانات العميقة من StatsBomb
    df_sb = fetch_and_process_statsbomb_data()
    if df_sb.empty:
        print("⚠️ فشل الاتصال بـ StatsBomb. سيتم ملء البيانات العميقة بقيم فارغة لضمان استمرار عمل النظام.")
        df_sb = pd.DataFrame(columns=['player_name', 'matches_analyzed', 'total_xG', 'total_xA', 
                                      'actions_under_pressure', 'pressure_retention_pct', 'pass_success_under_pressure_pct'])
                                      
    df_sb['norm_name'] = df_sb['player_name'].apply(normalize_player_name)
    df_sb = df_sb.drop_duplicates(subset=['norm_name'])
    
    # 2. جلب ودمج بيانات اللاعبين من الـ CSV
    print("⏳ جاري قراءة ودمج ملفات CSV الأربعة...")
    df_csv = merge_csv_datasets(DATA_DIR)
    
    # 3. الدمج الكامل بين CSV و StatsBomb
    print("⏳ جاري الدمج الكامل مع بيانات StatsBomb العميقة...")
    final_df = pd.merge(df_csv, df_sb, on='norm_name', how='outer', suffixes=('', '_sb'))
    
    # حل اسم اللاعب وقسم الموضع
    final_df['player_name'] = final_df['player_name'].fillna(final_df['player_name_sb'])
    final_df['position'] = final_df['position'].fillna('Unknown')
    
    # ملء فراغات الخصائص بقيم افتراضية
    numeric_cols = ['overall_rating', 'pace', 'pace_2024', 'pace_2025', 
                    'finishing', 'finishing_2024', 'finishing_2025', 
                    'composure', 'composure_2024', 'composure_2025', 
                    'off_the_ball', 'vision', 'pace_change', 'finishing_change',
                    'matches_analyzed', 'total_xG', 'total_xA', 
                    'actions_under_pressure', 'pressure_retention_pct', 'pass_success_under_pressure_pct']
                    
    for col in numeric_cols:
        if col in final_df.columns:
            final_df[col] = final_df[col].fillna(0)
        else:
            final_df[col] = 0
            
    # تحويل التنسيقات الرقمية
    for col in ['overall_rating', 'pace', 'pace_2024', 'pace_2025', 
                'finishing', 'finishing_2024', 'finishing_2025', 
                'composure', 'composure_2024', 'composure_2025', 
                'off_the_ball', 'vision', 'pace_change', 'finishing_change',
                'matches_analyzed', 'actions_under_pressure']:
        final_df[col] = final_df[col].astype(int)
        
    for col in ['total_xG', 'total_xA', 'pressure_retention_pct', 'pass_success_under_pressure_pct']:
        final_df[col] = final_df[col].astype(float)
        
    # إسقاط عمود norm_name للحفاظ على قاعدة بيانات نظيفة
    if 'norm_name' in final_df.columns:
        final_df = final_df.drop(columns=['norm_name'])
        
    db_path = os.path.join(DB_DIR, 'openscout_database.db')
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(db_path)
    
    # حفظ الجدول
    final_df.to_sql('players_scouting_data', conn, if_exists='replace', index=False)
    conn.close()
    
    print(f"🎉 تمت العملية بنجاح! تم إنشاء قاعدة البيانات في المسار التالي:\n{db_path}")
    print("\n--- عينة من قاعدة البيانات النهائية (أعلى اللاعبين xG) ---")
    
    sample_view = final_df.sort_values(by='total_xG', ascending=False)
    # استخدام طباعة آمنة لتجنب مشاكل ترميز سطر الأوامر في ويندوز
    try:
        print(sample_view[['player_name', 'position', 'overall_rating', 'pace', 'pace_2024', 'pace_2025', 'total_xG', 'pass_success_under_pressure_pct']].head(12))
    except Exception:
        print("أعلى اللاعبين مسجلين في النظام بنجاح.")

# نقطة إطلاق البرنامج
if __name__ == "__main__":
    print("🚀 بدء تشغيل محرك بيانات OpenScout AI...\n")
    build_scouting_database()