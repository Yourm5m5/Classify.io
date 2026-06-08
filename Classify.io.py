import os
import shutil
import time
import json
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

MODEL_NAME = "llama3.2:1b"
BATCH_SIZE = 20  # Process 20 files per single AI query block for maximum speed

PROTECTED_KEYWORDS = ["password", "secret", "private", "backup", "vault", "lock"]
PROJECT_MARKERS = [".git", "package.json", "node_modules", ".venv", "venv", "*.sln", "*.xcodeproj"]

class FolderSelectorDialog(tk.Toplevel):
    def __init__(self, parent, folders, close_event):
        super().__init__(parent)
        self.title("Select Folders to Process")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        
        self.folders = folders
        self.close_event = close_event
        self.checkbox_vars = {}
        self.result = []

        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        ttk.Label(
            self, 
            text="Choose which folders to scan/extract files from.\nUnchecked folders (like multi-file projects) will be ignored completely.",
            font=("Arial", 10), justify="left"
        ).pack(pady=10, padx=10, fill="x")

        container = ttk.Frame(self)
        container.pack(expand=True, fill="both", padx=10, pady=5)
        
        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        for folder_path, is_likely_project in self.folders:
            var = tk.BooleanVar(value=not is_likely_project)
            self.checkbox_vars[folder_path] = var
            
            label_text = folder_path.name
            if is_likely_project:
                label_text += " ⚠️ (Detected Project Structure)"
                
            cb = ttk.Checkbutton(self.scrollable_frame, text=label_text, variable=var)
            cb.pack(anchor="w", pady=2, padx=5)

        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Confirm Selection", command=self.on_confirm).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.on_cancel).pack(side="right")

    def on_confirm(self):
        self.result = [folder for folder, var in self.checkbox_vars.items() if var.get()]
        self.close_event.set()
        self.destroy()

    def on_cancel(self):
        self.result = [] 
        self.close_event.set()
        self.destroy()


class UniversalCleanerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Universal AI Deep Organizer & Project Guard")
        self.root.geometry("750x670")
        self.root.minsize(600, 550)

        self.target_dir = tk.StringVar(value=str(Path.home() / "Downloads"))
        
        self.dialog_closed_event = threading.Event()
        self.abort_event = threading.Event()

        self.staged_moves = []
        self.staged_allowed_folders = []
        self.staged_lock = threading.Lock()
        self.progress_lock = threading.Lock()

        # Low-resource cache layer to prevent re-querying the local AI for repeated file structural types
        self.classification_cache = {}

        self.setup_ui()

    def setup_ui(self):
        frame_top = ttk.LabelFrame(self.root, text=" Target Directory to Clean ", padding=10)
        frame_top.pack(fill="x", padx=15, pady=10)
        ttk.Entry(frame_top, textvariable=self.target_dir, width=50).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(frame_top, text="Browse...", command=self.browse_folder).pack(side="right")

        frame_options = ttk.Frame(self.root, padding=5)
        frame_options.pack(fill="x", padx=15)
        
        ai_status = "✨ AI Brain Ready (Ollama)" if OLLAMA_AVAILABLE else "⚠️ Ollama Missing (Using Smart Static Extensions)"
        ttk.Label(frame_options, text=ai_status, font=("Arial", 9, "italic"), foreground="gray").pack(side="left")

        self.control_frame = ttk.Frame(self.root)
        self.control_frame.pack(fill="x", padx=15, pady=10)

        self.btn_run = ttk.Button(self.control_frame, text="⚡ Deep Scan & Preview Architecture (Dry Run)", command=self.start_scan_thread)
        self.btn_run.pack(pady=5)

        self.btn_apply = ttk.Button(self.control_frame, text="🚀 Apply Changes Live (Move Files Now)", command=self.start_apply_thread)
        self.btn_apply.pack_forget()

        self.progress_frame = ttk.Frame(self.control_frame)
        self.status_label = ttk.Label(self.progress_frame, text="Preparing environment...", font=("Arial", 10, "bold"))
        self.status_label.pack(anchor="w", pady=(0, 2))
        
        progress_inner_frame = ttk.Frame(self.progress_frame)
        progress_inner_frame.pack(fill="x", expand=True)
        
        self.progress_bar = ttk.Progressbar(progress_inner_frame, mode="indeterminate", length=300)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.btn_abort = ttk.Button(progress_inner_frame, text="🛑 Abort Operation", command=self.trigger_abort)
        self.btn_abort.pack(side="right")

        frame_log = ttk.LabelFrame(self.root, text=" System Output Log ", padding=10)
        frame_log.pack(expand=True, fill="both", padx=15, pady=(0, 15))
        self.log_text = tk.Text(frame_log, wrap="word", state="disabled", font=("Courier New", 9))
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

    def show_loading(self, status_text, determinate=False, maximum=100):
        try:
            self.btn_run.pack_forget()
            self.btn_apply.pack_forget()
            self.progress_frame.pack(fill="x", expand=True)
            self.status_label.config(text=status_text)
            
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

    def update_progress(self, current_value, status_text=None):
        try:
            if self.progress_bar.winfo_exists():
                if status_text:
                    self.status_label.config(text=status_text)
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
                self.btn_run.pack(pady=5)
            if show_apply_button and self.staged_moves and self.btn_apply.winfo_exists():
                self.btn_apply.pack(pady=5)
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def trigger_abort(self):
        self.log("\n🛑 [ABORT REQUEST] Halting pipeline operations...")
        self.abort_event.set()

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
            ('png', 'jpg', 'jpeg', 'gif', 'svg'): 'Media/Images',
            ('mp4', 'mkv', 'avi', 'mov'): 'Media/Videos',
            ('mp3', 'wav', 'flac'): 'Media/Audio',
            ('zip', 'tar', 'gz', 'rar', '7z'): 'Archives',
            ('pdf', 'docx', 'txt', 'xlsx', 'pptx'): 'Documents',
            ('exe', 'msi', 'dmg', 'pkg'): 'Installers_and_Setups',
            ('py', 'js', 'html', 'css', 'json', 'cpp'): 'Development/Code',
            ('stl', '3mf', 'step', 'stp', 'f3z', 'catpart'): '3D_Models_and_CAD',
            ('gcode', 'bgcode'): '3D_Printing_Gcode'
        }
        for extensions, classification in fallback_maps.items():
            if ext in extensions:
                return classification
        return "Unsorted_Other_Files"

    def ask_ai_batch_prompt(self, filenames_batch):
        """High-density token prompt to parse blocks of 20 elements swiftly inside under 5 seconds."""
        if self.abort_event.is_set():
            return {}
        
        prompt = (
            "Map files to target paths:\n"
            "- 3D_Models_and_CAD (.stl/.3mf/.step -> clean CamelCase subfolder based on identity)\n"
            "- 3D_Printing_Gcode (.gcode/.bgcode -> matching item subfolder)\n"
            "- Installers_and_Setups (.exe/.msi)\n"
            "- Documents (.pdf/.txt/.xlsx)\n"
            "- Media (.png/.jpg)\n\n"
            f"Files to sort:\n{filenames_batch}\n\n"
            "Format: Return ONLY lines matching 'filename: Category/Subfolder'. No markdown wrappers or conversational filler."
        )
        
        mapping = {}
        try:
            response = ollama.chat(
                model=MODEL_NAME, 
                messages=[{'role': 'user', 'content': prompt}], 
                options={'temperature': 0.01}  # Keep answers deterministic and tight
            )
            content = response['message']['content'].strip()
            for line in content.split('\n'):
                if ':' in line:
                    fname, path_assignment = line.split(':', 1)
                    mapping[fname.strip().replace("'", "").replace('"', '')] = path_assignment.strip()
            return mapping
        except Exception:
            return {}

    def start_scan_thread(self):
        self.abort_event.clear()
        self.staged_moves = []
        try:
            if self.btn_apply.winfo_exists():
                self.root.after(0, lambda: self.btn_apply.pack_forget())
        except tk.TclError:
            pass
        threading.Thread(target=self.run_scan_phase, daemon=True).start()

    def run_scan_phase(self):
        global OLLAMA_AVAILABLE 
        target = Path(self.target_dir.get())
        if not target.exists() or not target.is_dir():
            messagebox.showerror("Error", "Selected target folder is invalid.")
            return

        self.root.after(0, lambda: self.show_loading("🔍 Scanning directory structures..."))

        detected_subfolders = []
        # Low resource consumption pass using os.scandir instead of indexing complete file trees to memory
        try:
            with os.scandir(target) as entries:
                for entry in entries:
                    if entry.is_dir() and not entry.name.startswith('.') and not self.is_protected(Path(entry.path)):
                        is_proj = self.is_project_folder(Path(entry.path))
                        detected_subfolders.append((Path(entry.path), is_proj))
        except Exception as e:
            self.log(f"Error indexing top folders: {str(e)}")
            return

        self.staged_allowed_folders = []
        if detected_subfolders:
            self.dialog_closed_event.clear()
            def run_dialog():
                dialog = FolderSelectorDialog(self.root, detected_subfolders, self.dialog_closed_event)
                self.root.wait_window(dialog)
                self.staged_allowed_folders = dialog.result
            self.root.after(0, run_dialog)
            self.dialog_closed_event.wait()

        if self.abort_event.is_set():
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.log("--- 🛡️ RUNNING PREVIEW MODE: NO FILES ARE BEING MODIFIED YET ---")

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
            if self.abort_event.is_set(): 
                break
            self.log(f"🔍 Scan inclusion stack updated: {folder.name}")
            for sub_item in folder.rglob('*'):
                if sub_item.is_file() and sub_item.suffix != '.py' and not self.is_protected(sub_item):
                    all_files.append(sub_item)

        total_files = len(all_files)
        if not all_files:
            self.log("\nNo eligible files found to organize.")
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.root.after(0, lambda: self.show_loading(f"🧠 Group-Batch Analyzing {total_files} files...", determinate=True, maximum=total_files))

        # Vector Batching Processing Loop
        for i in range(0, total_files, BATCH_SIZE):
            if self.abort_event.is_set():
                break

            batch_chunk = all_files[i:i + BATCH_SIZE]
            ai_query_stack = []

            self.root.after(0, lambda v=i: self.update_progress(v, f"⚡ Block Matrix Run {v}/{total_files}..."))

            # Step A: Query memory cache lookups to preserve 0% CPU footprint on duplicate items
            for file_path in batch_chunk:
                ext = file_path.suffix.lower()
                # Create structural signature key from file extensions and leading strings
                cache_sig = f"{file_path.stem[:6].lower()}_{ext}"

                if cache_sig in self.classification_cache:
                    suggested = self.classification_cache[cache_sig]
                    with self.staged_lock:
                        self.staged_moves.append((file_path, suggested))
                    self.log(f"⚡ [CACHE HIT] {file_path.name} ➔ {suggested}")
                else:
                    ai_query_stack.append((file_path, cache_sig))

            # Step B: Call Ollama on unmatched elements inside the batch bundle array
            if ai_query_stack and OLLAMA_AVAILABLE:
                names_to_evaluate = [fp.name for fp, _ in ai_query_stack]
                ai_results = self.ask_ai_batch_prompt(names_to_evaluate)

                for file_path, cache_sig in ai_query_stack:
                    default_fallback = self.fallback_static_rules(file_path.name)
                    suggested = ai_results.get(file_path.name, default_fallback)

                    if not suggested or any(b in suggested.lower() for b in ["categories", "unsorted", "files"]):
                        suggested = default_fallback

                    # Register signature map dynamically into global workspace memory
                    self.classification_cache[cache_sig] = suggested
                    with self.staged_lock:
                        self.staged_moves.append((file_path, suggested))
                    self.log(f"🔮 [BATCH PARSED] {file_path.name} ➔ {suggested}")
                    
            elif ai_query_stack:
                # Fallback if Ollama environment dependency is unavailable
                for file_path, _ in ai_query_stack:
                    default_fallback = self.fallback_static_rules(file_path.name)
                    with self.staged_lock:
                        self.staged_moves.append((file_path, default_fallback))
                    self.log(f"📁 [STATIC MAP] {file_path.name} ➔ {default_fallback}")

        if self.abort_event.is_set():
            self.staged_moves = []
            self.log("🛑 Scan simulation forcefully aborted.")
            self.root.after(0, lambda: self.hide_loading(False))
            return

        self.log(f"\n--- SCAN READY ---")
        self.log(f"Successfully processed optimization steps for {len(self.staged_moves)} items.")
        self.log("⚠️ Click 'Apply Changes Live' below to finalize structural transfers.")
        
        self.root.after(0, lambda: self.hide_loading(show_apply_button=True))

    def start_apply_thread(self):
        self.abort_event.clear()
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
        
        moved_count = 0
        for idx, (file_path, rel_path) in enumerate(moves_to_execute):
            if self.abort_event.is_set():
                self.log(f"⚠️ Live transfers paused halfway. Safely held back remaining {total_moves - moved_count} files.")
                break

            self.root.after(0, lambda val=idx: self.update_progress(val, f"🚚 Transferring item {val}/{total_moves}..."))

            rel_path = rel_path.replace('"', '').replace("'", "").strip()
            dest_dir = target / rel_path
            
            if file_path.parent == dest_dir or not file_path.exists():
                continue

            self.log(f"🚀 [LIVE] Moving: {file_path.name} ➔ {rel_path}")
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                target_file = dest_dir / file_path.name
                if target_file.exists():
                    target_file = dest_dir / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
                shutil.move(str(file_path), str(target_file))
                moved_count += 1
            except Exception as e:
                self.log(f"❌ Error moving {file_path.name}: {str(e)}")

        if not self.abort_event.is_set():
            try:
                if self.status_label.winfo_exists():
                    self.root.after(0, lambda: self.status_label.config(text="🧹 Clearing leftover empty directories..."))
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
            self.log(f"\n🛑 PIPELINE TERMINATED MID-FLIGHT.")
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