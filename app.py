import socket
import time
import threading
import requests
import json
import os
import datetime

import customtkinter as ctk

PRINTER_IP = "10.10.10.221"
PRINTER_PORT = 9100
ZPL_FEED = "^XA^FO0,0^GB1,1,1^FS^XZ\n"
ZPL_CANCEL_ALL = "~JA\n"
STATUS_URL = f"http://{PRINTER_IP}/index.html"
MEDIA_OUT_TEXT = "Fehler: KEIN PAPIER"
HISTORY_FILE = "history.json"
HEAD_OPEN_TEXT = "Fehler: DRUCKKOPF OFFEN"

def is_head_closed():
    try:
        response = requests.get(STATUS_URL, timeout=5)
        if HEAD_OPEN_TEXT in response.text:
            return False
        else:
            return True
    except:
        raise



def is_media_out():
    try:
        response = requests.get(STATUS_URL, timeout=2)
        if MEDIA_OUT_TEXT in response.text:
            print("[!] Detected media out from web interface.")
            return True
        return False
    except requests.RequestException as e:
        print(f"[!] Error fetching status page: {e}")
        return False


class LabelCounterThread(threading.Thread):
    def __init__(self, update_callback, status_callback, stop_event, pause_event):
        super().__init__(daemon=True)
        self.update_callback = update_callback
        self.status_callback = status_callback
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.count = 0

    def run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect((PRINTER_IP, PRINTER_PORT))
                try:
                    s.send(ZPL_CANCEL_ALL.encode("utf-8"))
                    print("[\u2713] Sent cancel all jobs command.")
                except Exception as e:
                    print(f"[!] Failed to cancel jobs: {e}")
                print("[\u2713] Connected to printer.")
                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        time.sleep(0.1)
                        continue
                    if is_media_out():
                        print("[!] Alle Etiketten gezählt")
                        s.send(ZPL_CANCEL_ALL.encode("utf-8"))
                        self.status_callback("Alle Etiketten gezählt")
                        break
                    if not is_head_closed():
                        self.status_callback("Druckkopf offen - bitte schlie\u00dfen")
                        s.send(ZPL_CANCEL_ALL.encode("utf-8"))
                        time.sleep(0.5)
                        continue
                    else:
                        self.status_callback("")
                    s.send(ZPL_FEED.encode("utf-8"))
                    self.count += 1
                    self.update_callback(self.count)
                    time.sleep(0.5)
        except Exception as e:
            print(f"[!] Connection error: {e}")
            self.status_callback("Verbindungsfehler zum Drucker")


class LabelCounterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Etikettenzähler")
        self.geometry("500x600")

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.job_name_var = ctk.StringVar()
        self.count_var = ctk.IntVar(value=0)
        self.status_var = ctk.StringVar(value="")
        self.history = self.load_history()
        self.current_job = None
        self.worker = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

        self.create_widgets()
        self.update_history_display()

    def create_widgets(self):
        self.frame_current = ctk.CTkFrame(self)
        self.frame_current.pack(padx=10, pady=10, fill="x")

        self.entry_job = ctk.CTkEntry(self.frame_current, textvariable=self.job_name_var, placeholder_text="Job Name")
        self.entry_job.pack(side="left", expand=True, fill="x", padx=(0, 10))
        self.btn_start = ctk.CTkButton(self.frame_current, text="Start", command=self.start_job)
        self.btn_start.pack(side="left")

        self.label_status = ctk.CTkLabel(self, textvariable=self.status_var, text_color="red")
        self.label_status.pack(padx=10, pady=(0, 10), fill="x")

        self.frame_controls = ctk.CTkFrame(self)

        self.frame_history = ctk.CTkFrame(self)
        self.frame_history.pack(padx=10, pady=10, fill="both", expand=True)
        self.text_history = ctk.CTkTextbox(self.frame_history, state="disabled")
        self.text_history.pack(fill="both", expand=True)

    def start_job(self):
        name = self.job_name_var.get().strip()
        if not name:
            return
        self.current_job = {
            "name": name,
            "start": datetime.datetime.now().isoformat(timespec="seconds"),
            "count": 0,
            "canceled": False,
        }
        self.count_var.set(0)
        self.stop_event.clear()
        self.pause_event.clear()
        if not is_head_closed():
            self.set_status("Druckkopf offen - bitte schlie\u00dfen")
            return
        self.btn_start.configure(state="disabled")
        self.set_status("")
        self.worker = LabelCounterThread(self.update_count_from_thread, self.update_status_from_thread, self.stop_event, self.pause_event)
        self.worker.start()
        self.show_controls()

    def show_controls(self):
        for widget in self.frame_controls.winfo_children():
            widget.destroy()
        self.frame_controls.pack(padx=10, pady=10, fill="x")

        ctk.CTkLabel(self.frame_controls, textvariable=self.count_var, width=80).pack(side="left", padx=5)
        self.btn_pause = ctk.CTkButton(self.frame_controls, text="Pause", width=80, command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=5)
        self.btn_end = ctk.CTkButton(self.frame_controls, text="Fertig", width=80, command=self.end_job)
        self.btn_end.pack(side="left")
        self.btn_cancel = ctk.CTkButton(self.frame_controls, text="Abbrechen", width=80, command=self.cancel_job)
        self.btn_cancel.pack(side="left", padx=(5,0))

    def update_count_from_thread(self, value):
        self.after(0, self.set_count, value)

    def update_status_from_thread(self, text):
        self.after(0, self.set_status, text)

    def set_count(self, value):
        self.count_var.set(value)
        if self.current_job:
            self.current_job["count"] = value

    def set_status(self, text):
        self.status_var.set(text)

    def increment_count(self):
        self.set_count(self.count_var.get() + 1)

    def decrement_count(self):
        if self.count_var.get() > 0:
            self.set_count(self.count_var.get() - 1)

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text="Pause")
        else:
            self.pause_event.set()
            self.btn_pause.configure(text="Resume")

    def end_job(self):
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.worker.join()
        if self.current_job:
            self.current_job["end"] = datetime.datetime.now().isoformat(timespec="seconds")
            self.history.append(self.current_job)
            self.save_history()
            self.update_history_display()
        self.reset_job()

    def cancel_job(self):
        if self.current_job:
            self.current_job["canceled"] = True
        self.end_job()

    def reset_job(self):
        self.current_job = None
        self.job_name_var.set("")
        self.frame_controls.pack_forget()
        self.btn_start.configure(state="normal")
        self.set_status("")

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"[!] Could not save history: {e}")

    def update_history_display(self):
        self.text_history.configure(state="normal")
        self.text_history.delete("1.0", "end")
        for job in self.history:
            line = f"{job['start']} - {job['name']} : {job['count']} labels"
            if job.get('canceled'):
                line += " (canceled)"
            elif job.get('end'):
                line += f" ended {job['end']}"
            self.text_history.insert('end', line + '\n')
        self.text_history.configure(state='disabled')


if __name__ == "__main__":
    app = LabelCounterApp()
    app.mainloop()
