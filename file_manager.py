#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件管理工具 - 批量文件筛选和操作工具
支持按文件名关键词搜索、按文件类型筛选，并提供复制/剪切/移动功能
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import platform


class FileManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FileFinder")
        self.root.geometry("900x700")

        # 变量初始化
        self.folder_path = tk.StringVar()
        self.target_folder = tk.StringVar()
        self.file_extensions = []  # 选中的文件扩展名
        self.all_extensions = set()  # 所有检测到的扩展名
        self.found_files = []  # 找到的文件列表
        self.selected_files = []  # 用户选中的文件

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

        # 1. 文件夹选择区域
        folder_frame = ttk.LabelFrame(main_frame, text="源文件夹", padding="10")
        folder_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(1, weight=1)

        ttk.Label(folder_frame, text="路径:").grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Entry(folder_frame, textvariable=self.folder_path, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(folder_frame, text="浏览...", command=self.browse_folder).grid(
            row=0, column=2, padx=5
        )

        # 2. 搜索和筛选区域
        search_frame = ttk.LabelFrame(main_frame, text="搜索和筛选", padding="10")
        search_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        search_frame.columnconfigure(0, weight=1)

        # 关键词输入框（支持多行输入，每行一个关键词）
        keyword_frame = ttk.Frame(search_frame)
        keyword_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)
        keyword_frame.columnconfigure(1, weight=1)

        ttk.Label(keyword_frame, text="关键词(每行一个):").grid(row=0, column=0, sticky=tk.W, padx=5)

        # 创建多行文本框用于输入关键词
        text_frame = ttk.Frame(keyword_frame)
        text_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.keyword_text = tk.Text(text_frame, height=4, width=60)
        scrollbar_keyword = ttk.Scrollbar(text_frame, command=self.keyword_text.yview)
        self.keyword_text.configure(yscrollcommand=scrollbar_keyword.set)

        self.keyword_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar_keyword.pack(side=tk.RIGHT, fill=tk.Y)

        # 扫描按钮
        ttk.Button(keyword_frame, text="扫描文件", command=self.scan_files).grid(
            row=1, column=2, padx=5, sticky=tk.N
        )

        # 文件类型筛选
        ttk.Label(search_frame, text="文件类型筛选:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5
        )
        type_frame = ttk.Frame(search_frame)
        type_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)

        ttk.Button(type_frame, text="全选", command=self.select_all_types).grid(
            row=0, column=0, padx=2
        )
        ttk.Button(type_frame, text="全不选", command=self.deselect_all_types).grid(
            row=0, column=1, padx=2
        )
        ttk.Button(type_frame, text="常用类型", command=self.select_common_types).grid(
            row=0, column=2, padx=2
        )

        # 扩展名复选框容器（动态创建）
        self.extension_checkboxes = {}
        checkbox_frame = ttk.Frame(search_frame)
        checkbox_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.checkbox_container = checkbox_frame

        # 3. 文件列表区域
        list_frame = ttk.LabelFrame(main_frame, text="找到的文件", padding="10")
        list_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # 带滚动条的列表框
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.file_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            yscrollcommand=scrollbar.set,
            height=10,
        )
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)

        # 选择按钮和复制剪贴板按钮
        select_btn_frame = ttk.Frame(list_frame)
        select_btn_frame.grid(row=1, column=0, pady=5)
        ttk.Button(
            select_btn_frame, text="全选", command=self.select_all_files
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            select_btn_frame, text="全不选", command=self.deselect_all_files
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            select_btn_frame, text="反选", command=self.invert_selection
        ).pack(side=tk.LEFT, padx=5)
        
        # 剪贴板操作按钮组
        clipboard_frame = ttk.LabelFrame(list_frame, text="剪贴板操作", padding="5")
        clipboard_frame.grid(row=2, column=0, pady=5, sticky=(tk.W, tk.E))
        
        ttk.Button(
            clipboard_frame, text="复制路径到剪贴板", command=self.copy_paths_to_clipboard
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            clipboard_frame, text="复制文件到剪贴板", command=self.copy_files_to_clipboard
        ).pack(side=tk.LEFT, padx=5)

        # 4. 操作区域
        action_frame = ttk.LabelFrame(main_frame, text="文件操作", padding="10")
        action_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=5)
        action_frame.columnconfigure(1, weight=1)

        ttk.Label(action_frame, text="目标文件夹:").grid(
            row=0, column=0, sticky=tk.W, padx=5
        )
        ttk.Entry(action_frame, textvariable=self.target_folder, width=50).grid(
            row=0, column=1, sticky=(tk.W, tk.E), padx=5
        )
        ttk.Button(action_frame, text="浏览...", command=self.browse_target).grid(
            row=0, column=2, padx=5
        )

        # 操作按钮
        btn_frame = ttk.Frame(action_frame)
        btn_frame.grid(row=1, column=0, columnspan=3, pady=10)

        ttk.Button(
            btn_frame, text="复制到目标文件夹", command=lambda: self.perform_action("copy")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame, text="剪切到目标文件夹", command=lambda: self.perform_action("move")
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame, text="直接移动", command=lambda: self.perform_action("direct_move")
        ).pack(side=tk.LEFT, padx=5)

        # 5. 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN
        )
        status_bar.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)

    def browse_folder(self):
        """浏览选择源文件夹"""
        folder = filedialog.askdirectory(title="选择源文件夹")
        if folder:
            self.folder_path.set(folder)
            self.status_var.set(f"已选择文件夹: {folder}")

    def browse_target(self):
        """浏览选择目标文件夹"""
        folder = filedialog.askdirectory(title="选择目标文件夹")
        if folder:
            self.target_folder.set(folder)
            self.status_var.set(f"已选择目标文件夹: {folder}")

    def scan_files(self):
        """扫描文件夹中的文件"""
        source_folder = self.folder_path.get()

        if not source_folder:
            messagebox.showwarning("警告", "请先选择源文件夹！")
            return

        if not os.path.exists(source_folder):
            messagebox.showerror("错误", "源文件夹不存在！")
            return

        # 获取搜索关键词列表
        keyword_text = self.keyword_text.get("1.0", tk.END).strip()
        keywords = [kw.strip() for kw in keyword_text.split('\n') if kw.strip()] if keyword_text else []

        # 获取选中的文件扩展名
        selected_extensions = [
            ext for ext, var in self.extension_checkboxes.items() if var.get()
        ]

        # 扫描文件
        self.found_files = []
        try:
            for item in os.listdir(source_folder):
                full_path = os.path.join(source_folder, item)

                # 只处理文件
                if not os.path.isfile(full_path):
                    continue

                # 检查文件扩展名
                _, ext = os.path.splitext(item)
                ext = ext.lower()

                # 如果有扩展名筛选且当前文件不在选中列表中，跳过
                if selected_extensions and ext not in selected_extensions:
                    continue

                # 如果没有输入关键词，显示所有文件；否则检查是否包含任意一个关键词
                if keywords:
                    matched = False
                    for keyword in keywords:
                        if keyword.lower() in item.lower():
                            matched = True
                            break
                    if not matched:
                        continue

                self.found_files.append(full_path)

            # 更新文件列表显示
            self.update_file_list()

            # 收集所有扩展名（首次扫描时）
            if not self.all_extensions:
                self.collect_extensions(source_folder)

            self.status_var.set(f"找到 {len(self.found_files)} 个文件")

        except Exception as e:
            messagebox.showerror("错误", f"扫描文件时出错: {str(e)}")

    def collect_extensions(self, folder):
        """收集文件夹中所有的文件扩展名"""
        self.all_extensions.clear()
        for item in os.listdir(folder):
            full_path = os.path.join(folder, item)
            if os.path.isfile(full_path):
                _, ext = os.path.splitext(item)
                ext = ext.lower()
                if ext:
                    self.all_extensions.add(ext)

        # 创建扩展名复选框
        self.create_extension_checkboxes()

    def create_extension_checkboxes(self):
        """创建扩展名复选框"""
        # 清空现有复选框
        for widget in self.checkbox_container.winfo_children():
            widget.destroy()
        self.extension_checkboxes.clear()

        # 按字母排序扩展名
        sorted_extensions = sorted(self.all_extensions)

        # 创建复选框（每行5个）
        row = 0
        col = 0
        for ext in sorted_extensions:
            var = tk.BooleanVar(value=True)  # 默认全选
            cb = ttk.Checkbutton(
                self.checkbox_container, text=ext, variable=var
            )
            cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            self.extension_checkboxes[ext] = var

            col += 1
            if col >= 5:
                col = 0
                row += 1

    def select_all_types(self):
        """全选所有文件类型"""
        for var in self.extension_checkboxes.values():
            var.set(True)

    def deselect_all_types(self):
        """全不选所有文件类型"""
        for var in self.extension_checkboxes.values():
            var.set(False)

    def select_common_types(self):
        """选择常用文件类型"""
        common_types = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp',  # 图片
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',  # 文档
            '.txt', '.csv',  # 文本
            '.mp3', '.mp4', '.avi', '.mkv',  # 媒体
            '.zip', '.rar', '.7z',  # 压缩文件
        }

        for ext, var in self.extension_checkboxes.items():
            var.set(ext in common_types)

    def update_file_list(self):
        """更新文件列表显示"""
        self.file_listbox.delete(0, tk.END)
        for file_path in self.found_files:
            filename = os.path.basename(file_path)
            self.file_listbox.insert(tk.END, filename)

    def select_all_files(self):
        """全选文件"""
        self.file_listbox.select_set(0, tk.END)

    def deselect_all_files(self):
        """全不选文件"""
        self.file_listbox.select_clear(0, tk.END)

    def invert_selection(self):
        """反选文件"""
        current_selection = set(self.file_listbox.curselection())
        total = self.file_listbox.size()

        self.file_listbox.select_clear(0, tk.END)
        for i in range(total):
            if i not in current_selection:
                self.file_listbox.select_set(i)

    def copy_paths_to_clipboard(self):
        """复制选中文件的路径到剪贴板"""
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制路径的文件！")
            return

        # 获取选中文件的路径
        selected_files = [self.found_files[i] for i in selected_indices]
        
        # 将路径用换行符连接
        paths_text = '\n'.join(selected_files)
        
        # 复制到剪贴板
        self.root.clipboard_clear()
        self.root.clipboard_append(paths_text)
        self.root.update()  # 确保剪贴板内容被更新
        
        self.status_var.set(f"已复制 {len(selected_files)} 个文件路径到剪贴板")
        messagebox.showinfo("成功", f"已复制 {len(selected_files)} 个文件路径到剪贴板！\n\n可以直接在其他地方粘贴使用。")

    def copy_files_to_clipboard(self):
        """复制选中文件本体到系统剪贴板"""
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要复制的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]
        
        try:
            system = platform.system()
            
            if system == "Windows":
                self._copy_files_windows(selected_files)
            elif system == "Darwin":  # macOS
                self._copy_files_macos(selected_files)
            else:  # Linux
                self._copy_files_linux(selected_files)
            
            self.status_var.set(f"已复制 {len(selected_files)} 个文件到剪贴板")
            messagebox.showinfo(
                "成功", 
                f"已复制 {len(selected_files)} 个文件到剪贴板！\n\n"
                f"现在可以在其他文件夹中按 Ctrl+V (Mac: Cmd+V) 粘贴文件。"
            )
        except Exception as e:
            messagebox.showerror("错误", f"复制文件到剪贴板失败：{str(e)}")
    
    def _copy_files_windows(self, files):
        """Windows系统：使用PowerShell复制文件到剪贴板"""
        import subprocess
        
        # 使用PowerShell的Set-Clipboard命令
        # 将文件路径用逗号分隔，构建PowerShell命令
        file_paths = ", ".join([f'"{f}"' for f in files])
        powershell_script = f"Set-Clipboard -Path {file_paths}"
        
        result = subprocess.run(
            ["powershell", "-Command", powershell_script],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"PowerShell执行失败: {result.stderr}")
    
    def _copy_files_macos(self, files):
        """macOS系统：使用AppleScript复制文件到剪贴板"""
        import subprocess
        
        # 使用Finder复制文件
        posix_files = ", ".join([f'POSIX file "{f}"' for f in files])
        script = f'''
        tell application "Finder"
            set theFiles to {{{posix_files}}}
            set the clipboard to theFiles
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
    
    def _copy_files_linux(self, files):
        """Linux系统：使用xclip复制文件到剪贴板"""
        import subprocess
        
        # 尝试使用xclip
        try:
            file_uris = "\n".join([f"file://{f}" for f in files])
            proc = subprocess.Popen(
                ['xclip', '-selection', 'clipboard', '-t', 'text/uri-list'],
                stdin=subprocess.PIPE
            )
            proc.communicate(input=file_uris.encode())
            if proc.returncode != 0:
                raise RuntimeError("xclip执行失败")
        except FileNotFoundError:
            raise RuntimeError("需要安装xclip工具（sudo apt-get install xclip）")

    def perform_action(self, action):
        """执行文件操作"""
        target_folder = self.target_folder.get()

        if not target_folder:
            messagebox.showwarning("警告", "请先选择目标文件夹！")
            return

        if not os.path.exists(target_folder):
            messagebox.showerror("错误", "目标文件夹不存在！")
            return

        # 获取选中的文件
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("警告", "请先选择要操作的文件！")
            return

        selected_files = [self.found_files[i] for i in selected_indices]

        # 确认操作
        action_names = {
            "copy": "复制",
            "move": "剪切",
            "direct_move": "直接移动",
        }

        confirm = messagebox.askyesno(
            "确认操作",
            f"确定要{action_names[action]} {len(selected_files)} 个文件到:\n{target_folder} 吗？"
        )

        if not confirm:
            return

        # 执行操作
        success_count = 0
        error_count = 0

        for file_path in selected_files:
            try:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(target_folder, filename)

                if action == "copy":
                    shutil.copy2(file_path, dest_path)
                elif action in ["move", "direct_move"]:
                    shutil.move(file_path, dest_path)

                success_count += 1
            except Exception as e:
                error_count += 1
                print(f"处理文件失败 {filename}: {str(e)}")

        # 显示结果
        result_msg = f"操作完成！\n成功: {success_count} 个文件"
        if error_count > 0:
            result_msg += f"\n失败: {error_count} 个文件"

        messagebox.showinfo("结果", result_msg)
        self.status_var.set(result_msg.replace("\n", ", "))

        # 如果是移动操作，刷新列表
        if action in ["move", "direct_move"]:
            self.scan_files()


def main():
    root = tk.Tk()
    app = FileManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
