#!/usr/bin/env python3
"""
3G DESIGN — Local Call Tracker
Run on your shop computer to log WhatsApp/phone interactions to the ERP.

Setup in .env:
  LOCAL_API_KEY=your-secret-key-here
  LOCAL_API_URL=http://127.0.0.1:5001/api/communications/log

Usage:
  python local_call_tracker.py           # GUI on Windows, CLI elsewhere
  python local_call_tracker.py --gui     # Force GUI
  python local_call_tracker.py --cli     # Force terminal mode
  python local_call_tracker.py +231... "Name" whatsapp_call "Notes"
"""
import os
import sys
import json
import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_URL = os.getenv('LOCAL_API_URL', 'http://127.0.0.1:5001/api/communications/log')
API_KEY = os.getenv('LOCAL_API_KEY', '')
STATUS_URL = API_URL.replace('/api/communications/log', '/api/communications/status')

TYPE_OPTIONS = [
    ('WhatsApp Call', 'whatsapp_call'),
    ('WhatsApp Message', 'whatsapp_message'),
    ('Phone Call', 'voice'),
]


def check_server():
    try:
        req = urllib.request.Request(STATUS_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get('status') == 'online', data
    except Exception:
        return False, {}


def log_call(phone, caller_name='', call_type='whatsapp_call', notes='', status='logged'):
    if not API_KEY:
        return False, 'Set LOCAL_API_KEY in your .env file first.'

    payload = json.dumps({
        'phone_number': phone,
        'caller_name': caller_name,
        'call_type': call_type,
        'notes': notes,
        'status': status,
        'source': 'local_desktop',
        'logged_by': os.getenv('USERNAME', 'local_tracker'),
    }).encode('utf-8')

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY,
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            msg = f"Logged #{result.get('id')} — {phone}"
            return True, msg
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return False, f'API Error ({e.code}): {body}'
    except Exception as e:
        return False, f'Connection failed: {e}\nMake sure the server is running: python run.py'


def interactive_mode():
    print('=' * 50)
    print('  3G DESIGN — Local Communications Tracker')
    print('=' * 50)

    online, _ = check_server()
    if not online:
        print('\nServer not reachable. Start it with: python run.py\n')
    else:
        print('\nServer connected.\n')

    if not API_KEY:
        print('WARNING: LOCAL_API_KEY not set in .env — logging will fail.\n')

    while True:
        print('-' * 50)
        phone = input('Phone number (or "quit"): ').strip()
        if phone.lower() in ('quit', 'exit', 'q'):
            print('Goodbye.')
            break
        if not phone:
            continue

        name = input('Customer name (optional): ').strip()
        print('Type: 1=WhatsApp Call  2=WhatsApp Message  3=Phone Call')
        type_choice = input('Choose [1]: ').strip() or '1'
        type_map = {'1': 'whatsapp_call', '2': 'whatsapp_message', '3': 'voice'}
        call_type = type_map.get(type_choice, 'whatsapp_call')

        notes = input('Notes / order details (optional): ').strip()
        ok, msg = log_call(phone, name, call_type, notes)
        print(msg if ok else f'ERROR: {msg}')


def gui_mode():
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title('3G DESIGN — Call Tracker')
    root.geometry('400x420')
    root.resizable(False, False)
    root.configure(bg='#0B1F3A')

    style_font = ('Segoe UI', 10)
    title_font = ('Segoe UI', 14, 'bold')

    header = tk.Frame(root, bg='#0B1F3A', pady=12)
    header.pack(fill='x')
    tk.Label(header, text='3G DESIGN', font=title_font, fg='#C9A84C', bg='#0B1F3A').pack()
    tk.Label(header, text='Quick Call Logger', font=('Segoe UI', 9), fg='#FAF8F4', bg='#0B1F3A').pack()

    status_var = tk.StringVar(value='Checking server...')
    status_label = tk.Label(root, textvariable=status_var, font=('Segoe UI', 8), fg='#8a94a0', bg='#0B1F3A')
    status_label.pack(pady=(0, 8))

    form = tk.Frame(root, bg='#FAF8F4', padx=20, pady=16)
    form.pack(fill='both', expand=True)

    def add_field(label, row):
        tk.Label(form, text=label, font=style_font, bg='#FAF8F4', anchor='w').grid(row=row, column=0, sticky='w', pady=(8, 2))
        entry = tk.Entry(form, font=style_font, width=32)
        entry.grid(row=row + 1, column=0, sticky='ew', pady=(0, 4))
        return entry

    phone_entry = add_field('Phone Number *', 0)
    name_entry = add_field('Customer Name', 2)
    notes_entry = add_field('Notes / Order Details', 4)

    tk.Label(form, text='Interaction Type', font=style_font, bg='#FAF8F4', anchor='w').grid(row=6, column=0, sticky='w', pady=(8, 2))
    type_var = tk.StringVar(value='whatsapp_call')
    type_combo = ttk.Combobox(form, textvariable=type_var, values=[t[1] for t in TYPE_OPTIONS], state='readonly', width=30)
    type_combo.grid(row=7, column=0, sticky='ew')
    type_combo.set('whatsapp_call')
    type_display = {v: k for k, v in TYPE_OPTIONS}
    type_combo['values'] = [f'{k} ({v})' for k, v in TYPE_OPTIONS]

    def get_call_type():
        sel = type_combo.get()
        for label, val in TYPE_OPTIONS:
            if sel.startswith(label):
                return val
        return 'whatsapp_call'

    type_combo.set('WhatsApp Call (whatsapp_call)')

    result_var = tk.StringVar()
    result_label = tk.Label(form, textvariable=result_var, font=('Segoe UI', 9), fg='#0B1F3A', bg='#FAF8F4', wraplength=340)
    result_label.grid(row=8, column=0, pady=(12, 0), sticky='w')

    def refresh_status():
        online, data = check_server()
        if online:
            wa = ' · WA API ready' if data.get('whatsapp_api_configured') else ''
            status_var.set(f'Server online{wa}')
            status_label.configure(fg='#25d366')
        else:
            status_var.set('Server offline — run: python run.py')
            status_label.configure(fg='#dc3545')

    def do_log():
        phone = phone_entry.get().strip()
        if not phone:
            messagebox.showwarning('Required', 'Enter a phone number.')
            phone_entry.focus()
            return
        ok, msg = log_call(phone, name_entry.get().strip(), get_call_type(), notes_entry.get().strip())
        if ok:
            result_var.set(msg)
            notes_entry.delete(0, tk.END)
            phone_entry.focus()
        else:
            result_var.set('')
            messagebox.showerror('Log Failed', msg)

    btn_frame = tk.Frame(form, bg='#FAF8F4')
    btn_frame.grid(row=9, column=0, pady=(16, 0), sticky='ew')

    log_btn = tk.Button(
        btn_frame, text='Log Now', font=('Segoe UI', 11, 'bold'),
        bg='#C9A84C', fg='#0B1F3A', activebackground='#d4b85e',
        relief='flat', padx=20, pady=8, cursor='hand2', command=do_log,
    )
    log_btn.pack(fill='x')

    open_btn = tk.Button(
        btn_frame, text='Open Web Quick Log', font=style_font,
        bg='#0B1F3A', fg='#FAF8F4', activebackground='#1a3354',
        relief='flat', pady=6, cursor='hand2',
        command=lambda: os.startfile('http://127.0.0.1:5001/admin/communications/quick'),
    )
    open_btn.pack(fill='x', pady=(8, 0))

    form.columnconfigure(0, weight=1)
    root.bind('<Return>', lambda e: do_log())
    refresh_status()
    phone_entry.focus()
    root.mainloop()


def main():
    args = sys.argv[1:]

    if '--cli' in args:
        interactive_mode()
        return

    if '--gui' in args or (not args and sys.platform == 'win32'):
        try:
            gui_mode()
        except ImportError:
            print('Tkinter not available — falling back to CLI mode.')
            interactive_mode()
        return

    if args and args[0] not in ('--gui', '--cli'):
        ok, msg = log_call(
            args[0],
            args[1] if len(args) > 1 else '',
            args[2] if len(args) > 2 else 'whatsapp_call',
            ' '.join(args[3:]) if len(args) > 3 else '',
        )
        print(msg if ok else f'ERROR: {msg}')
        return

    interactive_mode()


if __name__ == '__main__':
    main()
