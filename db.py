import json
import os
import random

DB_DIR = "db"

def _get_file_path(part_key):
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    return os.path.join(DB_DIR, f"{part_key}.json")

def save_questions(part_key, new_questions):
    """將新生出的題目儲存（附加）到對應的 JSON 檔案中。"""
    if not new_questions:
        return

    file_path = _get_file_path(part_key)
    existing_data = []
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            pass
            
    # 追加題目
    existing_data.extend(new_questions)
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

def get_random_questions(part_key, count):
    """從題庫隨機挑選指定數量的題目。若數量不足將全數回傳。"""
    file_path = _get_file_path(part_key)
    
    if not os.path.exists(file_path):
        return []
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    except json.JSONDecodeError:
        return []
        
    if len(existing_data) <= count:
        return random.sample(existing_data, len(existing_data))
        
    return random.sample(existing_data, count)

def get_available_count(part_key):
    """回傳指定題型目前的本地庫存量。"""
    file_path = _get_file_path(part_key)
    if not os.path.exists(file_path):
        return 0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return len(data)
    except:
        return 0
