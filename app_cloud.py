import streamlit as st
import streamlit.components.v1 as components
import time
import asyncio
import random
import os
import json
import base64
import db

st.set_page_config(page_title="TOEIC 模擬考試系統 (雲端體驗版)", page_icon="🎓", layout="wide")

# Google Search Console 擁有權驗證標籤
st.markdown('<meta name="google-site-verification" content="8bhBxGk7NWw-ObZUN9rr20dLcguo5gQDaK1pbM4LrB8" />', unsafe_allow_html=True)

st.markdown("""
<style>
/* 隱藏右上角 Share、GitHub、Edit 及選單列 */
#MainMenu { visibility: hidden; display: none !important; }
header { visibility: hidden; display: none !important; }
footer { visibility: hidden; display: none !important; }
[data-testid="stHeader"] { visibility: hidden; display: none !important; }
[data-testid="stToolbar"] { visibility: hidden; display: none !important; }
[data-testid="stDecoration"] { visibility: hidden; display: none !important; }
.stAppHeader { visibility: hidden; display: none !important; }
.stAppToolbar { visibility: hidden; display: none !important; }

/* 徹底隱藏 Streamlit 側邊欄與展開按鈕 */
[data-testid="stSidebar"] { display: none !important; visibility: hidden !important; }
[data-testid="stSidebarNav"] { display: none !important; visibility: hidden !important; }
[data-testid="collapsedControl"] { display: none !important; visibility: hidden !important; }
button[kind="header"] { display: none !important; visibility: hidden !important; }

/* 自動適應系統 Light / Dark 模式 */
@media (prefers-color-scheme: light) {
  .stApp {
    background-color: #f8fafc !important;
    color: #0f172a !important;
  }
}
@media (prefers-color-scheme: dark) {
  .stApp {
    background-color: #0f172a !important;
    color: #f8fafc !important;
  }
}

.stButton>button { background-color: #4C51BF; color: white; border-radius: 6px; }
.stButton>button:hover { background-color: #434190; }
</style>
""", unsafe_allow_html=True)

st.title("🎓 TOEIC 模擬考試系統 (雲端線上測驗版)")
st.markdown("歡迎使用 TOEIC 模擬考試系統！本系統提供精準的擬真多益 8 大題型測驗與單字例句練習。")

# 主頁面切換：2.1 模擬測驗 / 2.2 單字例句練習
main_tab1, main_tab2 = st.tabs(["📝 2.1 模擬測驗", "📚 2.2 單字例句練習"])

import requests

# ═══════════════════════════════════════════════════════════════════════════
# ☁️ Google Drive 資料庫讀取與快取模組
# ═══════════════════════════════════════════════════════════════════════════
def extract_gdrive_id(url_or_id: str) -> str:
    """提取 Google Drive 連結中的 File ID"""
    if not url_or_id: return ""
    url_or_id = url_or_id.strip()
    if "/folders/" in url_or_id:
        try:
            return url_or_id.split("/folders/")[1].split("?")[0].split("/")[0]
        except:
            pass
    if "/d/" in url_or_id:
        try:
            return url_or_id.split("/d/")[1].split("/")[0]
        except:
            pass
    if "id=" in url_or_id:
        try:
            return url_or_id.split("id=")[1].split("&")[0]
        except:
            pass
    return url_or_id

@st.cache_data(ttl=300)
def load_gdrive_json(file_id_or_url: str):
    """從 Google Drive 下載 JSON 檔案並解析 (快取 5 分鐘)"""
    if not file_id_or_url or "/folders/" in file_id_or_url:
        # 專案根目錄/資料夾連結直接切換至專案庫內部檔案讀取
        return None

    file_id = extract_gdrive_id(file_id_or_url)
    if not file_id:
        return None
    
    # Google Drive 直連下載網址
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    try:
        session = requests.Session()
        response = session.get(download_url, timeout=10)
        
        # 處理大檔案的確認提示頁面
        if "confirm=" in response.text or "download_warning" in response.text:
            for key, val in response.cookies.items():
                if key.startswith("download_warning"):
                    download_url += f"&confirm={val}"
                    response = session.get(download_url, timeout=10)
                    break

        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[Google Drive Load Error]: {e}")
    return None

# 🔑 Google Drive API 金鑰設定 (請貼入您的 Google Drive API Key)
# GDRIVE_API_KEY = st.secrets.get("GDRIVE_API_KEY", "")
GDRIVE_API_KEY = "AIzaSyD5fF2wPzk7xhJE7v3G8k2UqK2W7eW9Uss"


@st.cache_data(ttl=3600)
def load_gdrive_audio_map(folder_url: str = "", api_key: str = ""):
    """強大解析器：優先載入語音索引檔，並支援 Google Drive API v3 動態深度提取」"""
    # 0. 優先載入隨專案庫提交的 17,290 個原聲音檔全量索引檔
    local_map_path = os.path.join("vocabulary", "audio_gdrive_map.json")
    root_map_path = "audio_gdrive_map.json"
    
    target_path = None
    if os.path.exists(root_map_path):
        target_path = root_map_path
    elif os.path.exists(local_map_path):
        target_path = local_map_path
        
    if target_path:
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception as e:
            print(f"[Local Audio Map Load Error]: {e}")

    folder_id = extract_gdrive_id(folder_url)
    if not folder_id:
        return {}
    
    audio_map = {}
    session = requests.Session()

    # 1. 優先使用 Google Drive API v3 進行 2 階段 100% 深度掃描
    if api_key:
        try:
            q_root = f"'{folder_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
            url_root = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(q_root)}&fields=files(id,name)&pageSize=100&key={api_key}"
            r_root = session.get(url_root, timeout=10)
            if r_root.status_code == 200:
                subfolders = r_root.json().get("files", [])
                for subfolder in subfolders:
                    sf_id = subfolder["id"]
                    page_token = None
                    while True:
                        q_sub = f"'{sf_id}' in parents and trashed = false"
                        url_sub = f"https://www.googleapis.com/drive/v3/files?q={requests.utils.quote(q_sub)}&fields=nextPageToken,files(id,name)&pageSize=1000&key={api_key}"
                        if page_token:
                            url_sub += f"&pageToken={page_token}"
                        r_sub = session.get(url_sub, timeout=10)
                        if r_sub.status_code != 200:
                            break
                        data = r_sub.json()
                        for f in data.get("files", []):
                            if f.get("name", "").endswith(".mp3"):
                                clean_f_name = f["name"].replace("\\", "/").split("/")[-1].strip().lower()
                                audio_map[clean_f_name] = f["id"]
                        page_token = data.get("nextPageToken")
                        if not page_token:
                            break
            if audio_map:
                print(f"[GDrive API] Successfully mapped {len(audio_map)} mp3 files via API!")
                return audio_map
        except Exception as e:
            print(f"[GDrive API 2-step Error]: {e}")

    # 2. 備選：從網頁 HTML/JS 提取
    try:
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        resp = session.get(url, timeout=12)
        if resp.status_code == 200:
            import re
            pattern = r'\["([a-zA-Z0-9_-]{25,50})",\s*\[?"([^"]+\.mp3)"'
            matches = re.findall(pattern, resp.text)
            for file_id, filename in matches:
                clean_name = filename.replace("\\", "/").split("/")[-1].strip().lower()
                audio_map[clean_name] = file_id
            pattern_alt = r'"([^"]+\.mp3)"[^\}]{1,120}?"([a-zA-Z0-9_-]{25,50})"'
            matches_alt = re.findall(pattern_alt, resp.text)
            for filename, file_id in matches_alt:
                clean_name = filename.replace("\\", "/").split("/")[-1].strip().lower()
                if clean_name not in audio_map:
                    audio_map[clean_name] = file_id
    except Exception as e:
        print(f"[GDrive Audio Map Error]: {e}")
    return audio_map

def resolve_audio_source(path_str: str, audio_map: dict):
    """判斷音檔來源：回傳 (type, value)"""
    if not path_str:
        return (None, None)
    if os.path.exists(path_str):
        return ("local", path_str)
    
    clean_filename = path_str.replace("\\", "/").split("/")[-1].strip().lower()
    if clean_filename in audio_map:
        file_id = audio_map[clean_filename]
        # 使用 Google 高速媒體 CDN 直網址，100% 支援全瀏覽器免 API Key 跨域播放
        return ("gdrive_url", f"https://lh3.googleusercontent.com/d/{file_id}")
    return (None, None)

# ☁️ 雲端專案根目錄 (TOEIC_simulation/):
# https://drive.google.com/drive/folders/1TyQm_WFj2ibibiYUAnWuzipLtft-BzPR?usp=drive_link
# 
# ⚠️ 注意：根目錄下兩個資料庫位於完全不同的子資料夾中，請填寫各自對應的「單一檔案」分享 ID/連結：
# 1. 模擬試題庫相對路徑：TOEIC_simulation/TOEIC_App/public/data/db.json
DEFAULT_EXAM_GDRIVE = ""

# 2. 單字例句庫相對路徑：TOEIC_simulation/vocabulary/sentences_cache.json
DEFAULT_VOCAB_GDRIVE = "https://drive.google.com/file/d/1aAqRod-aQcelluM-ke5ky2oHbsIbO8_S/view?usp=drive_link"

# 3. 語音檔雲端資料夾：TOEIC_simulation/vocabulary/audio/
DEFAULT_AUDIO_FOLDER_GDRIVE = "https://drive.google.com/drive/folders/1RdujqiKbwnBNBqnH6pxu-D71rCt8i-Qg?usp=drive_link"

gdrive_db_id = DEFAULT_EXAM_GDRIVE
gdrive_vocab_id = DEFAULT_VOCAB_GDRIVE

# ═══════════════════════════════════════════════════════════════════════════
# 📚 功能 2.2：單字例句練習
# ═══════════════════════════════════════════════════════════════════════════
with main_tab2:
    if st.button("🔄 立即重新整理雲端資料庫 (清除快取)", use_container_width=True, key="clear_cache_main"):
        st.cache_data.clear()
        st.success("✅ 已清除快取，重新載入最新資料庫！")
        st.rerun()

    _SENTENCES_PATH = os.path.join("vocabulary", "sentences_cache.json")
    sentences_db = {}
    
    # 讀取 Google Drive 音檔資料夾映射表 (支援 API Key 遞迴掃描)
    gdrive_audio_map = load_gdrive_audio_map(DEFAULT_AUDIO_FOLDER_GDRIVE, api_key=GDRIVE_API_KEY)
    
    # 優先嘗試從 Google Drive 讀取單字庫
    if gdrive_vocab_id:
        gdrive_vocab_data = load_gdrive_json(gdrive_vocab_id)
        if gdrive_vocab_data:
            sentences_db = gdrive_vocab_data
            st.info("☁️ 已成功連結並讀取 Google Drive 單字例句庫！")

    # 備選：從本地檔案讀取
    if not sentences_db and os.path.exists(_SENTENCES_PATH):
        with open(_SENTENCES_PATH, "r", encoding="utf-8") as _sf:
            sentences_db = json.load(_sf)

    def _get_autoplay_html(s_list, start_idx=0, interval=1.5):
        playlist = []
        for item in s_list:
            en = item.get("sentence_en", "")
            zh = item.get("sentence_zh", "")
            
            # 優先嘗試尋找可用音檔來源
            chosen = None
            chosen_src = (None, None)
            if item.get("audio_en_variants"):
                for v in item["audio_en_variants"]:
                    src = resolve_audio_source(v.get("path"), gdrive_audio_map)
                    if src[0]:
                        chosen = v
                        chosen_src = src
                        break
            
            en_b64 = ""
            en_url = ""
            if chosen_src[0] == "local":
                with open(chosen_src[1], "rb") as f:
                    en_b64 = base64.b64encode(f.read()).decode("ascii")
            elif chosen_src[0] == "gdrive_url":
                en_url = chosen_src[1]
                
            zh_src = resolve_audio_source(item.get("audio_zh"), gdrive_audio_map)
            zh_b64 = ""
            zh_url = ""
            if zh_src[0] == "local":
                with open(zh_src[1], "rb") as f:
                    zh_b64 = base64.b64encode(f.read()).decode("ascii")
            elif zh_src[0] == "gdrive_url":
                zh_url = zh_src[1]
                
            word_en_src = resolve_audio_source(item.get("audio_word_en"), gdrive_audio_map)
            word_en_b64, word_en_url = "", ""
            if word_en_src[0] == "local":
                with open(word_en_src[1], "rb") as f:
                    word_en_b64 = base64.b64encode(f.read()).decode("ascii")
            elif word_en_src[0] == "gdrive_url":
                word_en_url = word_en_src[1]
                
            word_zh_src = resolve_audio_source(item.get("audio_word_zh"), gdrive_audio_map)
            word_zh_b64, word_zh_url = "", ""
            if word_zh_src[0] == "local":
                with open(word_zh_src[1], "rb") as f:
                    word_zh_b64 = base64.b64encode(f.read()).decode("ascii")
            elif word_zh_src[0] == "gdrive_url":
                word_zh_url = word_zh_src[1]

            playlist.append({
                "word": item.get("display", item.get("word", "")),
                "word_zh": item.get("word_zh", ""),
                "en": en,
                "zh": zh,
                "accent": chosen["label"] if chosen else ("Google Drive 原聲" if en_url else "雲端TTS語音"),
                "en_b64": en_b64,
                "en_url": en_url,
                "zh_b64": zh_b64,
                "zh_url": zh_url,
                "word_en_b64": word_en_b64,
                "word_en_url": word_en_url,
                "word_zh_b64": word_zh_b64,
                "word_zh_url": word_zh_url
            })
            
        js_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: white; background: transparent; padding: 0; margin: 0; }}
          .card {{ background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255,255,255,0.18); border-radius: 18px; padding: 1.8rem 2rem; margin: 0.5rem 0; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3); backdrop-filter: blur(10px); }}
          .word {{ font-size: 2.2rem; font-weight: 800; color: #60a5fa; margin-bottom: 0.8rem; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }}
          .word-zh {{ font-size: 1.4rem; color: #fcd34d; font-weight: 600; }}
          .counter {{ float: right; margin-left: auto; font-size: 1.2rem; font-weight: 500; color: #94a3b8; }}
          .en {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; margin-bottom: 1rem; line-height: 1.8; letter-spacing: 0.3px; }}
          .zh {{ font-size: 1.45rem; font-weight: 500; color: #cbd5e1; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 0.9rem; margin-top: 0.6rem; line-height: 1.6; }}
          .btn {{ padding: 10px 24px; border: none; border-radius: 8px; color: white; cursor: pointer; font-size: 1.15rem; font-weight: 600; transition: all 0.2s ease; }}
          .btn-primary {{ background: #3b82f6; }}
          .btn-primary:hover {{ background: #2563eb; }}
          .btn-secondary {{ background: #475569; }}
          .btn-secondary:hover {{ background: #334155; }}
        </style>
        </head>
        <body>
        <div id="container"></div>
        <script>
          const playlist = {json.dumps(playlist)};
          let idx = {start_idx};
          let step = 0;
          let currentAudio = null;
          let isPaused = false;
          let currentTimer = null;
          let currentStepId = 0;
          let wakeLock = null;

          // 1. 螢幕防休眠保護 (Screen Wake Lock API)
          async function requestWakeLock() {{
            try {{
              if ('wakeLock' in navigator) {{
                wakeLock = await navigator.wakeLock.request('screen');
              }}
            }} catch (err) {{
              console.log('Wake Lock error:', err);
            }}
          }}
          requestWakeLock();
          document.addEventListener('visibilitychange', () => {{
            if (wakeLock !== null && document.visibilityState === 'visible') {{
              requestWakeLock();
            }}
          }});

          function clearCurrentStep() {{
            if (currentTimer) {{
              clearTimeout(currentTimer);
              currentTimer = null;
            }}
            if (currentAudio) {{
              currentAudio.onended = null;
              currentAudio.onerror = null;
              currentAudio.pause();
              currentAudio.src = "";
              currentAudio = null;
            }}
          }}

          function render() {{
            clearCurrentStep();
            if(idx >= playlist.length) {{
              document.getElementById('container').innerHTML = `
                <div class='card' style='text-align:center; padding: 2.5rem;'>
                  <h2 style='color:#4ade80; font-size: 2.2rem; margin: 0;'>🎉 所有例句播放完畢！</h2>
                </div>`;
              return;
            }}
            const item = playlist[idx];
            document.getElementById('container').innerHTML = `
              <div class="card">
                <div class="word">
                  📝 ${{item.word}}
                  ${{item.word_zh ? '<span class="word-zh"> - ' + item.word_zh + '</span>' : ''}}
                  <span class="counter">(${{idx+1}}/${{playlist.length}})</span>
                </div>
                <div class="en">🔊 ${{item.en}}</div>
                <div class="zh">💬 ${{item.zh || '（無中文翻譯）'}}</div>
                <div style="margin-top: 18px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                   <div>
                     <button id="btn-pause" class="btn btn-primary">${{isPaused ? "▶ 繼續播放" : "⏸ 暫停"}}</button>
                     <button id="btn-next" class="btn btn-secondary" style="margin-left: 8px;">下一句 ➡</button>
                   </div>
                   <div style="font-size: 0.95rem; color: #38bdf8; display: flex; align-items: center; gap: 10px;">
                      <span>💡 螢幕防休眠保護中</span>
                   </div>
                </div>
              </div>
            `;
            
            document.getElementById('btn-pause').onclick = togglePause;
            document.getElementById('btn-next').onclick = playNext;
            
            step = 0;
            playStep();
          }}

          function togglePause() {{
            isPaused = !isPaused;
            const btn = document.getElementById('btn-pause');
            if (btn) btn.innerText = isPaused ? "▶ 繼續播放" : "⏸ 暫停";
            
            if(isPaused) {{
              if(currentTimer) {{ clearTimeout(currentTimer); currentTimer = null; }}
              if(currentAudio) currentAudio.pause();
            }} else {{
              if(currentAudio) {{
                currentAudio.play().catch(() => playStep());
              }} else {{
                playStep();
              }}
            }}
          }}

          function playNext() {{
            clearCurrentStep();
            idx++;
            render();
          }}

          function playStep() {{
            if(isPaused) return;
            clearCurrentStep();
            
            const stepToken = ++currentStepId;
            const item = playlist[idx];
            if (!item) return;

            let b64 = "";
            let audioUrl = "";

            if (step === 0) {{ b64 = item.word_en_b64; audioUrl = item.word_en_url; }}
            else if (step === 1) {{ b64 = item.word_zh_b64; audioUrl = item.word_zh_url; }}
            else if (step === 2 || step === 4) {{ b64 = item.en_b64; audioUrl = item.en_url; }}
            else if (step === 3) {{ b64 = item.zh_b64; audioUrl = item.zh_url; }}

            let hasFinished = false;
            const triggerNextStepOnce = (delayMs) => {{
              if (hasFinished) return;
              hasFinished = true;
              if (stepToken !== currentStepId || isPaused) return;
              
              currentTimer = setTimeout(() => {{
                if (stepToken !== currentStepId || isPaused) return;
                step++;
                if (step < 5) {{
                  playStep();
                }} else {{
                  playNext();
                }}
              }}, delayMs);
            }};

            const onStepEnd = () => {{
              triggerNextStepOnce({int(interval * 1000)});
            }};

            const targetAudioSrc = b64 ? ("data:audio/mp3;base64," + b64) : audioUrl;

            if (targetAudioSrc) {{
              currentAudio = new Audio(targetAudioSrc);
              currentAudio.onended = onStepEnd;
              currentAudio.onerror = (e) => {{
                console.warn("Audio load error:", e);
                triggerNextStepOnce(200);
              }};
              currentAudio.play().catch((err) => {{
                console.warn("Audio play rejected:", err);
                triggerNextStepOnce(500);
              }});
            }} else {{
              triggerNextStepOnce(0);
            }}
          }}
          
          render();
        </script>
        </body>
        </html>
        """
        return js_code

    if sentences_db:
        st.subheader("📚 單字例句隨機朗讀與特訓")
        sent_themes = list(sentences_db.keys())
        sel_theme = st.selectbox("選擇主題：", sent_themes, key="sent_theme_sel_cloud")

        col_a, col_b = st.columns([3, 1])
        with col_a:
            items_pool  = sentences_db.get(sel_theme, [])
            valid_items = [it for it in items_pool if it.get("sentence_en")]
            mp3_ready_count = sum(1 for it in items_pool if it.get("audio_en_variants") and any(os.path.exists(v["path"]) for v in it["audio_en_variants"]))
            st.caption(f"📖 本主題共 {len(valid_items)} 條單字例句 ({mp3_ready_count} 條備妥實體音檔)")
        with col_b:
            start_practice = st.button("▶ 開始練習", type="primary", key="start_sent_practice_cloud")

        if start_practice:
            if not valid_items:
                st.warning("⚠️ 該主題暫無可練習單字例句。")
            else:
                shuffled = random.sample(valid_items, len(valid_items))
                st.session_state["sent_practice_list"]  = shuffled
                st.session_state["sent_practice_idx"]   = 0
                st.session_state["sent_practice_theme"] = sel_theme

        if (st.session_state.get("sent_practice_list") and
                st.session_state.get("sent_practice_theme") == sel_theme):

            s_list  = st.session_state["sent_practice_list"]
            s_idx   = st.session_state.get("sent_practice_idx", 0)
            total_s = len(s_list)

            auto_play_mode = st.toggle("🔄 開啟連續自動播放模式", value=False, key="sent_autoplay_toggle_cloud")
            
            if auto_play_mode:
                play_interval = st.slider("播放間隔 (秒)", min_value=0.5, max_value=3.0, value=1.0, step=0.1)
                html_code = _get_autoplay_html(s_list, start_idx=s_idx, interval=play_interval)
                components.html(html_code, height=480)
            else:
                st.progress(s_idx / total_s, text=f"第 {s_idx+1} / {total_s} 句")

                if s_idx < total_s:
                    item        = s_list[s_idx]
                    word_disp   = item.get("display", item.get("word", ""))
                    word_zh     = item.get("word_zh", "")
                    sentence_en = item.get("sentence_en", "")
                    sentence_zh = item.get("sentence_zh", "")

                    chosen_variant = None
                    en_audio_target = (None, None)
                    if item.get("audio_en_variants"):
                        for v in item["audio_en_variants"]:
                            src = resolve_audio_source(v.get("path"), gdrive_audio_map)
                            if src[0]:
                                chosen_variant = v
                                en_audio_target = src
                                break

                    zh_audio_target = resolve_audio_source(item.get("audio_zh"), gdrive_audio_map)
                    word_zh_html = f" <span style='font-size:1.4rem;color:#fcd34d;'> - {word_zh}</span>" if word_zh else ""

                    st.markdown(f"""
<div style="background:rgba(15, 23, 42, 0.65);border:1px solid rgba(255,255,255,0.18);
            border-radius:18px;padding:1.8rem 2rem;margin:0.5rem 0;box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);">
  <div style="font-size:2.2rem;font-weight:bold;color:#60a5fa;margin-bottom:0.8rem;">
    📝 {word_disp}{word_zh_html}
  </div>
  <div style="font-size:1.75rem;font-weight:700;color:#f8fafc;margin-bottom:1rem;line-height:1.8;">
    🔊 {sentence_en}
  </div>
  <div style="font-size:1.45rem;color:#cbd5e1;border-top:1px dashed rgba(255,255,255,0.15);
              padding-top:0.9rem;margin-top:0.6rem;line-height:1.6;">
    💬 {sentence_zh if sentence_zh else "（無中文翻譯）"}
  </div>
</div>
""", unsafe_allow_html=True)

                    c_en, c_zh = st.columns(2)
                    with c_en:
                        if en_audio_target[0] == "local":
                            with open(en_audio_target[1], "rb") as _af:
                                st.audio(_af.read(), format="audio/mp3")
                        elif en_audio_target[0] == "gdrive_url":
                            st.audio(en_audio_target[1], format="audio/mp3")
                        else:
                            st.info("⚠️ 該句尚無英文 MP3 音檔")

                    with c_zh:
                        if zh_audio_target[0] == "local":
                            with open(zh_audio_target[1], "rb") as _af:
                                st.audio(_af.read(), format="audio/mp3")
                        elif zh_audio_target[0] == "gdrive_url":
                            st.audio(zh_audio_target[1], format="audio/mp3")
                        else:
                            st.info("⚠️ 該句尚無中文 MP3 音檔")

                    nav1, nav2, nav3 = st.columns([1, 1, 2])
                    with nav1:
                        if st.button("⬅ 上一句", key="sent_prev_cloud", disabled=(s_idx == 0)):
                            st.session_state["sent_practice_idx"] -= 1
                            st.rerun()
                    with nav2:
                        if st.button("下一句 ➡", key="sent_next_cloud", disabled=(s_idx >= total_s - 1)):
                            st.session_state["sent_practice_idx"] += 1
                            st.rerun()
                    with nav3:
                        if st.button("🔀 重新隨機排序", key="sent_reshuffle_cloud"):
                            st.session_state["sent_practice_list"] = random.sample(valid_items, len(valid_items))
                            st.session_state["sent_practice_idx"]  = 0
                            st.rerun()
                else:
                    st.success(f"🎉 本主題 {total_s} 句練習完畢！點選「▶ 開始練習」重新開始。")
    else:
        st.info("💡 尚未檢測到單字例句快取庫。")

# ═══════════════════════════════════════════════════════════════════════════
# 📝 功能 2.1：模擬測驗
# ═══════════════════════════════════════════════════════════════════════════
with main_tab1:
    MODES = {
        "正式": {
            "listening": {"p1": 6, "p2": 25, "p3": 39, "p4": 30},
            "reading": {"p5": 30, "p6": 16, "p7a": 29, "p7b": 25}
        },
        "模擬": {
            "listening": {"p1": 3, "p2": 13, "p3": 21, "p4": 15},
            "reading": {"p5": 15, "p6": 8, "p7a": 15, "p7b": 13}
        },
        "簡短": {
            "listening": {"p1": 2, "p2": 8, "p3": 13, "p4": 10},
            "reading": {"p5": 10, "p6": 5, "p7a": 10, "p7b": 8}
        }
    }

    selected_mode = st.radio("選擇測驗模式：", ["正式", "模擬", "簡短"], horizontal=True, key="mode_sel_cloud")
    m = MODES[selected_mode]
    total_l = sum(m["listening"].values())
    total_r = sum(m["reading"].values())

    col1, col2, col3 = st.columns(3)
    col1.metric("總題數", f"{total_l + total_r} 題")
    col2.metric("聽力題數 (P1-P4)", f"{total_l} 題")
    col3.metric("閱讀題數 (P5-P7)", f"{total_r} 題")

    st.divider()

    _PUBLISHED_DB_PATH = os.path.join("TOEIC_App", "public", "data", "db.json")

    @st.cache_data(ttl=60)
    def _load_published_db():
        # 1. 優先嘗試從 Google Drive 讀取試題庫
        if gdrive_db_id:
            gdrive_data = load_gdrive_json(gdrive_db_id)
            if gdrive_data:
                return gdrive_data
                
        # 2. 備選：從本地檔案讀取
        if os.path.exists(_PUBLISHED_DB_PATH):
            with open(_PUBLISHED_DB_PATH, "r", encoding="utf-8") as _f:
                return json.load(_f)
        return None

    def _is_mp3_path(audio_val: str) -> bool:
        return audio_val and audio_val.startswith("/audio/")

    def _mp3_path_to_b64(audio_path: str) -> str:
        full_path = os.path.join("TOEIC_App", "public", audio_path.lstrip("/"))
        if os.path.exists(full_path):
            with open(full_path, "rb") as _f:
                return base64.b64encode(_f.read()).decode("utf-8")
        return ""

    def render_audio(audio_val):
        if not audio_val: return None
        try:
            if _is_mp3_path(audio_val):
                full_path = os.path.join("TOEIC_App", "public", audio_val.lstrip("/"))
                if os.path.exists(full_path):
                    with open(full_path, "rb") as _f:
                        return _f.read()
                return None
            else:
                return base64.b64decode(audio_val)
        except:
            return None

    def render_audio_once_md(audio_val, q_id):
        if not audio_val: return ""
        if _is_mp3_path(audio_val):
            b64 = _mp3_path_to_b64(audio_val)
            if not b64: return f'<p style="color:red;">⚠️ 音檔不存在</p>'
        else:
            b64 = audio_val
        return f'''
        <audio id="{q_id}" controls controlsList="nodownload"
               onended="this.controls=false; this.style.opacity=0.3;" 
               style="width: 100%; height: 40px; margin-bottom: 5px;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        '''

    if st.button("📝 開始模擬測試", type="primary", use_container_width=True, key="start_exam_btn_cloud"):
        for key in list(st.session_state.keys()):
            if str(key).startswith("ans_"): del st.session_state[key]

        published = _load_published_db()
        exam_data = {"listening": {}, "reading": {}}
        parts_map = {
            "listening": ["p1", "p2", "p3", "p4"],
            "reading":   ["p5", "p6", "p7a", "p7b"]
        }

        if published:
            for section, parts in parts_map.items():
                for p in parts:
                    needed = m[section][p]
                    if p in ["p3", "p4"]: needed = max(1, needed // 3)
                    elif p == "p6":       needed = max(1, needed // 4)
                    elif p == "p7a":      needed = max(1, needed // 3)
                    elif p == "p7b":      needed = max(1, needed // 5)
                    pool = published.get(p, [])
                    avail = len(pool)
                    exam_data[section][p] = random.sample(pool, min(avail, needed)) if pool else []
        else:
            for section, parts in parts_map.items():
                for p in parts:
                    needed = m[section][p]
                    if p in ["p3", "p4"]: needed = max(1, needed // 3)
                    elif p == "p6":       needed = max(1, needed // 4)
                    elif p == "p7a":      needed = max(1, needed // 3)
                    elif p == "p7b":      needed = max(1, needed // 5)
                    avail = db.get_available_count(p)
                    exam_data[section][p] = db.get_random_questions(p, needed)
            
        has_any_q = any(exam_data[sec][p] for sec in exam_data for p in exam_data[sec])
        if not has_any_q:
            st.warning("💡 雲端題庫資料庫暫未上傳/同步。請完成題庫上傳後再點選開始測試。")
        else:
            st.session_state['exam_data'] = exam_data
            st.session_state['exam_status'] = 'IN_PROGRESS'
            
            duration_map = {"正式": 120, "模擬": 60, "簡短": 30}
            st.session_state['exam_end_time'] = time.time() + duration_map[selected_mode] * 60
            st.rerun()

    # 測驗進行與結果介面
    if 'exam_data' in st.session_state:
        status = st.session_state.get('exam_status')
        is_completed = (status == 'COMPLETED')
        
        if status == 'IN_PROGRESS':
            time_splits = {"正式": (45, 75), "模擬": (25, 40), "簡短": (15, 25)}
            l_m, r_m = time_splits.get(selected_mode, (45, 75))
            left_sec = int(st.session_state.get('exam_end_time', time.time()) - time.time())
            timer_html = f"""
            <div style="background: #e53e3e; color: white; padding: 12px; border-radius: 8px; font-size: 22px; font-weight: bold; text-align: center; font-family: sans-serif;">
                ⏳ 剩餘時間: <span id="time-display">--:--</span> ( 聽力 {l_m} 分鐘 ｜ 閱讀 {r_m} 分鐘 )
            </div>
            <script>
            var timeLeft = Math.max(0, {left_sec});
            var display = document.getElementById("time-display");
            var timerId = setInterval(function() {{
                if (timeLeft <= 0) {{
                    clearInterval(timerId);
                    display.innerHTML = "00:00 - 時間到！請交卷";
                }} else {{
                    var m = Math.floor(timeLeft / 60);
                    var s = Math.floor(timeLeft % 60);
                    display.innerHTML = (m < 10 ? "0" + m : m) + ":" + (s < 10 ? "0" + s : s);
                    timeLeft -= 1;
                }}
            }}, 1000);
            </script>
            """
            components.html(timer_html, height=60)
            st.markdown("<br>", unsafe_allow_html=True)
            
        d = st.session_state['exam_data']
        
        if is_completed:
            score = st.session_state.get('exam_score', {})
            st.success(f"🎉 測驗結束！您的總得分率為 **{score.get('total', 0):.1f}%**")
            c1, c2 = st.columns(2)
            c1.metric("🎧 聽力正確率", f"{score.get('listening', 0):.1f}%")
            c2.metric("📖 閱讀正確率", f"{score.get('reading', 0):.1f}%")
            st.divider()

        tabL, tabR = st.tabs(["🎧 聽力測驗", "📖 閱讀測驗"])
        
        with tabL:
            # Part 1
            st.header("Part 1: Photographs")
            _IMG_BASE = os.path.join("TOEIC_App", "public")
            for i, q in enumerate(d["listening"].get("p1", [])):
                with st.container(border=True):
                    st.write(f"**Question P1-{i+1}**")
                    img_url = q.get("image_url", "")
                    if img_url:
                        img_file = os.path.join(_IMG_BASE, img_url.lstrip("/"))
                        if os.path.exists(img_file):
                            st.image(img_file, width=640)
                        else:
                            st.info(f"📷 {q.get('image_scenario', '')}")
                    else:
                        st.info(f"📷 {q.get('image_scenario', '')}")

                    if q.get('audio'):
                        if is_completed: st.audio(render_audio(q['audio']), format="audio/mp3")
                        else: st.markdown(render_audio_once_md(q['audio'], f"a_p1_{i}"), unsafe_allow_html=True)
                    opts = q.get('options', ["(A)", "(B)", "(C)", "(D)"])
                    ans_key = f"ans_p1_{i}"
                    st.radio("Your Answer:", opts, key=ans_key, horizontal=True, label_visibility="collapsed", disabled=is_completed)

                    if is_completed:
                        user_ans = st.session_state.get(ans_key)
                        correct_ans = q.get('answer')
                        if str(user_ans).strip() == str(correct_ans).strip(): st.success(f"✅ 您選擇了 {user_ans}，正確！")
                        else: st.error(f"❌ 您選擇了 {user_ans if user_ans else '未作答'}，正確答案為 **{correct_ans}**")
                        with st.expander("核對解答與逐字稿"):
                            st.write(f"正確答案: **{correct_ans}**")
                            for opts_key, opts_val in q.get('full_statements', {}).items():
                                if str(correct_ans).strip() in opts_key:
                                    st.markdown(f"**{opts_key}** {opts_val} &nbsp;✅")
                                else:
                                    st.markdown(f"**{opts_key}** {opts_val}")
            
            # Part 2
            st.header("Part 2: Question-Response")
            for i, q in enumerate(d["listening"].get("p2", [])):
                with st.container(border=True):
                    st.write(f"**Question P2-{i+1}**")
                    st.info("🎧 請專注聆聽音檔並選出解答：")
                    if q.get('audio'):
                        if is_completed: st.audio(render_audio(q['audio']), format="audio/mp3")
                        else: st.markdown(render_audio_once_md(q['audio'], f"a_p2_{i}"), unsafe_allow_html=True)
                    opts = q.get('options', ["(A)", "(B)", "(C)"])
                    ans_key = f"ans_p2_{i}"
                    st.radio("Your Answer:", opts, key=ans_key, horizontal=True, label_visibility="collapsed", disabled=is_completed)
                    
                    if is_completed:
                        user_ans = st.session_state.get(ans_key)
                        correct_ans = q.get('answer')
                        if str(user_ans).strip() == str(correct_ans).strip(): st.success(f"✅ 您選擇了 {user_ans}，正確！")
                        else: st.error(f"❌ 您選擇了 {user_ans if user_ans else '未作答'}，正確答案為 **{correct_ans}**")
                        with st.expander("核對解答與逐字稿"):
                            st.write(f"👉 **對白:** {q.get('transcript')}")
                            st.write(f"🎯 **正確答案:** **{correct_ans}**")
                        
            # Part 3 / 4
            parts = [("Part 3: Conversations", "p3"), ("Part 4: Talks", "p4")]
            for title, key in parts:
                st.header(title)
                for i, clip in enumerate(d["listening"].get(key, [])):
                    with st.container(border=True):
                        st.write(f"**Audio Section {i+1}**")
                        if clip.get('audio'):
                            if is_completed: st.audio(render_audio(clip['audio']), format="audio/mp3")
                            else: st.markdown(render_audio_once_md(clip['audio'], f"a_{key}_{i}"), unsafe_allow_html=True)
                        
                        for j, q in enumerate(clip.get("questions", [])):
                            st.write(f"**Q{j+1}.** {q.get('question_text')}")
                            ans_key = f"ans_{key}_{i}_{j}"
                            st.radio("Ans:", q.get('options', []), key=ans_key, horizontal=True, label_visibility="collapsed", disabled=is_completed)
                            
                            if is_completed:
                                user_ans = st.session_state.get(ans_key)
                                correct_ans = q.get('answer')
                                if str(user_ans).strip() == str(correct_ans).strip(): st.success(f"✅ **{correct_ans}**")
                                else: st.error(f"❌ {user_ans if user_ans else '未作答'} (應為 **{correct_ans}**)")

        with tabR:
            # Part 5
            st.header("Part 5: Incomplete Sentences")
            for i, q in enumerate(d["reading"].get("p5", [])):
                with st.container(border=True):
                    st.write(f"**Q5-{i+1}.** {q.get('question_text')}")
                    ans_key = f"ans_p5_{i}"
                    st.radio("Ans:", q.get('options', []), key=ans_key, horizontal=True, label_visibility="collapsed", disabled=is_completed)
                    
                    if is_completed:
                        user_ans = st.session_state.get(ans_key)
                        correct_ans = q.get('answer')
                        if str(user_ans).strip() == str(correct_ans).strip(): st.success(f"✅ 正確！")
                        else: st.error(f"❌ 正確答案為 **{correct_ans}**")
                        
            # Part 6
            st.header("Part 6: Text Completion")
            for i, passage in enumerate(d["reading"].get("p6", [])):
                st.warning(f"Passage {i+1}")
                st.write(passage.get("text", "").replace("\n", "\n\n"))
                for j, q in enumerate(passage.get("questions", [])):
                    with st.container(border=True):
                        st.write(f"**[Blank {q.get('blank_number', j+1)}]**")
                        ans_key = f"ans_p6_{i}_{j}"
                        st.radio("Ans:", q.get('options', []), key=ans_key, label_visibility="collapsed", disabled=is_completed)
                        
                        if is_completed:
                            user_ans = st.session_state.get(ans_key)
                            correct_ans = q.get('answer')
                            if user_ans == correct_ans: st.success(f"✅ **{correct_ans}**")
                            else: st.error(f"❌ 正確答案為 **{correct_ans}**")

            # Part 7
            st.header("Part 7: Reading Comprehension")
            p7_sections = [("Part 7A (Single)", "p7a"), ("Part 7B (Multiple)", "p7b")]
            for title, key in p7_sections:
                st.subheader(title)
                for i, p_set in enumerate(d["reading"].get(key, [])):
                    st.info(f"Reading Set {i+1}")
                    st.markdown(p_set.get("passage_text", "").replace("\n", "\n\n"))
                    
                    for j, q in enumerate(p_set.get("questions", [])):
                        with st.container(border=True):
                            st.write(f"**Q{j+1}.** {q.get('question_text')}")
                            ans_key = f"ans_{key}_{i}_{j}"
                            st.radio("Ans:", q.get('options', []), key=ans_key, label_visibility="collapsed", disabled=is_completed)
                            
                            if is_completed:
                                user_ans = st.session_state.get(ans_key)
                                correct_ans = q.get('answer')
                                if str(user_ans).strip() == str(correct_ans).strip(): st.success(f"✅ **{correct_ans}**")
                                else: st.error(f"❌ 正確答案為 **{correct_ans}**")

        if status == 'IN_PROGRESS':
            st.divider()
            if st.button("📝 交卷並查看成績", use_container_width=True, type="primary", key="submit_exam_cloud"):
                corr_l = 0
                tot_l = 0
                for pk in ["p1", "p2"]:
                    for i, q in enumerate(d["listening"].get(pk, [])):
                        tot_l += 1
                        ans_key = f"ans_{pk}_{i}"
                        if str(st.session_state.get(ans_key)).strip() == str(q.get('answer')).strip(): corr_l += 1
                        
                for pk in ["p3", "p4"]:
                    for i, clip in enumerate(d["listening"].get(pk, [])):
                        for j, q in enumerate(clip.get("questions", [])):
                            tot_l += 1
                            ans_key = f"ans_{pk}_{i}_{j}"
                            if str(st.session_state.get(ans_key)).strip() == str(q.get('answer')).strip(): corr_l += 1
                            
                corr_r = 0
                tot_r = 0
                for pk in ["p5"]:
                    for i, q in enumerate(d["reading"].get(pk, [])):
                        tot_r += 1
                        ans_key = f"ans_{pk}_{i}"
                        if str(st.session_state.get(ans_key)).strip() == str(q.get('answer')).strip(): corr_r += 1
                        
                for pk in ["p6"]:
                    for i, passage in enumerate(d["reading"].get(pk, [])):
                        for j, q in enumerate(passage.get("questions", [])):
                            tot_r += 1
                            ans_key = f"ans_{pk}_{i}_{j}"
                            if str(st.session_state.get(ans_key)).strip() == str(q.get('answer')).strip(): corr_r += 1
                            
                for pk in ["p7a", "p7b"]:
                    for i, p_set in enumerate(d["reading"].get(pk, [])):
                        for j, q in enumerate(p_set.get("questions", [])):
                            tot_r += 1
                            ans_key = f"ans_{pk}_{i}_{j}"
                            if str(st.session_state.get(ans_key)).strip() == str(q.get('answer')).strip(): corr_r += 1
                            
                score_data = {
                    "listening": round((corr_l / max(tot_l, 1)) * 100, 1),
                    "reading": round((corr_r / max(tot_r, 1)) * 100, 1),
                    "total": round(((corr_l + corr_r) / max(tot_l + tot_r, 1)) * 100, 1)
                }
                
                st.session_state['exam_score'] = score_data
                st.session_state['exam_status'] = 'COMPLETED'
                st.rerun()
