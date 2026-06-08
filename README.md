# Classify.io

This is a file sorter that uses local AI. It scans, checks, and organizes messy directory structures—categorizing raw files into clean, logical subfolders while automatically protecting programming projects and sensitive files.

---

## What is Classify.io?
**Classify.io** is a desktop automation utility built in Python using the Tkinter GUI framework. It acts as an automated digital housekeeper for crowded storage areas (like your Downloads folder). Instead of relying strictly on rigid, hardcoded file extension paths, it leverages a locally running Large Language Model (LLM) to intelligently read filenames, evaluate context, and automatically determine the most logical structural destination for your data.

---

## How It Works
The application processes files using a strict, multi-tier execution pipeline designed for safety and speed:

1. **Project Guard Rails & Exclusions:** The script scans your target path. If it identifies folder structures containing development markers (like `.git`, `node_modules`, `venv`, or project solution files), it pauses and prompts you with a confirmation window. You can uncheck these folders so your active code workspaces stay untouched.
2. **Local Cache Signatures:** To reduce unnecessary AI overhead, the app generates a temporary signature hash for file types. Recurring files are matched instantly using this local cache.
3. **Local LLM Evaluation:** Uncached items are compiled into chunks and evaluated locally by Ollama. The AI assigns an optimal, nested directory path (e.g., changing a chaotic layout of mechanical drawings, receipts, and audio samples into organized tracks like `3D_Models_and_CAD/Mechanical_Parts`, `Documents/Invoices`, and `Media/Audio`).

---

## Step-by-Step Installation & Setup

Follow these quick terminal steps to get the environment configured and the application running.

### 1. Download or Clone the Tool
Either clone the repository using Git or download the source ZIP file directly from GitHub and extract it to your machine.

```
powershell
git clone [https://github.com/YOUR_USERNAME/Classify.io.git](https://github.com/YOUR_USERNAME/Classify.io.git); cd Classify.io; python -m venv .venv
.venv\Scripts\Activate.ps1; pip install --upgrade pip; pip install ollama
ollama run llama3.2:1b "Ready?"; pythonw cleaner.py
```

### 2. Start and Warm Up the AI Model
Ensure Ollama is running on your machine, then pull and pre-load the ultra-fast llama3.2:1b model. This eliminates cold-start lag when you trigger a deep scan:

```
Bash
ollama run llama3.2:1b "Ready?"
```

Once the model replies, type /exit to return to your normal terminal. The model will remain warm in your system RAM.

### 3. Set Up an Isolated Virtual Environment
Creating a virtual environment ensures the application dependencies don't interfere with your computer's other global Python setups.

Windows (PowerShell):

```
PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
macOS / Linux:

```
Bash
python3 -m venv .venv
source .venv/bin/activate
```

###4. Install Runtime Dependencies
Upgrade your local package manager and pull down the official Ollama library interface module:

```
Bash
pip install --upgrade pip
pip install ollama
```

### 5. Launch the Application
Execute the script from your active environment terminal prompt:

```
Bash
python Classify.io.py
```

(Windows users who want to run the application cleanly without leaving a black console window hanging open in the background can launch using pythonw cleaner.py instead).'''

### Disclaimer & Limitations
Local Processing Scope: This application runs entirely on your local machine. No file names, data metadata, or directory structures are uploaded to the internet or sent to third-party endpoints.

AI Inaccuracy Variance: Because sorting is handled by a lightweight generative AI model (llama3.2:1b), classification logic is non-deterministic. The AI can occasionally hallucinate path assignments, misinterpret context clues within a string, or make inconsistent choices across large file sets.

Dry Run First: It is highly recommended to always review the results during the Deep Scan (Dry Run) phase within the logging console before clicking Apply Changes Live to commit permanent filesystem modifications.
