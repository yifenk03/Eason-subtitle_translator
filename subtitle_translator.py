#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LM Studio 字幕翻译工具
使用本地LM Studio大语言模型对字幕文件进行智能翻译
支持格式: TXT, SRT, ASS
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import requests
import json
import threading
import re
from datetime import datetime
from queue import Queue
import time

# 尝试导入GPUtil，如果失败则设为None
try:
    import GPUtil
    HAS_GPUtil = True
except ImportError:
    HAS_GPUtil = False


class SubtitleTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LM Studio 字幕翻译工具")
        self.root.geometry("950x800")
        self.root.resizable(True, True)

        # 配置变量
        self.ip_var = tk.StringVar(value="http://127.0.0.1:1234/v1")
        self.temperature_var = tk.StringVar(value="0.3")
        self.max_tokens_var = tk.StringVar(value="4096")
        self.prompt_var = tk.StringVar()
        self.save_path_var = tk.StringVar()
        self.save_format_var = tk.StringVar(value="srt")  # 保存格式
        self.use_same_dir = tk.BooleanVar(value=True)
        self.selected_files = []
        self.selected_model = tk.StringVar()
        self.is_connected = False
        self.model_list = []

        # 处理队列和并发控制
        self.processing_queue = Queue()
        self.is_processing = False
        self.current_processing = False  # 确保同时只有一个任务在执行

        # 默认提示词 - 日语字幕翻译
        self.default_prompt = """你是一个专业的日语字幕翻译助手，专门将日语字幕翻译成自然流畅的中文。请按照以下要求处理字幕翻译：

翻译规则：

## 保留格式：保持原字幕的序号和时间戳完全不变，只翻译日语文本部分

## 标点处理：句末只保留问号，其他标点（句号、感叹号等）一律去除

## 上下文连贯：结合前后字幕内容，确保翻译在语境中通顺合理

## 文风核心：使用口语化、自然的中文表达，符合日常对话习惯"""

        self.prompt_var.set(self.default_prompt)

        # 颜色配置
        self.colors = {
            'primary': '#2563EB',
            'secondary': '#1E40AF',
            'success': '#10B981',
            'warning': '#F59E0B',
            'error': '#EF4444',
            'bg': '#F8FAFC',
            'card': '#FFFFFF',
            'text': '#1E293B',
            'text_secondary': '#64748B',
            'border': '#E2E8F0'
        }

        # 字体配置
        self.fonts = {
            'title': ('Microsoft YaHei', 16, 'bold'),
            'section': ('Microsoft YaHei', 11, 'bold'),
            'body': ('Microsoft YaHei', 10),
            'secondary': ('Microsoft YaHei', 9),
            'log': ('Consolas', 9)
        }

        self.create_widgets()
        self.load_gpu_info()

    def create_widgets(self):
        """创建所有组件"""
        # 主容器
        main_container = tk.Frame(self.root, bg=self.colors['bg'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 标题
        title_label = tk.Label(main_container, text="字幕翻译工具 by EASON",
                              font=self.fonts['title'],
                              fg=self.colors['primary'], bg=self.colors['bg'])
        title_label.pack(pady=(0, 16))

        # 创建卡片式布局
        # 1. 文件选择区域
        self.create_file_section(main_container)

        # 2. LM Studio 连接区域
        self.create_connection_section(main_container)

        # 3. 提示词模板区域
        self.create_prompt_section(main_container)

        # 4. 日志区域
        self.create_log_section(main_container)

        # 5. GPU 信息区域
        self.create_gpu_section(main_container)

    def create_card(self, parent):
        """创建卡片容器"""
        card = tk.Frame(parent, bg=self.colors['card'], relief=tk.FLAT,
                        highlightbackground=self.colors['border'],
                        highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 12))
        return card

    def create_file_section(self, parent):
        """文件选择区域"""
        card = self.create_card(parent)

        # 标题
        header = tk.Frame(card, bg=self.colors['card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text="文件选择", font=self.fonts['section'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        # 文件选择区域 - 左边按钮 + 右边文件显示
        content_frame = tk.Frame(card, bg=self.colors['card'])
        content_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        # 左侧：文件选择按钮（一上一下）
        left_frame = tk.Frame(content_frame, bg=self.colors['card'])
        left_frame.pack(side=tk.LEFT, padx=(0, 16))

        tk.Button(left_frame, text="选择字幕文件", command=self.select_files,
                 bg=self.colors['primary'], fg='white', font=self.fonts['body'],
                 relief=tk.FLAT, padx=16, pady=6).pack(fill=tk.X, pady=(0, 8))

        tk.Button(left_frame, text="选择文件夹", command=self.select_folder,
                 bg=self.colors['secondary'], fg='white', font=self.fonts['body'],
                 relief=tk.FLAT, padx=16, pady=6).pack(fill=tk.X)

        # 右侧：已选文件显示
        right_frame = tk.Frame(content_frame, bg=self.colors['card'])
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.file_label = tk.Label(right_frame, text="未选择任何文件",
                                   font=self.fonts['secondary'], fg=self.colors['text_secondary'],
                                   bg=self.colors['card'], anchor='nw', justify=tk.LEFT,
                                   wraplength=520, height=4)
        self.file_label.pack(fill=tk.BOTH, expand=True, padx=(8, 0))

        # 保存位置和格式设置 - 一行水平显示
        save_frame = tk.Frame(card, bg=self.colors['card'])
        save_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        tk.Checkbutton(save_frame, text="保存到源文件相同目录",
                      variable=self.use_same_dir,
                      bg=self.colors['card'], font=self.fonts['secondary'],
                      command=self.on_save_dir_toggle).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(save_frame, text="指定保存位置", command=self.select_save_dir,
                 bg=self.colors['text_secondary'], fg='white', font=self.fonts['secondary'],
                 relief=tk.FLAT, padx=12, pady=4).pack(side=tk.LEFT, padx=(0, 8))

        self.save_path_entry = tk.Entry(save_frame, textvariable=self.save_path_var,
                                        font=self.fonts['secondary'], state='disabled')
        self.save_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 保存格式选择
        format_frame = tk.Frame(card, bg=self.colors['card'])
        format_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        tk.Label(format_frame, text="保存格式:", font=self.fonts['body'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT, padx=(0, 8))

        format_combo = ttk.Combobox(format_frame, textvariable=self.save_format_var,
                                    font=self.fonts['body'], width=10,
                                    values=['srt', 'ass'], state='readonly')
        format_combo.pack(side=tk.LEFT, padx=(0, 16))

        tk.Label(format_frame, text="(仅影响文本字幕的转换，SRT/ASS原格式保持不变)",
                font=self.fonts['secondary'], fg=self.colors['text_secondary'],
                bg=self.colors['card']).pack(side=tk.LEFT)

        # 开始处理按钮
        btn_frame = tk.Frame(card, bg=self.colors['card'])
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 12))

        self.start_btn = tk.Button(btn_frame, text="开始翻译", command=self.start_processing,
                                  bg=self.colors['success'], fg='white',
                                  font=('Microsoft YaHei', 11, 'bold'),
                                  relief=tk.FLAT, padx=24, pady=8)
        self.start_btn.pack(side=tk.LEFT)

        self.progress_label = tk.Label(btn_frame, text="",
                                       font=self.fonts['secondary'],
                                       fg=self.colors['text_secondary'], bg=self.colors['card'])
        self.progress_label.pack(side=tk.RIGHT)

    def create_connection_section(self, parent):
        """连接设置区域"""
        card = self.create_card(parent)

        header = tk.Frame(card, bg=self.colors['card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text="LM Studio 连接", font=self.fonts['section'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        # IP地址设置 + 连接状态 - 一行水平显示
        top_row = tk.Frame(card, bg=self.colors['card'])
        top_row.pack(fill=tk.X, padx=16, pady=(0, 8))

        # IP地址设置
        tk.Label(top_row, text="API 地址:", font=self.fonts['body'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)
        self.ip_entry = tk.Entry(top_row, textvariable=self.ip_var,
                                 font=self.fonts['body'], width=40)
        self.ip_entry.pack(side=tk.LEFT, padx=(8, 16), fill=tk.X, expand=True)

        # 连接状态
        tk.Button(top_row, text="检测连接", command=self.check_connection,
                 bg=self.colors['primary'], fg='white', font=self.fonts['body'],
                 relief=tk.FLAT, padx=16, pady=6).pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = tk.Label(top_row, text="未检测",
                                     bg=self.colors['card'], fg=self.colors['text_secondary'],
                                     font=self.fonts['body'])
        self.status_label.pack(side=tk.LEFT, padx=(0, 8))

        self.status_indicator = tk.Label(top_row, text="●",
                                        bg=self.colors['card'], fg=self.colors['text_secondary'],
                                        font=('Microsoft YaHei', 14))
        self.status_indicator.pack(side=tk.LEFT)

        # 模型选择
        model_frame = tk.Frame(card, bg=self.colors['card'])
        model_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        tk.Label(model_frame, text="选择模型:", font=self.fonts['body'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        self.model_combo = ttk.Combobox(model_frame, textvariable=self.selected_model,
                                         font=self.fonts['body'], width=40,
                                         state='readonly')
        self.model_combo.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        tk.Button(model_frame, text="刷新模型", command=self.refresh_models,
                 bg=self.colors['secondary'], fg='white', font=self.fonts['secondary'],
                 relief=tk.FLAT, padx=12, pady=4).pack(side=tk.LEFT, padx=(8, 0))

        # 参数设置
        params_frame = tk.Frame(card, bg=self.colors['card'])
        params_frame.pack(fill=tk.X, padx=16, pady=(0, 12))

        # Temperature 设置
        temp_frame = tk.Frame(params_frame, bg=self.colors['card'])
        temp_frame.pack(side=tk.LEFT, padx=(0, 24))

        tk.Label(temp_frame, text="Temperature:", font=self.fonts['body'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        self.temp_entry = tk.Entry(temp_frame, textvariable=self.temperature_var,
                                   font=self.fonts['body'], width=8)
        self.temp_entry.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(temp_frame, text="(0.0-2.0)", font=self.fonts['secondary'],
                fg=self.colors['text_secondary'], bg=self.colors['card']).pack(side=tk.LEFT, padx=(4, 0))

        # Max Tokens 设置
        tokens_frame = tk.Frame(params_frame, bg=self.colors['card'])
        tokens_frame.pack(side=tk.LEFT)

        tk.Label(tokens_frame, text="Max Tokens:", font=self.fonts['body'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        self.tokens_entry = tk.Entry(tokens_frame, textvariable=self.max_tokens_var,
                                     font=self.fonts['body'], width=10)
        self.tokens_entry.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(tokens_frame, text="(单次翻译最大token)", font=self.fonts['secondary'],
                fg=self.colors['text_secondary'], bg=self.colors['card']).pack(side=tk.LEFT, padx=(4, 0))

    def create_prompt_section(self, parent):
        """提示词模板区域"""
        card = self.create_card(parent)

        header = tk.Frame(card, bg=self.colors['card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text="翻译提示词模板", font=self.fonts['section'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        # 提示词文本框
        self.prompt_text = scrolledtext.ScrolledText(card, font=self.fonts['secondary'],
                                                     height=6, wrap=tk.WORD,
                                                     relief=tk.FLAT,
                                                     highlightbackground=self.colors['border'],
                                                     highlightthickness=1)
        self.prompt_text.insert('1.0', self.default_prompt)
        self.prompt_text.pack(fill=tk.X, padx=16, pady=(0, 12))

        # 恢复默认按钮
        tk.Button(card, text="恢复默认模板", command=self.reset_prompt,
                 bg=self.colors['text_secondary'], fg='white', font=self.fonts['secondary'],
                 relief=tk.FLAT, padx=12, pady=4).pack(anchor='e', padx=16, pady=(0, 12))

    def create_log_section(self, parent):
        """日志区域"""
        card = self.create_card(parent)

        header = tk.Frame(card, bg=self.colors['card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text="处理日志", font=self.fonts['section'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(card, font=self.fonts['log'],
                                                   height=10, wrap=tk.WORD,
                                                   relief=tk.FLAT, state='disabled',
                                                   bg='#1E1E1E', fg='#D4D4D4',
                                                   insertbackground='white')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

        # 配置标签颜色
        self.log_text.tag_config('info', foreground='#D4D4D4')
        self.log_text.tag_config('success', foreground='#4EC9B0')
        self.log_text.tag_config('error', foreground='#F48771')
        self.log_text.tag_config('warning', foreground='#CCA700')
        self.log_text.tag_config('time', foreground='#808080')


    def create_gpu_section(self, parent):
        """GPU信息区域"""
        card = self.create_card(parent)

        header = tk.Frame(card, bg=self.colors['card'])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(header, text="GPU 信息", font=self.fonts['section'],
                fg=self.colors['text'], bg=self.colors['card']).pack(side=tk.LEFT)

        # GPU信息标签
        self.gpu_label = tk.Label(card, text="正在检测GPU...",
                                  font=self.fonts['secondary'],
                                  fg=self.colors['text_secondary'], bg=self.colors['card'],
                                  anchor='w', justify=tk.LEFT)
        self.gpu_label.pack(fill=tk.X, padx=16, pady=(0, 12))

        # 启动GPU信息自动更新（每5秒）
        self.update_gpu_info()

    def update_gpu_info(self):
        """更新GPU信息"""
        if not HAS_GPUtil:
            self.gpu_label.config(text="GPUtil未安装 (pip install GPUtil)", fg=self.colors['text_secondary'])
            return

        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                # 计算显存使用百分比
                usage_percent = (gpu.memoryUsed / gpu.memoryTotal) * 100 if gpu.memoryTotal > 0 else 0
                gpu_info = f"GPU: {gpu.name} | 显存: {gpu.memoryTotal}MB (已用: {gpu.memoryUsed}MB, {usage_percent:.1f}% | 可用: {gpu.memoryFree}MB)"
                self.gpu_label.config(text=gpu_info, fg=self.colors['text'])
            else:
                self.gpu_label.config(text="未检测到独立GPU (使用CPU)", fg=self.colors['text_secondary'])
        except Exception as e:
            self.gpu_label.config(text="GPU信息获取失败", fg=self.colors['warning'])

        # 每5秒自动更新一次
        self.root.after(5000, self.update_gpu_info)

    def load_gpu_info(self):
        """加载GPU信息（兼容旧调用）"""
        self.update_gpu_info()

    def select_files(self):
        """选择文件"""
        files = filedialog.askopenfilenames(
            title="选择需要翻译的字幕文件",
            filetypes=[
                ("字幕文件", "*.srt *.ass *.txt"),
                ("SRT字幕", "*.srt"),
                ("ASS字幕", "*.ass"),
                ("TXT文本", "*.txt"),
                ("所有文件", "*.*")
            ]
        )
        if files:
            self.selected_files = list(files)
            self.log(f"已选择 {len(files)} 个文件", 'info')
            self.update_file_label()

    def select_folder(self):
        """选择文件夹"""
        folder = filedialog.askdirectory(title="选择包含字幕文件的文件夹")
        if folder:
            subtitle_files = []
            supported_extensions = ['.srt', '.ass', '.txt']
            for root, dirs, files in os.walk(folder):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in supported_extensions):
                        subtitle_files.append(os.path.join(root, file))

            self.selected_files = subtitle_files
            self.log(f"已选择文件夹: {folder}", 'info')
            self.log(f"找到 {len(subtitle_files)} 个字幕文件", 'info')
            self.update_file_label()

    def update_file_label(self):
        """更新文件显示"""
        if not self.selected_files:
            self.file_label.config(text="未选择任何文件")
            return

        if len(self.selected_files) == 1:
            self.file_label.config(text=f"已选择: {self.selected_files[0]}")
        else:
            self.file_label.config(text=f"已选择 {len(self.selected_files)} 个文件\n" +
                                  "\n".join(self.selected_files[:5]) +
                                  (f"\n... 还有 {len(self.selected_files) - 5} 个文件" if len(self.selected_files) > 5 else ""))

    def on_save_dir_toggle(self):
        """保存目录切换"""
        if self.use_same_dir.get():
            self.save_path_entry.config(state='disabled')
            self.save_path_var.set("")
        else:
            self.save_path_entry.config(state='normal')

    def select_save_dir(self):
        """选择保存目录"""
        folder = filedialog.askdirectory(title="选择保存位置")
        if folder:
            self.save_path_var.set(folder)
            self.use_same_dir.set(False)
            self.save_path_entry.config(state='normal')

    def reset_prompt(self):
        """恢复默认提示词"""
        self.prompt_text.delete('1.0', tk.END)
        self.prompt_text.insert('1.0', self.default_prompt)
        self.log("提示词已恢复为默认值", 'info')

    def log(self, message, level='info'):
        """添加日志"""
        self.log_text.config(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 根据语言设置标签
        if level == 'info':
            prefix = "[INFO]"
        elif level == 'success':
            prefix = "[SUCCESS]"
        elif level == 'error':
            prefix = "[ERROR]"
        elif level == 'warning':
            prefix = "[WARNING]"
        else:
            prefix = "[LOG]"

        self.log_text.insert(tk.END, f"[{timestamp}] ", 'time')
        self.log_text.insert(tk.END, f"{prefix} ", level)
        self.log_text.insert(tk.END, f"{message}\n", level)

        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def check_connection(self):
        """检测连接"""
        ip = self.ip_var.get().strip()
        if not ip:
            self.log("请输入API地址", 'error')
            return

        self.log(f"正在连接 {ip}...", 'info')

        try:
            # 添加 /v1/models 后缀
            if not ip.endswith('/v1'):
                base_url = ip.rstrip('/')
            else:
                base_url = ip.rstrip('/v1').rstrip('/')

            url = f"{base_url}/v1/models"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                self.is_connected = True
                self.status_label.config(text="已连接", fg=self.colors['success'])
                self.status_indicator.config(fg=self.colors['success'])
                self.log("连接成功!", 'success')

                # 解析模型列表
                try:
                    data = response.json()
                    models = data.get('data', [])
                    self.model_list = [m.get('id', 'unknown') for m in models]

                    if self.model_list:
                        self.model_combo['values'] = self.model_list
                        self.selected_model.set(self.model_list[0])
                        self.log(f"找到 {len(self.model_list)} 个模型", 'success')
                        for model in self.model_list:
                            self.log(f"  - {model}", 'info')
                    else:
                        self.log("未找到可用模型", 'warning')

                except json.JSONDecodeError:
                    self.log("模型列表解析失败", 'warning')

            else:
                self.is_connected = False
                self.status_label.config(text=f"连接失败 ({response.status_code})", fg=self.colors['error'])
                self.status_indicator.config(fg=self.colors['error'])
                self.log(f"连接失败: HTTP {response.status_code}", 'error')

        except requests.exceptions.Timeout:
            self.is_connected = False
            self.status_label.config(text="连接超时", fg=self.colors['error'])
            self.status_indicator.config(fg=self.colors['error'])
            self.log("连接超时，请检查LM Studio是否运行", 'error')

        except requests.exceptions.ConnectionError:
            self.is_connected = False
            self.status_label.config(text="无法连接", fg=self.colors['error'])
            self.status_indicator.config(fg=self.colors['error'])
            self.log("无法连接到服务器，请检查LM Studio是否运行", 'error')

        except Exception as e:
            self.is_connected = False
            self.status_label.config(text=f"错误: {str(e)}", fg=self.colors['error'])
            self.status_indicator.config(fg=self.colors['error'])
            self.log(f"连接错误: {str(e)}", 'error')

    def refresh_models(self):
        """刷新模型列表"""
        self.check_connection()

    def get_output_path(self, input_path):
        """获取输出路径"""
        ext = self.save_format_var.get()
        if self.use_same_dir.get():
            base, _ = os.path.splitext(input_path)
            return f"{base}-已翻译.{ext}"
        else:
            folder = self.save_path_var.get()
            filename = os.path.basename(input_path)
            base, _ = os.path.splitext(filename)
            return os.path.join(folder, f"{base}-已翻译.{ext}")

    def parse_srt(self, content):
        """解析SRT字幕"""
        subtitles = []
        blocks = re.split(r'\n\n+', content.strip())

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                # 解析序号
                try:
                    index = int(lines[0].strip())
                except ValueError:
                    continue

                # 解析时间轴
                time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', lines[1])
                if time_match:
                    start_time = time_match.group(1)
                    end_time = time_match.group(2)
                else:
                    continue

                # 解析文本（可能有换行）
                text = '\n'.join(lines[2:])
                subtitles.append({
                    'index': index,
                    'start': start_time,
                    'end': end_time,
                    'text': text
                })

        return subtitles

    def parse_ass(self, content):
        """解析ASS字幕"""
        subtitles = []
        lines = content.strip().split('\n')

        in_events = False
        format_line = None

        for line in lines:
            line = line.strip()

            if line.startswith('[Events]'):
                in_events = True
                continue

            if in_events:
                if line.startswith('Format:'):
                    format_line = line[7:].strip()
                    continue

                if line.startswith('Dialogue:'):
                    if format_line:
                        # 解析Format
                        format_parts = [p.strip() for p in format_line.split(',')]
                        # 解析Dialogue
                        dialogue_content = line[9:].strip()

                        # 使用逗号分隔，但需要处理文本中的逗号
                        parts = []
                        current = ''
                        depth = 0
                        for char in dialogue_content:
                            if char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                            elif char == ',' and depth == 0:
                                parts.append(current.strip())
                                current = ''
                                continue
                            current += char
                        parts.append(current.strip())

                        if len(parts) >= len(format_parts):
                            dialogue_dict = dict(zip(format_parts, parts[:len(format_parts)]))

                            start = dialogue_dict.get('Start', '0:00:00.00')
                            end = dialogue_dict.get('End', '0:00:00.00')
                            text = dialogue_dict.get('Text', '')

                            # 转换时间格式
                            start = self.convert_ass_time_to_srt(start)
                            end = self.convert_ass_time_to_srt(end)

                            subtitles.append({
                                'start': start,
                                'end': end,
                                'text': text,
                                'style': dialogue_dict.get('Style', 'Default'),
                                'original_style': dialogue_dict.get('Style', 'Default')
                            })

        return subtitles

    def convert_ass_time_to_srt(self, ass_time):
        """将ASS时间格式转换为SRT格式"""
        # ASS格式: H:MM:SS.cc (例如 0:01:23.45)
        # SRT格式: HH:MM:SS,mmm (例如 00:01:23,450)
        match = re.match(r'(\d+):(\d{2}):(\d{2})\.(\d{2})', ass_time)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            centiseconds = int(match.group(4))
            milliseconds = centiseconds * 10
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        return ass_time

    def parse_txt(self, content):
        """解析TXT文件（简单按行处理，每4行一组字幕）"""
        subtitles = []
        lines = content.strip().split('\n')

        i = 0
        subtitle_index = 1
        while i < len(lines):
            text_lines = []

            # 收集多行文本直到遇到空行或文件结束
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1

            if text_lines:
                # 生成一个简单的时间轴（每条字幕约3秒）
                start_seconds = (subtitle_index - 1) * 3
                end_seconds = subtitle_index * 3

                start_time = self.format_srt_time(start_seconds)
                end_time = self.format_srt_time(end_seconds)

                subtitles.append({
                    'index': subtitle_index,
                    'start': start_time,
                    'end': end_time,
                    'text': ' '.join(text_lines)
                })
                subtitle_index += 1

            # 跳过空行
            while i < len(lines) and not lines[i].strip():
                i += 1

        return subtitles

    def format_srt_time(self, seconds):
        """将秒数转换为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def detect_format(self, file_path):
        """检测字幕格式"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.srt':
            return 'srt'
        elif ext == '.ass':
            return 'ass'
        elif ext == '.txt':
            return 'txt'
        else:
            # 尝试通过内容检测
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(1024)  # 只读开头部分

                if '--> ' in content:
                    return 'srt'
                elif '[Script Info]' in content or '[V4+ Styles]' in content:
                    return 'ass'
                else:
                    return 'txt'
            except:
                return 'txt'

    def generate_srt(self, subtitles):
        """生成SRT格式字幕"""
        output = []
        for i, sub in enumerate(subtitles, 1):
            output.append(f"{i}")
            output.append(f"{sub['start']} --> {sub['end']}")
            output.append(sub['text'])
            output.append('')
        return '\n'.join(output)

    def generate_ass(self, subtitles, original_content=None):
        """生成ASS格式字幕"""
        # 基本ASS头
        output = [
            '[Script Info]',
            'Title: Translated Subtitles',
            'ScriptType: v4.00+',
            'PlayDepth: 0',
            '',
            '[V4+ Styles]',
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
            'Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1',
            '',
            '[Events]',
            'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
        ]

        for sub in subtitles:
            # 转换时间格式为ASS
            start = self.convert_srt_time_to_ass(sub['start'])
            end = self.convert_srt_time_to_ass(sub['end'])
            text = sub['text'].replace('\n', '\\N')
            output.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return '\n'.join(output)

    def convert_srt_time_to_ass(self, srt_time):
        """将SRT时间格式转换为ASS格式"""
        # SRT格式: HH:MM:SS,mmm
        # ASS格式: H:MM:SS.cc
        match = re.match(r'(\d{2}):(\d{2}):(\d{2}),(\d{3})', srt_time)
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            centiseconds = int(match.group(4)) // 10
            return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
        return srt_time

    def translate_subtitle(self, subtitle_batch, prompt_template):
        """翻译字幕批次"""
        # 构建翻译请求
        # 将字幕组织成便于翻译的格式
        context_lines = []
        for i, sub in enumerate(subtitle_batch):
            context_lines.append(f"[字幕{i+1}] {sub['text']}")

        context_text = '\n'.join(context_lines)

        # 添加前一条和后一条字幕用于上下文
        full_prompt = f"""{prompt_template}

请翻译以下字幕，每条字幕翻译后用"【翻译】"标记：

{context_text}

请按以下格式输出（只输出翻译结果，不要其他说明）：
"""
        for i, _ in enumerate(subtitle_batch):
            full_prompt += f"\n【翻译{i+1}】"

        return full_prompt

    def call_llm(self, prompt):
        """调用大语言模型"""
        ip = self.ip_var.get().strip().rstrip('/')
        url = f"{ip}/chat/completions"

        model_name = self.selected_model.get()

        try:
            temperature = float(self.temperature_var.get())
            temperature = max(0.0, min(2.0, temperature))
        except ValueError:
            temperature = 0.3

        try:
            max_tokens = int(self.max_tokens_var.get())
            max_tokens = max(1, min(8192, max_tokens))
        except ValueError:
            max_tokens = 4096

        timeout_seconds = 300  # 5分钟超时

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        headers = {
            "Content-Type": "application/json"
        }

        full_content = ""
        last_update_time = datetime.now()
        line_count = 0

        for attempt in range(3):
            try:
                response = requests.post(url, json=payload, headers=headers,
                                        timeout=timeout_seconds, stream=True)

                if response.status_code == 200:
                    for line in response.iter_lines():
                        line_count += 1
                        if line:
                            line_text = line.decode('utf-8')
                            # 检查是否是SSE格式
                            if line_text.startswith('data: '):
                                data_str = line_text[6:]
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data = json.loads(data_str)
                                    if 'choices' in data:
                                        delta = data['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            full_content += delta['content']
                                            now = datetime.now()
                                            if (now - last_update_time).total_seconds() >= 3:
                                                self.log(f"翻译中... ({len(full_content)} 字符)", 'info')
                                                last_update_time = now
                                except json.JSONDecodeError as e:
                                    self.log(f"JSON解析错误: {e}, 行内容: {line_text[:100]}", 'warning')
                                    continue
                            # 尝试直接解析JSON（非SSE格式）
                            elif line_text.strip().startswith('{'):
                                try:
                                    data = json.loads(line_text)
                                    if 'choices' in data:
                                        delta = data['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            full_content += delta['content']
                                except:
                                    pass

                    self.log(f"流式响应处理完成，收到 {line_count} 行，解析到 {len(full_content)} 字符", 'info')
                    return full_content
                else:
                    self.log(f"API错误: HTTP {response.status_code}", 'error')
                    return None

            except requests.exceptions.Timeout:
                if attempt < 2:
                    self.log(f"请求超时，重试 ({attempt + 1}/3)...", 'warning')
                else:
                    self.log("请求超时，翻译失败", 'error')
                    return None
            except requests.exceptions.ConnectionError:
                self.log("连接中断", 'error')
                return None
            except Exception as e:
                self.log(f"请求异常: {e}", 'error')
                return None

        return None

    def parse_translation_result(self, result, expected_count):
        """解析翻译结果"""
        translations = []

        if not result:
            self.log("翻译结果为空", 'error')
            return translations

        self.log(f"原始翻译结果长度: {len(result)} 字符", 'info')

        # 保存原始结果到文件用于调试
        try:
            debug_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_translation_result.txt')
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(result)
            self.log(f"原始结果已保存到: {debug_file}", 'info')
        except Exception as e:
            self.log(f"保存调试文件失败: {e}", 'warning')

        # 清理结果 - 移除thinking标签和内容
        result_cleaned = re.sub(r'<\|think\|>[\s\S]*?<\|think\|>', '', result)
        result_cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', result_cleaned, flags=re.IGNORECASE)
        result_cleaned = re.sub(r'<think>[\s\S]*?</think>', '', result_cleaned, flags=re.IGNORECASE)

        # 方法1: 尝试匹配 [X] 纯序号格式（无中文）
        pattern1 = r'\[(\d+)\]\s*(.+?)(?=\[\d+\]|$)'
        matches1 = re.findall(pattern1, result_cleaned, re.DOTALL)
        if matches1 and len(matches1) >= expected_count // 2:
            self.log(f"使用格式1 [X]解析到 {len(matches1)} 条", 'info')
            for match in matches1:
                translations.append(match[1].strip())
            if len(translations) >= expected_count:
                return translations[:expected_count]

        # 方法2: 尝试匹配 【翻译X】 格式
        pattern2 = r'【翻译(\d+)】\s*(.+?)(?=【翻译\d+】|【\d+】|\[\d+\]|$)'
        matches2 = re.findall(pattern2, result_cleaned, re.DOTALL)
        if matches2:
            self.log(f"使用格式2 【翻译X】解析到 {len(matches2)} 条", 'info')
            for match in matches2:
                translations.append(match[1].strip())
            if len(translations) >= expected_count:
                return translations[:expected_count]

        # 方法3: 尝试匹配 【X】 中文括号格式
        pattern3 = r'【(\d+)】\s*(.+?)(?=\【\d+】|【翻译\d+】|\[\d+\]|$)'
        matches3 = re.findall(pattern3, result_cleaned, re.DOTALL)
        if matches3:
            self.log(f"使用格式3 【X】解析到 {len(matches3)} 条", 'info')
            for match in matches3:
                translations.append(match[1].strip())
            if len(translations) >= expected_count:
                return translations[:expected_count]

        # 方法4: 尝试匹配 ^\d+\. 行首数字格式
        pattern4 = r'^\s*(\d+)\.\s*(.+?)$'
        matches4 = re.findall(pattern4, result_cleaned, re.MULTILINE)
        if matches4 and len(matches4) >= expected_count // 2:
            self.log(f"使用格式4 ^X. 解析到 {len(matches4)} 条", 'info')
            for match in matches4:
                translations.append(match[1].strip())
            if len(translations) >= expected_count:
                return translations[:expected_count]

        # 方法5: 纯文本行 - 没有标记的连续行
        if not translations:
            lines = result_cleaned.strip().split('\n')
            for line in lines:
                line = line.strip()
                if len(line) < 2:
                    continue
                # 跳过包含标记的行
                if any(marker in line for marker in ['【', '】', '[', ']', '翻译', '字幕', '以下', '请按', '原文', '时间']):
                    continue
                # 跳过纯标点行
                if re.match(r'^[\s\W]+$', line):
                    continue
                translations.append(line)

        self.log(f"总共解析到 {len(translations)} 条翻译（期望 {expected_count} 条）", 'info')

        return translations[:expected_count] if translations else []

    def process_file(self, file_path):
        """处理单个字幕文件"""
        try:
            self.log(f"正在处理: {file_path}", 'info')

            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                self.log(f"文件为空，跳过: {file_path}", 'warning')
                return False

            # 检测格式
            fmt = self.detect_format(file_path)
            self.log(f"检测到格式: {fmt.upper()}", 'info')

            # 解析字幕
            if fmt == 'srt':
                subtitles = self.parse_srt(content)
            elif fmt == 'ass':
                subtitles = self.parse_ass(content)
            else:  # txt
                subtitles = self.parse_txt(content)

            if not subtitles:
                self.log(f"未能解析字幕，跳过: {file_path}", 'warning')
                return False

            self.log(f"共解析 {len(subtitles)} 条字幕", 'info')

            # 获取提示词
            prompt_template = self.prompt_text.get('1.0', tk.END).strip()

            # 构建翻译提示 - 一次性发送所有字幕
            self.log("正在发送翻译请求（全部字幕一次性翻译）...", 'info')

            # 构建简洁明确的prompt
            full_prompt = prompt_template + "\n\n请将以下日文字幕翻译成中文，只输出翻译结果，不要解释：\n\n"

            for j, sub in enumerate(subtitles):
                # 简化格式，只保留原文
                full_prompt += f"[{j+1}] {sub['text']}\n"

            full_prompt += "\n\n翻译结果（每行一条，用序号标注）：\n"

            # 调用模型（一次性翻译所有字幕）
            result = self.call_llm(full_prompt)

            if not result:
                self.log("翻译请求失败", 'error')
                return False

            self.log("正在解析翻译结果...", 'info')

            # 输出原始结果的前500字符用于调试
            debug_preview = result[:500] if len(result) > 500 else result
            self.log(f"模型原始输出预览: {debug_preview}...", 'info')

            # 解析结果
            parsed_translations = self.parse_translation_result(result, len(subtitles))

            # 构建翻译后的字幕列表
            translated_subtitles = []
            for j, trans in enumerate(parsed_translations):
                if j < len(subtitles):
                    translated_sub = subtitles[j].copy()
                    translated_sub['text'] = trans.strip() if trans.strip() else subtitles[j]['text']
                    translated_subtitles.append(translated_sub)

            # 如果解析失败或数量太少，保留原文
            if len(translated_subtitles) < len(subtitles) * 0.5:  # 如果解析少于50%
                self.log(f"警告: 只解析到 {len(translated_subtitles)}/{len(subtitles)} 条翻译", 'warning')
                # 补充原文
                for j in range(len(translated_subtitles), len(subtitles)):
                    translated_subtitles.append(subtitles[j].copy())
                # 同时保存原始翻译结果用于调试
                try:
                    output_dir = os.path.dirname(file_path) if self.use_same_dir.get() else self.save_path_var.get()
                    if not output_dir:
                        output_dir = os.path.dirname(file_path)
                    raw_output = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}_raw_translation.txt")
                    with open(raw_output, 'w', encoding='utf-8') as f:
                        f.write(result)
                    self.log(f"原始翻译结果已保存: {raw_output}", 'info')
                except Exception as e:
                    self.log(f"保存原始结果失败: {e}", 'warning')

            # 生成输出
            if not translated_subtitles:
                self.log("没有可用的翻译结果", 'error')
                return False

            # 选择输出格式
            output_format = self.save_format_var.get()

            if output_format == 'srt':
                output_content = self.generate_srt(translated_subtitles)
            else:  # ass
                output_content = self.generate_ass(translated_subtitles)

            # 保存文件
            output_path = self.get_output_path(file_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output_content)

            # 统计翻译成功率
            translated_count = sum(1 for i, sub in enumerate(translated_subtitles)
                                   if i < len(parsed_translations) and parsed_translations[i].strip())
            self.log(f"翻译完成: {output_path} ({translated_count}/{len(subtitles)} 条已翻译)", 'success')
            return True

        except FileNotFoundError:
            self.log(f"文件未找到: {file_path}", 'error')
            return False
        except PermissionError:
            self.log(f"权限错误: {file_path}", 'error')
            return False
        except Exception as e:
            self.log(f"处理错误: {str(e)}", 'error')
            return False

    def start_processing(self):
        """开始处理"""
        if not self.selected_files:
            messagebox.showwarning("提示", "请先选择需要翻译的字幕文件或文件夹")
            return

        if not self.is_connected:
            messagebox.showwarning("提示", "请先检测并确认LM Studio已连接")
            return

        if not self.selected_model.get():
            messagebox.showwarning("提示", "请选择一个模型")
            return

        # 禁用开始按钮
        self.start_btn.config(state='disabled', text="处理中...")
        self.progress_label.config(text="")

        # 在新线程中处理（串行处理，一次只处理一个文件）
        thread = threading.Thread(target=self._process_files_thread)
        thread.daemon = True
        thread.start()

    def _process_files_thread(self):
        """处理文件线程（串行执行）"""
        total = len(self.selected_files)
        success = 0

        self.log("=" * 50, 'info')
        self.log(f"开始翻译 {total} 个文件（串行处理）", 'info')
        self.log("注意: 每次只处理一个文件，确保模型调用次数为1", 'info')
        self.log("=" * 50, 'info')

        for i, file_path in enumerate(self.selected_files, 1):
            self.root.after(0, lambda i=i, t=total: self.progress_label.config(text=f"进度: {i}/{t}"))
            if self.process_file(file_path):
                success += 1

        self.root.after(0, self._processing_complete, total, success)

    def _processing_complete(self, total, success):
        """处理完成"""
        self.start_btn.config(state='normal', text="开始翻译")
        self.progress_label.config(text="")

        self.log("=" * 50, 'info')
        self.log(f"处理完成! 成功: {success}/{total}", 'success' if success == total else 'warning')
        self.log("=" * 50, 'info')

        messagebox.showinfo("完成", f"处理完成!\n成功: {success}/{total}\n失败: {total - success}/{total}")


def main():
    """主函数"""
    root = tk.Tk()

    # 设置窗口图标（如果有的话）
    try:
        root.iconbitmap('icon.ico')
    except:
        pass

    app = SubtitleTranslatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
