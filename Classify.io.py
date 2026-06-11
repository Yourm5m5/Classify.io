import os
import shutil
import time
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

MODEL_NAME = "llama3.2:1b"
BATCH_SIZE = 20  

PROTECTED_KEYWORDS = ["password", "secret", "private", "backup", "vault", "lock"]
PROJECT_MARKERS = [".git", "package.json", "node_modules", ".venv", "venv", "*.sln", "*.xcodeproj"]

# --- THEME CONFIGURATION PARADIGM ---
DARK_BG = "#121824"          # Deep Slate/Black
CARD_BG = "#1d273a"          # Midnight Blue Panel
ACCENT_BLUE = "#007acc"      # Electric Blue Highlight
ACCENT_ACTIVE = "#0098ff"    # Light Hover Blue
TEXT_MAIN = "#f0f4f8"        # Soft White
TEXT_MUTED = "#8a9aad"       # Cool Gray
LOG_BG = "#0a0d14"           # Pitch Black for Terminal Output
ALERT_RED = "#d9534f"        # Abort Button Highlight

class FolderSelectorDialog(tk.Toplevel):
    def __init__(self, parent, folders, base_dir_str, close_event):
        super().__init__(parent)
        self.title("Select Folders to Process")
        self.geometry("680x500")  # Widened to fit paths comfortably
        self.configure(bg=DARK_BG)
        self.transient(parent)
        self.grab_set()
        
        self.folders = folders
        self.base_dir = Path(base_dir_str)
        self.close_event = close_event
        self.result = []

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # --- 1. FIXED BOTTOM BUTTON FRAME ---
        btn_frame = tk.Frame(self, bg=DARK_BG, pady=12, padx=15)
        btn_frame.pack(fill="x", side="bottom")
        
        btn_confirm = tk.Button(
            btn_frame, text="Confirm Selection", command=self.on_confirm,
            font=("Segoe UI", 9, "bold"), bg=ACCENT_BLUE, fg=TEXT_MAIN,
            activebackground=ACCENT_ACTIVE, activeforeground=TEXT_MAIN,
            relief="flat", bd=0, padx=18, pady=7, cursor="hand2"
        )
        btn_confirm.pack(side="right", padx=5)
        
        btn_cancel = tk.Button(
            btn_frame, text="Cancel", command=self.on_cancel,
            font=("Segoe UI", 9), bg=CARD_BG, fg=TEXT_MUTED,
            activebackground=DARK_BG, activeforeground=TEXT_MAIN,
            relief="flat", bd=0, padx=15, pady=7, cursor="hand2"
        )
        btn_cancel.pack(side="right")

        # --- 2. TOP HEADER LABEL ---
        lbl = tk.Label(
            self, 
            text="Choose which folders to scan/extract files from.\nUncheck deep project directories or dependencies you want to bypass completely.",
            font=("Segoe UI", 10), justify="left", bg=DARK_BG, fg=TEXT_MAIN
        )
        lbl.pack(pady=15, padx=15, fill="x", side="top")

        # --- 3. MODERN TREEVIEW DATA CONTAINER ---
        container = tk.Frame(self, bg=DARK_BG)
        container.pack(expand=True, fill="both", padx=15, pady=5)

        # Style the modern list tree view explicitly to force visibility
        style = ttk.Style()
        style.theme_use('clam')  
        
        style.configure("Custom.Treeview", 
                        background=CARD_BG, 
                        foreground=TEXT_MAIN, 
                        fieldbackground=CARD_BG, 
                        rowheight=28,
                        font=("Segoe UI", 9),
                        borderwidth=0)
        
        style.configure("Custom.Treeview.Heading", 
                        font=("Segoe UI", 9, "bold"), 
                        background=DARK_BG, 
                        foreground=ACCENT_BLUE,
                        relief="flat")
        
        style.map("Custom.Treeview.Heading",
                  background=[('active', CARD_BG)],
                  foreground=[('active', ACCENT_BLUE)])

        self.tree = ttk.Treeview(container, columns=("Path", "Status"), style="Custom.Treeview", show="tree headings")
        self.tree.heading("#0", text=" Folder Name", anchor="w")
        self.tree.heading("Path", text=" Relative Location", anchor="w")
        self.tree.heading("Status", text=" Scan Action", anchor="w")
        
        self.tree.column("#0", width=180, minwidth=120)
        self.tree.column("Path", width=320, minwidth=200)
        self.tree.column("Status", width=120, minwidth=100)

        self.tree.tag_configure('clean', foreground=TEXT_MAIN, background=CARD_BG)
        self.tree.tag_configure('project', foreground=ALERT_RED, background=CARD_BG)
        self.tree.tag_configure('ignored', foreground=TEXT_MUTED, background=CARD_BG)

        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        # Populate the tree rows
        for folder_path, is_likely_project in self.folders:
            try:
                rel_path = str(folder_path.relative_to(self.base_dir))
            except Exception:
                rel_path = str(folder_path)

            status_text = "⚠️ Skip (Project)" if is_likely_project else "✅ Scan Folder"
            
            item_id = self.tree.insert("", "end", text=f" {folder_path.name}", values=(rel_path, status_text))
            
            if is_likely_project:
                self.tree.item(item_id, tags=('project',))
            else:
                self.tree.item(item_id, tags=('clean',))

        self.tree.bind("<ButtonRelease-1>", self.toggle_row_status)

    def toggle_row_status(self, event):
        selected_item = self.tree.identify_row(event.y)
        if not selected_item:
            return
        
        current_values = self.tree.item(selected_item, "values")
        if not current_values:
            return
            
        if "Scan Folder" in current_values[1]:
            self.tree.set(selected_item, column="Status", value="❌ Ignored")
            self.tree.item(selected_item, tags=('ignored',))
        else:
            self.tree.set(selected_item, column="Status", value="✅ Scan Folder")
            
            is_project = False
            for folder_path, is_likely_project in self.folders:
                if folder_path.name == self.tree.item(selected_item, "text").strip():
                    is_project = is_likely_project
                    break
                    
            if is_project:
                self.tree.item(selected_item, tags=('project',))
            else:
                self.tree.item(selected_item, tags=('clean',))

    def on_confirm(self):
        self.result = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values and "Scan Folder" in values[1]:
                self.result.append(self.base_dir / values[0])
                
        self.close_event.set()
        self.destroy()

    def on_cancel(self):
        self.result = [] 
        self.close_event.set()
        self.destroy()


class UniversalCleanerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Classify.io")
        self.root.geometry("780x700")
        self.root.minsize(650, 600)
        self.root.configure(bg=DARK_BG)

        self.target_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        
        self.dialog_closed_event = threading.Event()
        self.abort_event = threading.Event()
        self.is_aborted_forcefully = False

        self.staged_moves = []
        self.staged_allowed_folders = []
        self.staged_lock = threading.Lock()

        self.classification_cache = {}

        self.apply_theme_styles()
        self.setup_ui()

    def apply_theme_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Window & Frame Panel styles
        style.configure(".", background=DARK_BG, foreground=TEXT_MAIN, font=("Segoe UI", 10))
        style.configure("TLabelfraw", background=DARK_BG, foreground=TEXT_MAIN)
        style.configure("TLabelFrame", background=DARK_BG, foreground=ACCENT_BLUE, borderwidth=1, relief="solid")
        style.configure("TLabelFrame.Label", font=("Segoe UI", 10, "bold"), foreground=ACCENT_BLUE, background=DARK_BG)
        style.configure("TFrame", background=DARK_BG)
        
        # Input entry style
        style.configure("TEntry", fieldbackground=CARD_BG, foreground=TEXT_MAIN, borderwidth=0, padding=5)
        
        # Horizontal Progress Bar styling
        style.configure("TProgressbar", thickness=12, troughcolor=CARD_BG, background=ACCENT_BLUE, borderwidth=0)
        
        # Scrollbar mapping styling
        style.configure("Vertical.TScrollbar", troughcolor=DARK_BG, background=CARD_BG, borderwidth=0, arrowsize=12)

    def setup_ui(self):
        # Top Directory Panel
        frame_top = ttk.LabelFrame(self.root, text=" Target Directory to Clean ", padding=15)
        frame_top.pack(fill="x", padx=20, pady=15)
        
        self.ent_dir = ttk.Entry(frame_top, textvariable=self.target_dir, font=("Segoe UI", 10))
        self.ent_dir.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        btn_browse = tk.Button(
            frame_top, text="Browse...", command=self.browse_folder,
            font=("Segoe UI", 9, "bold"), bg=CARD_BG, fg=TEXT_MAIN,
            activebackground=ACCENT_BLUE, activeforeground=TEXT_MAIN,
            relief="flat", bd=0, padx=15, pady=5
        )
        btn_browse.pack(side="right")

        frame_options = ttk.Frame(self.root, padding=5)
        frame_options.pack(fill="x", padx=20)
        
        ai_status = "AI Ready (Ollama)" if OLLAMA_AVAILABLE else "Ollama Missing"
        lbl_status = tk.Label(frame_options, text=ai_status, font=("Segoe UI", 9, "italic"), fg=TEXT_MUTED, bg=DARK_BG)
        lbl_status.pack(side="left")

        # Command Action Controls Section
        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(fill="x", padx=20, pady=10)

        self.btn_run = tk.Button(
            self.control_frame, text="⚡ Deep Scan (Dry Run)", command=self.start_scan_thread,
            font=("Segoe UI", 10, "bold"), bg=ACCENT_BLUE, fg=TEXT_MAIN,
            activebackground=ACCENT_ACTIVE, activeforeground=TEXT_MAIN,
            relief="flat", bd=0, pady=10
        )
        self.btn_run.pack(fill="x", pady=5)

        self.btn_apply = tk.Button(
            self.control_frame, text="🚀 Apply Changes Live (Move Files Now)", command=self.start_apply_thread,
            font=("Segoe UI", 10, "bold"), bg="#28a745", fg=TEXT_MAIN, # Rich Success Green for execution
            activebackground="#218838", activeforeground=TEXT_MAIN,
            relief="flat", bd=0, pady=10
        )
        self.btn_apply.pack_forget()

        # Modernized Progress Tracking Module
        self.progress_frame = ttk.Frame(self.control_frame)
        
        self.status_label = tk.Label(self.progress_frame, text="Preparing environment...", font=("Segoe UI", 10, "bold"), fg=TEXT_MAIN, bg=DARK_BG)
        self.status_label.pack(anchor="w", pady=(0, 2))
        
        self.time_label = tk.Label(self.progress_frame, text="", font=("Segoe UI", 9, "italic"), fg=ACCENT_BLUE, bg=DARK_BG)
        self.time_label.pack(anchor="w", pady=(0, 5))
        
        progress_inner_frame = ttk.Frame(self.progress_frame)
        progress_inner_frame.pack(fill="x", expand=True)
        
        self.progress_bar = ttk.Progressbar(progress_inner_frame, mode="indeterminate", length=300)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        self.btn_abort = tk.Button(
            progress_inner_frame, text="Abort Operation", command=self.trigger_abort,
            font=("Segoe UI", 9, "bold"), bg=ALERT_RED, fg=TEXT_MAIN,
            activebackground="#c9302c", activeforeground=TEXT_MAIN,
            relief="flat", bd=0, padx=12, pady=4
        )
        self.btn_abort.pack(side="right")

        # Terminal Output Logging Panel
        frame_log = ttk.LabelFrame(self.root, text=" System Output Log ", padding=10)
        frame_log.pack(expand=True, fill="both", padx=20, pady=(0, 20))
        
        self.log_text = tk.Text(
            frame_log, wrap="word", state="disabled", 
            font=("Consolas", 9), bg=LOG_BG, fg="#a2b4c7", # Sleek terminal color layout
            insertbackground=TEXT_MAIN, relief="flat", highlightthickness=0
        )
        self.log_text.pack(side="left", expand=True, fill="both")
        
        scrollbar = ttk.Scrollbar(frame_log, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def browse_folder(self):
        selected = filedialog.askdirectory(initialdir=self.target_dir.get())
        if selected:
            self.target_dir.set(selected)

    def log(self, message):
        self.root.after(0, self._safe_log, message)

    def _safe_log(self, message):
        try:
            if self.log_text.winfo_exists():
                self.log_text.config(state="normal")
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state="disabled")
        except tk.TclError:
            pass

    def format_time(self, seconds):
        if seconds < 1:
            return "Less than a second"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def show_loading(self, status_text, determinate=False, maximum=100):
        try:
            self.btn_run.pack_forget()
            self.btn_apply.pack_forget()
            self.progress_frame.pack(fill="x", expand=True)
            self.status_label.config(text=status_text)
            self.time_label.config(text="") 
            
            if determinate:
                self.progress_bar.config(mode="determinate", maximum=maximum)
                self.progress_bar["value"] = 0
            else:
                self.progress_bar.config(mode="indeterminate")
                try:
                    self.progress_bar.start(10)
                except tk.TclError:
                    pass
        except tk.TclError:
            pass

    def update_progress(self, current_value, status_text=None, time_text=None):
        try:
            if self.progress_bar.winfo_exists():
                if status_text:
                    self.status_label.config(text=status_text)
                if time_text is not None:
                    self.time_label.config(text=time_text)
                self.progress_bar["value"] = current_value
        except tk.TclError:
            pass

    def hide_loading(self, show_apply_button=False):
        try:
            if self.progress_bar.winfo_exists():
                try:
                    self.progress_bar.stop()
                except tk.TclError:
                    pass
            if self.progress_frame.winfo_exists():
                self.progress_frame.pack_forget()
            if self.btn_run.winfo_exists():
                self.btn_run.pack(fill="x", pady=5)
            if show_apply_button and self.staged_moves and self.btn_apply.winfo_exists():
                self.btn_apply.pack(fill="x", pady=5)
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def trigger_abort(self):
        if self.abort_event.is_set():
            self.log("\n [HARD RESET] Forcing UI unfreeze. Skipping background response verification...")
            self.is_aborted_forcefully = True
            self.staged_moves = []
            self.hide_loading(show_apply_button=False)
        else:
            self.log("\n [ABORT REQUEST] Signal sent. Waiting for active pipeline process block to clear...")
            self.abort_event.set()
            self.btn_abort.config(text=" Force Reset UI Now", bg="#e04440")

    def is_protected(self, path: Path) -> bool:
        name_lower = path.name.lower()
        if any(kw in name_lower for kw in PROTECTED_KEYWORDS) or name_lower.startswith('.'):
            return True
        for part in path.parts:
            if any(kw in part.lower() for kw in PROTECTED_KEYWORDS):
                return True
        return False

    def is_project_folder(self, folder_path: Path) -> bool:
        for marker in PROJECT_MARKERS:
            if list(folder_path.glob(marker)):
                return True
        return False

    def fallback_static_rules(self, filename):
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        fallback_maps = {
            ('png', 'jpg', 'jpeg', 'gif', 'svg', 'bmp', 'tiff'): 'Media/Images',
            ('mp4', 'mkv', 'avi', 'mov', 'flv', 'wmv'): 'Media/Videos',
            ('mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac'): 'Media/Audio',
            ('zip', 'tar', 'gz', 'rar', '7z', 'mrpack', 'iso', 'tgz'): 'Archives',
            ('pdf', 'docx', 'txt', 'xlsx', 'pptx', 'eml', 'csv', 'md', 'epub'): 'Documents',
            ('exe', 'msi', 'dmg', 'pkg', 'deb', 'rpm'): 'Installers_and_Setups',
            ('py', 'js', 'html', 'css', 'json', 'cpp', 'c', 'sh', 'bat', 'go', 'rs'): 'Development/Code',
            ('stl', '3mf', 'step', 'stp', 'f3z', 'catpart', 'dxf', 'dwg', 'obj'): '3D_Models_and_CAD',
            ('gcode', 'bgcode'): '3D_Printing_Gcode'
        }
        for extensions, classification in fallback_maps.items():
            if ext in extensions:
                return classification
        return "Unsorted_Other_Files"

    def ask_ai_batch_prompt(self, filenames_batch):
        if self.abort_event.is_set() or self.is_aborted_forcefully:
            return {}
        
        prompt = (
            "You are a global-scale file system architect optimizing data layouts dynamically.\n"
            "Analyze this list of filenames. Allocate each individual file to a clean, nested target path based on standard paradigms (e.g., 'Documents/Invoices', 'Media/Audio/Sound_Effects', '3D_Models_and_CAD/Mechanical_Parts', 'Installers_and_Setups/Browsers').\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "- Never return bare top-level categories like 'documents' or 'media'. Use structured subfolders.\n"
            "- Ensure paths are generic, clear, and logical for any global audience.\n\n"
            f"Files to process:\n{filenames_batch}\n\n"
            "You must return your response cleanly in this line-by-line format strict format:\n"
            "filename: Category/NestedSubfolder\n"
            "filename2: Category/NestedSubfolder"
        )
        
        file_mapping = {}
        try:
            response = ollama.chat(
                model=MODEL_NAME, 
                
                messages=[{'role': 'user', 'content': prompt}], 
                options={'temperature': 0.01}  
            )
            content = response['message']['content'].strip()
            
            for line in content.split('\n'):
                if ':' in line:
                    fname, path_assignment = line.split(':', 1)
                    clean_path = path_assignment.strip().replace("'", "").replace('"', '').strip('/')
                    file_mapping[fname.strip().replace("'", "").replace('"', '')] = clean_path
                        
            return file_mapping
        except Exception:
            return {}

    def start_scan_thread(self):
        self.abort_event.clear()
        self.is_aborted_forcefully = False
        self.staged_moves = []
        self.btn_abort.config(text="Abort Operation", bg=ALERT_RED)
        try:
            if self.btn_apply.winfo_exists():
                self.root.after(0, lambda: self.btn_apply.pack_forget())
        except tk.TclError:
            pass
        threading.Thread(target=self.run_scan_phase, daemon=True).start()

    def run_scan_phase(self):
        target = Path(self.target_dir.get())
        if not target.exists() or not target.is_dir():
            messagebox.showerror("Error", "Selected target folder is invalid.")
            return

        self.root.after(0, lambda: self.show_loading("Scanning directory structures..."))

        self.root.after(0, lambda: self.show_loading("Scanning directory structures..."))

        detected_subfolders = []
        try:
            # Use os.walk to find folders at any depth (nested folders)
            for root_dir, dirs, _ in os.walk(target):
                current_root = Path(root_dir)
                
                # Filter out the root itself and any hidden directories (.git, etc.)
                if current_root == target or current_root.name.startswith('.'):
                    continue
                    
                # Skip folders inside paths that are already flagged as protected
                if self.is_protected(current_root):
                    continue

                # Check if this specific nested folder contains project code layouts
                is_proj = self.is_project_folder(current_root)
                detected_subfolders.append((current_root, is_proj))
                
        except Exception as e:
            self.log(f"Error indexing deep folders: {str(e)}")
            return

        self.staged_allowed_folders = []
        if detected_subfolders:
            self.dialog_closed_event.clear()
            def run_dialog():
                dialog = FolderSelectorDialog(self.root, detected_subfolders, self.target_dir.get(), self.dialog_closed_event)
                self.root.wait_window(dialog)
                self.staged_allowed_folders = dialog.result
            self.root.after(0, run_dialog)
            self.dialog_closed_event.wait()

        if self.abort_event.is_set() or self.is_aborted_forcefully:
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.log("---  RUNNING PREVIEW MODE: NO FILES ARE BEING MODIFIED YET ---")

        all_files = []
        try:
            with os.scandir(target) as entries:
                for entry in entries:
                    if entry.is_file() and not entry.name.startswith('.') and not self.is_protected(Path(entry.path)):
                        if entry.name.endswith('.py'):
                            continue
                        all_files.append(Path(entry.path))
        except Exception as e:
            self.log(f"Error scanning baseline directory targets: {str(e)}")

        for folder in self.staged_allowed_folders:
            if self.abort_event.is_set() or self.is_aborted_forcefully: 
                break
            self.log(f" Scan inclusion stack updated: {folder.name}")
            for sub_item in folder.rglob('*'):
                if sub_item.is_file() and sub_item.suffix != '.py' and not self.is_protected(sub_item):
                    all_files.append(sub_item)

        total_files = len(all_files)
        if not all_files:
            self.log("\nNo eligible files found to organize.")
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.root.after(0, lambda: self.show_loading(f" Analyzing {total_files} files...", determinate=True, maximum=total_files))

        scan_start_time = time.time()

        for i in range(0, total_files, BATCH_SIZE):
            if self.abort_event.is_set() or self.is_aborted_forcefully:
                break

            batch_chunk = all_files[i:i + BATCH_SIZE]
            ai_query_stack = []

            elapsed = time.time() - scan_start_time
            if i > 0:
                avg_time_per_file = elapsed / i
                remaining_files = total_files - i
                est_remaining = remaining_files * avg_time_per_file
                time_str = f" Estimated scan time remaining: {self.format_time(est_remaining)}"
            else:
                time_str = " Calculating remaining timeline metrics..."

            self.root.after(0, lambda v=i, ts=time_str: self.update_progress(v, f"⚡ Block Matrix Run {v}/{total_files}...", ts))

            for file_path in batch_chunk:
                if self.is_aborted_forcefully: break
                ext = file_path.suffix.lower()
                
                cache_sig = f"{file_path.stem if len(file_path.stem) < 6 else file_path.stem[:6].lower()}_{ext}"
                if cache_sig in self.classification_cache:
                    suggested = self.classification_cache[cache_sig]
                    with self.staged_lock:
                        self.staged_moves.append((file_path, suggested))
                    self.log(f" [CACHE HIT] {file_path.name} ➔ {suggested}")
                else:
                    ai_query_stack.append((file_path, cache_sig))

            if ai_query_stack and OLLAMA_AVAILABLE and not self.is_aborted_forcefully:
                names_to_evaluate = [fp.name for fp, _ in ai_query_stack]
                ai_results = self.ask_ai_batch_prompt(names_to_evaluate)

                if self.is_aborted_forcefully: break

                for file_path, cache_sig in ai_query_stack:
                    default_fallback = self.fallback_static_rules(file_path.name)
                    suggested = ai_results.get(file_path.name, default_fallback)

                    if not suggested or len(suggested.split('/')) < 2 or any(b in suggested.lower() for b in ["categories", "unsorted", "files", "documents", "media"]):
                        suggested = default_fallback

                    self.classification_cache[cache_sig] = suggested
                    with self.staged_lock:
                        self.staged_moves.append((file_path, suggested))
                    self.log(f" [BATCH PARSED] {file_path.name} ➔ {suggested}")
                    
            elif ai_query_stack and not self.is_aborted_forcefully:
                for file_path, _ in ai_query_stack:
                    default_fallback = self.fallback_static_rules(file_path.name)
                    with self.staged_lock:
                        self.staged_moves.append((file_path, default_fallback))
                    self.log(f" [STATIC MAP] {file_path.name} ➔ {default_fallback}")

        if self.is_aborted_forcefully:
            return

        if self.abort_event.is_set():
            self.staged_moves = []
            self.log(" Scan simulation forcefully aborted.")
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.log(f"\n--- SCAN READY ---")
        self.log(f"Successfully processed optimization steps for {len(self.staged_moves)} items.")
        self.log(" Click 'Apply Changes Live' below to finalize structural transfers.")
        
        self.root.after(0, lambda: self.hide_loading(show_apply_button=True))

    def start_apply_thread(self):
        self.abort_event.clear()
        self.is_aborted_forcefully = False
        self.btn_abort.config(text=" Abort Operation", bg=ALERT_RED)
        threading.Thread(target=self.run_apply_phase, daemon=True).start()

    def run_apply_phase(self):
        target = Path(self.target_dir.get())
        with self.staged_lock:
            moves_to_execute = list(self.staged_moves)

        if not moves_to_execute:
            messagebox.showwarning("Error", "No staged actions found to execute. Run deep scan first.")
            return

        total_moves = len(moves_to_execute)
        self.root.after(0, lambda: self.show_loading("🚀 Executing Live Transfers...", determinate=True, maximum=total_moves))
        
        transfer_start_time = time.time()
        moved_count = 0

        for idx, (file_path, rel_path) in enumerate(moves_to_execute):
            if self.abort_event.is_set() or self.is_aborted_forcefully:
                self.log(f" Live transfers paused halfway. Safely held back remaining {total_moves - moved_count} files.")
                break

            elapsed_transfer = time.time() - transfer_start_time
            if idx > 0:
                avg_transfer_speed = elapsed_transfer / idx
                remaining_transfers = total_moves - idx
                est_remaining_transfer = remaining_transfers * avg_transfer_speed
                time_str = f" Estimated transfer finish: {self.format_time(est_remaining_transfer)}"
            else:
                time_str = " Warming up file transfer pipelines..."

            self.root.after(0, lambda val=idx, ts=time_str: self.update_progress(val, f"🚚 Transferring item {val}/{total_moves}...", ts))

            rel_path = rel_path.replace('"', '').replace("'", "").strip()
            dest_dir = target / rel_path
            
            if file_path.parent == dest_dir or not file_path.exists():
                continue

            self.log(f" [LIVE] Moving: {file_path.name} ➔ {rel_path}")
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                target_file = dest_dir / file_path.name
                if target_file.exists():
                    target_file = dest_dir / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
                shutil.move(str(file_path), str(target_file))
                moved_count += 1
            except Exception as e:
                self.log(f" Error moving {file_path.name}: {str(e)}")

        if self.is_aborted_forcefully:
            return

        if not self.abort_event.is_set():
            try:
                if self.status_label.winfo_exists():
                    self.root.after(0, lambda: self.status_label.config(text="🧹 Clearing leftover empty directories..."))
                    self.root.after(0, lambda: self.time_label.config(text=""))
            except tk.TclError:
                pass
                
            for root_dir, dirs, files in os.walk(target, topdown=False):
                if self.abort_event.is_set(): break
                for d in dirs:
                    folder_path = Path(root_dir) / d
                    if any(folder_path == allowed or folder_path.is_relative_to(allowed) for allowed in self.staged_allowed_folders):
                        if not any(folder_path.iterdir()):
                            try: folder_path.rmdir()
                            except Exception: pass

        if self.abort_event.is_set():
            self.log(f"\n PIPELINE TERMINATED MID-FLIGHT.")
            messagebox.showwarning("Aborted", "Live execution stopped.")
        else:
            self.log(f"\n--- LIVE PROCESSING ARCHITECTURE COMPLETE ---")
            messagebox.showinfo("Success", f"Successfully moved {moved_count} items into their permanent target positions!")
            self.staged_moves = [] 
            
        self.root.after(0, lambda: self.hide_loading(show_apply_button=False))



if __name__ == "__main__":
    root = tk.Tk()
    app = UniversalCleanerGUI(root)
    root.mainloop()