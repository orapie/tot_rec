# This script converts raw DuRecDial data (in txt format) into structured JSON files for:
# 1. 后台ToT的参考路径 (strategies.json)
# 2. RAG向量库的素材 (knowledge_rag.jsonl)
# 3. 前台话术样本 (chat_samples.jsonl)

import json
import re
import os

def clean_text(text):
    """清理掉 [1] 这种策略标签和首尾空格"""
    if not text: return ""
    return re.sub(r'\[\d+\]\s*', '', text).strip()

def extract_strategy_steps(goal_str):
    """将 goal 字符串解析为步骤列表"""
    # 比如 "[1] 寒暄 --> [2] 问姓名" -> ["寒暄", "问姓名"]
    steps = goal_str.split('-->')
    return [clean_text(s) for s in steps]

def convert_raw_txt(input_path, output_dir='data/processed_data'):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    strategy_list = []    # 存储后台ToT的参考路径
    knowledge_list = []   # 存储RAG向量库的素材
    sample_list = []      # 存储前台话术样本

    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line: continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                print(f"跳过第 {line_num} 行：非标准JSON格式")
                continue

            # --- 1. 提取策略逻辑 (后台ToT参考) ---
            goal_path = extract_strategy_steps(data.get('goal', ''))
            strategy_list.append({
                "situation": data.get('situation', ''),
                "steps": goal_path
            })

            # --- 2. 提取人设与知识 (RAG素材) ---
            profile = data.get('user_profile', {})
            user_name = profile.get('姓名', '用户')
            for key, value in profile.items():
                if value and value != []:
                    # 转化为易于检索的自然语言描述
                    fact = f"{user_name}的{key}是：{value}"
                    knowledge_list.append({
                        "text": fact,
                        "metadata": {"user": user_name, "category": key}
                    })

            # --- 3. 提取对话对 (前台话术范本) ---
            conv = data.get('conversation', [])
            # DuRecDial 格式通常为：[Bot, User, Bot, User...]
            # 我们提取 (User -> Bot) 的对应关系，这是最核心的“话术范本”
            for i in range(1, len(conv) - 1, 2):
                user_say = conv[i]
                bot_say = conv[i+1] # Bot针对User的回复
                
                # 记录Bot此时执行的是第几个策略步骤
                tag_match = re.search(r'\[(\d+)\]', bot_say)
                tag = tag_match.group(1) if tag_match else "unknown"

                sample_list.append({
                    "strategy_step": tag,
                    "user_input": clean_text(user_say),
                    "bot_response": clean_text(bot_say)
                })

    # --- 保存结果 ---
    with open(f'{output_dir}/strategies.json', 'w', encoding='utf-8') as f:
        json.dump(strategy_list, f, ensure_ascii=False, indent=2)

    with open(f'{output_dir}/knowledge_rag.jsonl', 'w', encoding='utf-8') as f:
        for k in knowledge_list:
            f.write(json.dumps(k, ensure_ascii=False) + '\n')

    with open(f'{output_dir}/chat_samples.jsonl', 'w', encoding='utf-8') as f:
        for s in sample_list:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    print(f"🎉 转化完成！输出至 {output_dir} 文件夹。")
    print(f"- 策略数: {len(strategy_list)} | 知识点: {len(knowledge_list)} | 对话范本: {len(sample_list)}")

if __name__ == "__main__":
    # 请确保你的txt文件名正确
    convert_raw_txt('data/raw/train.txt')