import customtkinter as ctk
import keyboard, threading, requests, json, subprocess, pyautogui, time, os, base64, sys, re
import mss
import winreg
import psutil
from tkinter import filedialog
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

# --- CONFIGURACIÓ GLOBAL ---
def get_windows_accent():
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent")
        value, _ = winreg.QueryValueEx(key, "AccentColorMenu")
        r, g, b = value & 0xff, (value >> 8) & 0xff, (value >> 16) & 0xff
        return "#{:02x}{:02x}{:02x}".format(r, g, b)
    except: return "#00D2FF"

ACCENT_COLOR = get_windows_accent()
ctk.set_appearance_mode("system") 

# Estils de la UI
C_BG = ("#F2F4F7", "#0A0A0B")
C_CARD = ("#FFFFFF", "#121214")
C_TEXT = ("#1A1A1A", "#E0E0E0")
C_FIELD = ("#F8F9FA", "#1A1B1E")

# --- PROMPT DE L'AGENT (SEPARAT DE LA LÒGICA) ---
AGENT_PERSONA = (
    "Ets Jarvis, un agent intel·ligent per a Windows. Ets eficient i directe. "
    "Respon de forma conversacional però breu. "
    "Si l'usuari demana una acció tècnica, inclou AL FINAL: [ACTION: {json_config}].\n"
    "Accions: crear_arxiu, terminal, obrir_app."
)

class JarvisSmoothOS(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Jarvis Agent Core")
        self.overrideredirect(True)
        self.attributes("-alpha", 0.0)
        self.withdraw()

        # IA Config
        self.url_ollama = "http://localhost:11434/api"
        self.model_brain = "llama3"
        self.fitxer_actual = os.path.abspath(__file__)
        self.ruta_esc = os.path.join(os.path.expanduser("~"), "Desktop")
        
        self.start_x = 0; self.start_y = 0
        self.setup_ui()
        self.setup_spotlight()
        self.setup_tray()
        
        self.after(500, self.carregar_codi_propi)
        threading.Thread(target=self.update_stats, daemon=True).start()

        keyboard.add_hotkey('alt+space', lambda: self.after(0, self.animar_fade_in, self.spot))

    def setup_ui(self):
        self.geometry("1100x750")
        self.configure(fg_color=C_BG)
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=240, fg_color=C_CARD, corner_radius=25)
        self.sidebar.grid(row=0, column=0, rowspan=2, padx=15, pady=15, sticky="nsew")
        self.sidebar.bind("<Button-1>", self.get_pos); self.sidebar.bind("<B1-Motion>", self.move_window)
        
        ctk.CTkLabel(self.sidebar, text="🧬 JARVIS", font=("Segoe UI", 32, "bold"), text_color=ACCENT_COLOR).pack(pady=(40, 20))
        
        # Monitor Sistema
        self.stats_frame = ctk.CTkFrame(self.sidebar, fg_color=C_FIELD, corner_radius=15)
        self.stats_frame.pack(padx=20, pady=10, fill="x")
        self.lbl_cpu = ctk.CTkLabel(self.stats_frame, text="CPU: 0%", font=("Segoe UI", 12, "bold"), text_color=C_TEXT); self.lbl_cpu.pack(pady=(10,0))
        self.bar_cpu = ctk.CTkProgressBar(self.stats_frame, fg_color="#333", progress_color=ACCENT_COLOR, height=8); self.bar_cpu.set(0); self.bar_cpu.pack(padx=15, pady=(0,10), fill="x")
        self.lbl_ram = ctk.CTkLabel(self.stats_frame, text="RAM: 0%", font=("Segoe UI", 12, "bold"), text_color=C_TEXT); self.lbl_ram.pack(pady=(0,0))
        self.bar_ram = ctk.CTkProgressBar(self.stats_frame, fg_color="#333", progress_color=ACCENT_COLOR, height=8); self.bar_ram.set(0); self.bar_ram.pack(padx=15, pady=(0,15), fill="x")

        self.combo_model = ctk.CTkComboBox(self.sidebar, values=["llama3", "mistral", "phi3"], fg_color=C_FIELD, border_color=ACCENT_COLOR)
        self.combo_model.set(self.model_brain); self.combo_model.pack(pady=20, padx=20)
        
        btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=25, padx=20, fill="x")
        ctk.CTkButton(btn_frame, text="─", width=50, height=35, fg_color=C_FIELD, text_color=C_TEXT, command=lambda: self.animar_fade_out(self)).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="✕", width=50, height=35, fg_color="#A52F2F", text_color="white", command=sys.exit).pack(side="right", padx=5)

        # Tabs
        self.tabs = ctk.CTkTabview(self, fg_color=C_CARD, corner_radius=25, segmented_button_selected_color=ACCENT_COLOR)
        self.tabs.grid(row=0, column=1, padx=(0, 15), pady=(15,0), sticky="nsew")
        self.tab_log = self.tabs.add("📟 Terminal"); self.tab_edit = self.tabs.add("📝 Code Lab")
        self.txt_log = ctk.CTkTextbox(self.tab_log, font=("Consolas", 14), fg_color=C_FIELD, text_color=C_TEXT, corner_radius=15)
        self.txt_log.pack(expand=True, fill="both", padx=15, pady=15)
        self.code_edit = ctk.CTkTextbox(self.tab_edit, font=("Consolas", 13), fg_color=C_FIELD, text_color=C_TEXT, corner_radius=15)
        self.code_edit.pack(expand=True, fill="both", padx=15, pady=15)
        ctk.CTkButton(self.tab_edit, text="🚀 APPLY CHANGES", fg_color="#A52F2F", command=self.aplicar_canvis).pack(pady=10)

        self.bar_ui = ctk.CTkFrame(self, fg_color=C_CARD, height=85, corner_radius=25)
        self.bar_ui.grid(row=1, column=1, padx=(0, 15), pady=15, sticky="ew")
        self.ent_ui = ctk.CTkEntry(self.bar_ui, font=("Segoe UI", 18), placeholder_text="Esperant ordres...", border_width=0, fg_color="transparent", text_color=C_TEXT)
        self.ent_ui.pack(fill="x", padx=25, pady=20)
        self.ent_ui.bind("<Return>", lambda e: self.processar(self.ent_ui))

    def update_stats(self):
        while True:
            self.after(0, lambda: self.refresh_ui_stats(psutil.cpu_percent(), psutil.virtual_memory().percent))
            time.sleep(2)

    def refresh_ui_stats(self, c, r):
        self.lbl_cpu.configure(text=f"CPU: {c}%"); self.bar_cpu.set(c/100)
        self.lbl_ram.configure(text=f"RAM: {r}%"); self.bar_ram.set(r/100)

    def demanar_ia(self, m):
        prompt = f"System: {AGENT_PERSONA}\nUser: {m}"
        try:
            r = requests.post(f"{self.url_ollama}/generate", json={"model": self.model_brain, "prompt": prompt, "stream": False})
            resp = r.json()["response"]
            
            # Orquestració d'accions
            if "[ACTION:" in resp:
                parts = resp.split("[ACTION:")
                msg = parts[0].strip()
                self.log(f"JARVIS: {msg}")
                accio_raw = parts[1].split("]")[0]
                try:
                    pla = json.loads(accio_raw).get("pla", [])
                    for pas in pla: self.executar_pas(pas)
                except: pass
            else:
                self.log(f"JARVIS: {resp}")
        except: self.log("SISTEMA: Error de comunicació amb el nucli.")

    def executar_pas(self, pas):
        a, p = pas["accio"], pas["params"]; self.log(f"EXEC: {a}")
        try:
            if a == "crear_arxiu": open(os.path.join(self.ruta_esc, str(p)), "w").close()
            elif a == "obrir_app": subprocess.Popen(str(p), shell=True)
            elif a == "terminal": subprocess.run(p, shell=True)
        except: pass

    def setup_spotlight(self):
        self.spot = ctk.CTkToplevel(self)
        self.spot.geometry("850x140"); self.spot.overrideredirect(True)
        self.spot.attributes("-topmost", True, "-alpha", 0.0); self.spot.configure(fg_color=C_BG, border_width=2, border_color=ACCENT_COLOR)
        x = int((self.winfo_screenwidth() / 2) - 425); y = int(self.winfo_screenheight() / 4); self.spot.geometry(f"+{x}+{y}")
        f = ctk.CTkFrame(self.spot, fg_color="transparent"); f.pack(fill="x", padx=20, pady=25)
        self.ent_s = ctk.CTkEntry(f, font=("Segoe UI", 24), height=60, placeholder_text="Command...", border_width=0, fg_color=C_CARD, corner_radius=20, text_color=C_TEXT)
        self.ent_s.pack(side="left", fill="x", expand=True, padx=(0, 15))
        for icon, cmd in [("⚙️", self.obrir_config), ("👁️", self.ull_jarvis)]:
            ctk.CTkButton(f, text=icon, width=60, height=60, command=cmd, fg_color=C_CARD, hover_color=ACCENT_COLOR, corner_radius=20, text_color=C_TEXT).pack(side="right", padx=3)
        self.ent_s.bind("<Return>", lambda e: self.processar(self.ent_s)); self.ent_s.bind("<Escape>", lambda e: self.animar_fade_out(self.spot)); self.spot.withdraw()

    def carregar_codi_propi(self):
        try:
            with open(self.fitxer_actual, "r", encoding="utf-8") as f:
                self.code_edit.delete("1.0", "end"); self.code_edit.insert("1.0", f.read())
        except: pass

    def obrir_config(self): self.animar_fade_in(self); self.animar_fade_out(self.spot)
    def animar_fade_in(self, win, alpha=0.0):
        if alpha == 0.0: (win.deiconify(), (self.ent_s.focus() if win == self.spot else self.ent_ui.focus()))
        if alpha < 1.0: (alpha := alpha + 0.2, win.attributes("-alpha", min(alpha, 1.0)), self.after(10, lambda: self.animar_fade_in(win, alpha)))
    def animar_fade_out(self, win, alpha=1.0):
        if alpha > 0.0: (alpha := alpha - 0.2, win.attributes("-alpha", max(alpha, 0.0)), self.after(10, lambda: self.animar_fade_out(win, alpha)))
        else: win.withdraw()

    def processar(self, obj):
        m = obj.get(); obj.delete(0, 'end'); self.log(f"USER: {m}")
        if obj == self.ent_s: self.animar_fade_out(self.spot)
        threading.Thread(target=self.demanar_ia, args=(m,)).start()

    def aplicar_canvis(self):
        with open(self.fitxer_actual, "w", encoding="utf-8") as f: f.write(self.code_edit.get("1.0", "end-1c"))
        os.execv(sys.executable, ['python'] + sys.argv)

    def log(self, t): self.txt_log.insert("end", f" >>> {t}\n"); self.txt_log.see("end")

    def setup_tray(self):
        img = Image.new('RGB', (64, 64), color=(30,30,30)); d = ImageDraw.Draw(img); d.ellipse((10, 10, 54, 54), fill=ACCENT_COLOR)
        self.tray = pystray.Icon("Jarvis", img, "Jarvis OS", (item('Show', lambda: self.after(0, self.animar_fade_in, self)), item('Exit', sys.exit)))
        threading.Thread(target=self.tray.run, daemon=True).start()

    def get_pos(self, e): self.start_x = e.x; self.start_y = e.y
    def move_window(self, e): self.geometry(f"+{self.winfo_x()+(e.x-self.start_x)}+{self.winfo_y()+(e.y-self.start_y)}")
    def ull_jarvis(self):
        self.animar_fade_out(self.spot); time.sleep(0.5)
        with mss.mss() as sct: sct.shot(output=self.ruta_esc+"/jarvis_view.png")
        self.log("Captura visual guardada."); self.animar_fade_in(self)

if __name__ == "__main__":
    app = JarvisSmoothOS(); app.mainloop()