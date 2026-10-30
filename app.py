"""Windows configuration launcher. No input control occurs in this window."""
import argparse
import multiprocessing
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from config import ROOT, load, save, validate

def gui():
    config = load()
    root = tk.Tk()
    root.title('GestureControl | Pixel 5')
    root.geometry('710x900')
    root.minsize(680, 860)
    panel = ttk.Frame(root, padding=18)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='GestureControl', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='Local hand tracking · Starts paused · F8 disables control globally').pack(anchor='w', pady=(0,16))
    fields = ttk.Frame(panel)
    fields.pack(fill='x')
    fields.columnconfigure(1, weight=1)
    variables = {}
    rows = [('source','Camera index or local stream URL'), ('backend','Windows capture backend'),
            ('rotation','Camera rotation (degrees)'), ('sensitivity','Sensitivity (0.2–5)'),
            ('smoothing','Smoothing seconds (0 = exact position, up to 0.5)'), ('deadzone','Jitter deadzone in pixels (0–20)'),
            ('dwell','Gesture hold in seconds (0.1–1)'), ('click_cooldown','Click cooldown in seconds (0.25–3)'),
            ('scroll_speed','Scroll sensitivity (1–100)'), ('confidence','Detection confidence (0.5–0.95)')]
    for i,(key,label) in enumerate(rows):
        ttk.Label(fields, text=label).grid(row=i, column=0, sticky='w', pady=5, padx=(0,14))
        var = tk.StringVar(value=str(config[key]))
        variables[key] = var
        if key in ('backend','rotation'):
            control = ttk.Combobox(fields, textvariable=var, state='readonly', values=('DSHOW','MSMF','AUTO') if key=='backend' else (0,90,180,270))
        else:
            control = ttk.Entry(fields, textvariable=var)
        control.grid(row=i,column=1,sticky='ew')
    for key,label in [('mirror','Mirror image (usually natural for cursor movement)'), ('cursor_only','Cursor only — disable clicking, scrolling and dragging while tuning'),
                      ('relaxed_pose','Relaxed hand in cursor-only mode — other fingers can stay open'),
                      ('absolute_cursor','Absolute cursor — blue rectangle maps directly to the screen'),
                      ('auto_resume','Automatically start/resume tracking; F8 always stays stopped')]:
        variables[key] = tk.BooleanVar(value=config[key])
        ttk.Checkbutton(panel, text=label, variable=variables[key]).pack(anchor='w', pady=8)
    ttk.Label(panel, text='Wi-Fi: use DroidCam Windows virtual camera or http://PHONE_IP:4747/video\nUSB: connect in DroidCam Windows client, then use its camera index.\nStart with 640×480 or 720p, 30 FPS. Source index is specific to the backend.', wraplength=650).pack(anchor='w', pady=8)
    status = tk.StringVar(value='Ready. Test video first, then start hand tracking.')
    child = [None]
    busy = [False]
    def read():
        current = load()  # retain calibration saved by preview
        for key,var in variables.items():
            current[key] = var.get()
        current['rotation'] = int(current['rotation'])
        return validate(current)
    def launch(video=False):
        try:
            if busy[0] or (child[0] and child[0].poll() is None):
                messagebox.showinfo('Already running', 'Close the current preview or wait for camera scan first.')
                return
            c = read()
            save(c)
            args = [sys.executable.replace('pythonw.exe','python.exe'), str(ROOT/'app.py'), '--video-test' if video else '--run']
            with (ROOT/'preview.log').open('w') as log:
                child[0] = subprocess.Popen(args, cwd=str(ROOT), stdout=log, stderr=log,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
            status.set('Preview opened. Close it before changing connection settings.')
        except Exception as exc:
            messagebox.showerror('Configuration', str(exc))
    def scan():
        if busy[0] or (child[0] and child[0].poll() is None):
            return
        backend = variables['backend'].get()
        busy[0] = True
        status.set('Scanning camera indices 0–5; allow up to 45 seconds...')
        def worker():
            from camera import probe
            results = []
            for index in range(6):
                results.append(f'{index}: {probe(str(index), backend)}')
            scan_results.append('\n'.join(results))
        threading.Thread(target=worker, daemon=True).start()
    scan_results = []
    def poll():
        if child[0] and child[0].poll() is not None:
            code = child[0].returncode
            child[0] = None
            current = load()
            for key in ('sensitivity', 'cursor_only'):
                variables[key].set(current[key])
            status.set('Preview closed; settings refreshed.' if code == 0 else 'Preview failed. See last_error.log.')
        if scan_results:
            result = scan_results.pop()
            busy[0] = False
            status.set('Scan complete. Enter a working index above; use video test to identify it.')
            messagebox.showinfo('Camera scan', result)
        root.after(200, poll)
    buttons = ttk.Frame(panel)
    buttons.pack(fill='x', pady=10)
    ttk.Button(buttons,text='Scan cameras',command=scan).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='1. Test video',command=lambda:launch(True)).pack(side='left',padx=8)
    ttk.Button(buttons,text='2. Start tracking',command=launch).pack(side='left',padx=8)
    ttk.Button(panel,text='Open setup instructions',command=lambda:__import__('os').startfile(str(ROOT/'README.md'))).pack(anchor='w',pady=5)
    ttk.Label(panel,textvariable=status,wraplength=650,foreground='#28664b').pack(anchor='w',pady=8)
    ttk.Label(panel,text='In preview: Space arms while pointing. Open palm pauses.\nC calibrates the reachable area. M toggles cursor-only mode.\nF8 is the emergency stop, even when another app has focus.',wraplength=650).pack(anchor='w',pady=8)
    def close():
        if child[0] and child[0].poll() is None:
            messagebox.showinfo('Preview still open', 'Close the camera preview first (Q or Esc). F8 disables mouse control.')
            return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()

if __name__ == '__main__':
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser()
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--video-test',action='store_true')
    parser.add_argument('--dry-run',action='store_true',help='Show tracking without injecting mouse input')
    parser.add_argument('--probe',help='Test a camera index or local URL and exit')
    args = parser.parse_args()
    try:
        if args.probe is not None:
            from camera import probe
            c = validate(load() | {'source':args.probe})
            result = probe(c['source'], c['backend'])
            print(result)
            sys.exit(0 if result.startswith('OK:') else 1)
        elif args.run or args.video_test or args.dry_run:
            from runtime import run
            run(load(), args.video_test, args.dry_run)
        else:
            from desktop import main
            sys.exit(main())
    except Exception:
        import traceback
        error = traceback.format_exc()
        (ROOT/'last_error.log').write_text(error)
        print(error, file=sys.stderr)
        messagebox.showerror('GestureControl', 'Could not start or continue. Details saved in last_error.log.\n\n'+error.splitlines()[-1])
        sys.exit(1)
