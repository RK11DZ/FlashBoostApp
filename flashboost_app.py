#!/usr/bin/env python3
import gi
import threading
import os
import subprocess
import pygame
import numpy as np
from datetime import datetime
import psutil
import re

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

class SystemInfo:
    def get_cpu_usage(self):
        try:
            return psutil.cpu_percent(interval=None)
        except Exception as e:
            print(f"Error getting CPU usage: {e}")
            return 0.0

    def get_ram_usage(self):
        try:
            return psutil.virtual_memory().percent
        except Exception as e:
            print(f"Error getting RAM usage: {e}")
            return 0.0

    def get_disk_usage(self, path='/'):
        try:
            return psutil.disk_usage(path).percent
        except FileNotFoundError:
            print(f"Error getting disk usage: Path '{path}' not found.")
            return 0.0
        except Exception as e:
            print(f"Error getting disk usage for '{path}': {e}")
            return 0.0

    def get_temperature(self):
        temp_str = "N/A"
        try:
            temps = psutil.sensors_temperatures()
            core_temps = temps.get('coretemp', []) or temps.get('k10temp', []) or temps.get('acpitz', [])
            if core_temps:
                package_temp = next((t.current for t in core_temps if 'Package' in t.label or 'Tdie' in t.label), None)
                if package_temp:
                    temp_str = f"{package_temp:.0f}°C"
                else:
                    temp_str = f"{core_temps[0].current:.0f}°C"
            else:
                for sensor_list in temps.values():
                    if sensor_list:
                        temp_str = f"{sensor_list[0].current:.0f}°C"; break
        except AttributeError: pass
        except Exception as e: print(f"Error getting temperature: {e}")
        return temp_str

    def find_active_wifi_interface(self):
        try:
            result = subprocess.run(['ip', '-o', 'link', 'show', 'up'], capture_output=True, text=True, check=True)
            match = re.search(r'^\d+:\s+([a-zA-Z0-9]+(?:wl|wifi|wlan)[a-zA-Z0-9]*)\s+.*state UP', result.stdout, re.MULTILINE)
            if match:
                return match.group(1)
            result_iw = subprocess.run(['iw', 'dev'], capture_output=True, text=True, check=True)
            match_iw = re.search(r'^\s*Interface\s+([a-zA-Z0-9]+(?:wl|wifi|wlan)[a-zA-Z0-9]*)\s*$', result_iw.stdout, re.MULTILINE)
            if match_iw:
                 return match_iw.group(1)
        except FileNotFoundError: print("Error: 'ip' or 'iw' command not found.")
        except subprocess.CalledProcessError: print("No active WiFi interface found or error executing command.")
        except Exception as e: print(f"Error finding WiFi interface: {e}")
        return None

    def check_command_exists(self, command):
        try:
            subprocess.run(['which', command], check=True, capture_output=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

class FlashBoostApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="⚡ FlashBoost") # عنوان أبسط
        self.set_default_size(800, 620)
        self.set_border_width(0) # إزالة الهامش الرئيسي للنافذة للتحكم الكامل بالتخطيط
        self.connect("destroy", self.on_quit)

        self.system_info = SystemInfo()
        self.logview = None # سيتم إنشاؤه في init_ui
        self.log_scroll_window = None # للحفاظ على مرجع لنافذة التمرير
        self.buttons = []
        self.spinner = Gtk.Spinner()

        self.init_pygame_mixer()
        self.load_css()
        self.init_ui()
        GLib.idle_add(self.optimize_performance)
        GLib.timeout_add(1500, self.update_info)

    def init_pygame_mixer(self):
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.log("تم تهيئة نظام الصوت (pygame).")
        except pygame.error as e:
             self.log(f"⚠️ فشل تهيئة pygame.mixer: {e}.")
             print(f"Pygame Mixer Init Error: {e}")
        except Exception as e:
            self.log(f"⚠️ خطأ غير متوقع أثناء تهيئة pygame.mixer: {e}")
            print(f"Unexpected Pygame Mixer Error: {e}")

    def load_css(self):
        screen = Gdk.Screen.get_default()
        css_provider = Gtk.CssProvider()
        # CSS بمظهر مسطح وحديث أكثر
        css_data = """
            /* استخدام خطوط النظام القياسية */
            * {
                 font-family: sans-serif;
                 font-size: 10pt; /* حجم خط أساسي */
            }

            /* النافذة الرئيسية - خلفية داكنة */
            window {
                background-color: #2d2d2d; /* لون أساسي داكن */
                color: #eeeeee;
            }

            /* إضافة هامش داخلي عبر Box رئيسي بدلاً من border_width للنافذة */
            .main-container {
                 padding: 15px;
            }

            /* تنسيق العناوين للأقسام */
            .section-title {
                font-size: 14pt; /* حجم أكبر للعناوين */
                font-weight: bold;
                color: #62a0ea; /* لون مميز للعناوين */
                margin-bottom: 10px; /* مسافة أسفل العنوان */
                margin-top: 10px; /* مسافة فوق العنوان (للأقسام غير الأولى) */
            }
            .section-title:first-child {
                 margin-top: 0; /* إزالة المسافة العلوية لأول عنوان */
            }

            /* تنسيق الأزرار - مظهر مسطح */
            button {
                background-color: #4a4a4a; /* لون أساسي للزر */
                color: #ffffff;
                border: none; /* إزالة الحدود */
                border-radius: 5px; /* زوايا دائرية */
                padding: 12px 18px; /* حشوة أكبر */
                font-weight: bold;
                transition: background-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
                box-shadow: 0 1px 2px rgba(0,0,0,0.2); /* ظل خفيف جداً */
                margin: 5px;
            }
            button:hover {
                background-color: #5a5a5a; /* لون أفتح عند التحويم */
                box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                /* لا يوجد transform هنا */
            }
            button:active {
                background-color: #404040; /* لون أغمق عند النقر */
                box-shadow: inset 0 1px 2px rgba(0,0,0,0.3);
            }
            button:disabled {
                background-color: #3f3f3f;
                color: #888888;
                box-shadow: none;
            }
             button:disabled label, button:disabled image {
                 opacity: 0.5;
            }

            /* تنسيق أشرطة التقدم */
            progressbar {
                 border-radius: 15px; /* شريط دائري تماماً */
                 padding: 3px;
                 background-color: #444444; /* خلفية أغمق للشريط */
                 box-shadow: none; /* إزالة الظل */
                 border: 1px solid rgba(0,0,0,0.2); /* حد خفيف */
            }
            progressbar progress {
                 background-image: linear-gradient(to right, #5294e2, #62a0ea); /* تدرج أزرق */
                 border-radius: 12px;
                 box-shadow: none;
            }
            progressbar text {
                color: #ffffff;
                font-weight: bold;
                font-size: 9pt; /* خط أصغر للنص داخل الشريط */
                text-shadow: 1px 1px 1px rgba(0,0,0,0.6);
            }

            /* منطقة السجل */
            #logview_container { /* اسم جديد لنافذة التمرير */
                 border-radius: 6px;
                 border: 1px solid #404040; /* حدود أغمق */
                 background-color: #252525; /* خلفية داكنة جداً للسجل */
                 min-height: 150px; /* تحديد ارتفاع أدنى للسجل */
            }
            #logview_widget text { /* النص داخل السجل */
                 background-color: transparent;
                 color: #bbbbbb; /* لون نص أفتح */
                 font-family: monospace; /* خط ثابت العرض */
                 font-size: 9pt; /* خط أصغر للسجل */
                 padding: 8px;
             }
             /* شريط التمرير */
             #logview_container scrollbar {
                 background-color: transparent;
             }
             #logview_container scrollbar slider {
                  background-color: #5a5a5a;
                  border-radius: 3px;
                  border: 1px solid #404040;
             }

             spinner {
                 -gtk-icon-transform: scale(1.3);
                 opacity: 0.8;
             }

            /* شريط الإجراءات في الأسفل */
             actionbar {
                  background-color: #353535; /* لون أغمق قليلاً للشريط */
                  border-top: 1px solid #454545; /* خط فاصل علوي */
                  padding: 5px;
             }
             actionbar button { /* تنسيق خاص لأزرار شريط الإجراءات */
                   padding: 6px 12px;
                   font-size: 9pt;
                   box-shadow: none;
                   background-color: #555555;
             }
              actionbar button:hover {
                    background-color: #656565;
              }
              actionbar button:active {
                     background-color: #4f4f4f;
              }

             tooltip {
                background-color: #1c1c1c;
                color: #e0e0e0;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 9pt;
                box-shadow: 0 2px 6px rgba(0,0,0,0.5);
            }
        """
        try:
            css_provider.load_from_data(css_data.encode("utf-8"))
            context = Gtk.StyleContext()
            context.add_provider_for_screen(
                screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            # لا نسجل هذه الرسالة لأن السجل لم يتم تهيئته بعد
            # self.log("🎨 تم تحميل تصميم الواجهة المحسّن (CSS).")
            print("CSS loaded successfully.")
        except Exception as e:
            print(f"CSS Load Error: {e}")

    def init_ui(self):
        # حاوية رئيسية للتحكم بالهامش العام
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15) # زيادة المسافة
        main_box.get_style_context().add_class("main-container") # لتطبيق الحشوة من CSS
        self.add(main_box)

        # --- قسم معلومات النظام ---
        status_title = Gtk.Label(label="📊 معلومات النظام", xalign=0)
        status_title.get_style_context().add_class("section-title")
        main_box.pack_start(status_title, False, False, 0)

        grid_status = Gtk.Grid(row_spacing=10, column_spacing=15) # زيادة المسافات
        main_box.pack_start(grid_status, False, False, 0)

        lbl_cpu = Gtk.Label(label="المعالج:", xalign=0)
        grid_status.attach(lbl_cpu, 0, 0, 1, 1)
        self.cpu_bar = Gtk.ProgressBar(text="0%", show_text=True)
        self.cpu_bar.set_hexpand(True)
        grid_status.attach(self.cpu_bar, 1, 0, 1, 1)
        self.cpu_temp_label = Gtk.Label(label="N/A", xalign=1, width_chars=6)
        grid_status.attach(self.cpu_temp_label, 2, 0, 1, 1)

        lbl_ram = Gtk.Label(label="الذاكرة:", xalign=0)
        grid_status.attach(lbl_ram, 0, 1, 1, 1)
        self.ram_bar = Gtk.ProgressBar(text="0%", show_text=True)
        self.ram_bar.set_hexpand(True)
        grid_status.attach(self.ram_bar, 1, 1, 2, 1)

        lbl_disk = Gtk.Label(label="القرص (/):", xalign=0)
        grid_status.attach(lbl_disk, 0, 2, 1, 1)
        self.disk_bar = Gtk.ProgressBar(text="0%", show_text=True)
        self.disk_bar.set_hexpand(True)
        grid_status.attach(self.disk_bar, 1, 2, 2, 1)

        # --- قسم العمليات ---
        actions_title = Gtk.Label(label="🚀 العمليات", xalign=0)
        actions_title.get_style_context().add_class("section-title")
        main_box.pack_start(actions_title, False, False, 0)

        hbox_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_box.pack_start(hbox_actions, False, False, 0)

        grid_actions = Gtk.Grid(row_spacing=10, column_spacing=10)
        grid_actions.set_hexpand(True)
        hbox_actions.pack_start(grid_actions, True, True, 0)

        actions = [
            ("تنظيف خفيف", self.on_light_clean, "إزالة الملفات المؤقتة وتفريغ كاش الصفحة", "edit-clear-symbolic"),
            ("تنظيف عميق", self.on_deep_clean, "تنظيف شامل للكاش والسجلات (يتطلب صلاحيات)", "edit-delete-symbolic"),
            ("إصلاح الحزم", self.on_fix_errors, "محاولة إصلاح مشاكل الحزم المعلقة (يتطلب صلاحيات)", "system-run-symbolic"),
            ("🚀 تعزيز الأداء", self.on_boost_performance, "إيقاف خدمات ورفع أولوية التطبيق (تجريبي ويتطلب صلاحيات)", "preferences-system-symbolic"),
            ("🌐 تعزيز الشبكة/الألعاب", self.on_network_game_boost, "تعديلات مؤقتة للشبكة والمعالج لتحسين الألعاب (يتطلب صلاحيات)", "network-workgroup-symbolic"), # تغيير الأيقونة
            ("عرض الحالة", self.on_show_status, "عرض معلومات النظام الحالية", "dialog-information-symbolic"),
        ]

        self.buttons = []
        cols = 3 # تجربة 3 أعمدة
        for idx, (lbl, handler, tip, icon_name) in enumerate(actions):
            btn_box = Gtk.Box(spacing=6)
            try: icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
            except GLib.Error:
                 try: icon = Gtk.Image.new_from_icon_name(icon_name.replace("-symbolic",""), Gtk.IconSize.BUTTON)
                 except GLib.Error: icon = Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.BUTTON)
            label_widget = Gtk.Label(label=lbl)
            btn_box.pack_start(icon, False, False, 0)
            btn_box.pack_start(label_widget, True, True, 0)
            btn = Gtk.Button(); btn.add(btn_box); btn.set_tooltip_text(tip); btn.connect("clicked", handler)
            grid_actions.attach(btn, idx % cols, idx // cols, 1, 1)
            btn.set_hexpand(True)
            self.buttons.append(btn)

        self.spinner.set_valign(Gtk.Align.CENTER); self.spinner.set_halign(Gtk.Align.CENTER)
        hbox_actions.pack_start(self.spinner, False, False, 15) # زيادة المسافة للـ Spinner

        # --- قسم سجل النشاط ---
        log_title = Gtk.Label(label="📝 سجل النشاط", xalign=0)
        log_title.get_style_context().add_class("section-title")
        main_box.pack_start(log_title, False, False, 0)

        box_log = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.pack_start(box_log, True, True, 0) # السماح بالتمدد

        self.log_scroll_window = Gtk.ScrolledWindow()
        self.log_scroll_window.set_hexpand(True)
        self.log_scroll_window.set_vexpand(True)
        self.log_scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_scroll_window.set_name("logview_container") # اسم لـ CSS

        self.logview = Gtk.TextView()
        self.logview.set_editable(False)
        self.logview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.logview.set_name("logview_widget") # اسم لـ CSS
        self.log_scroll_window.add(self.logview) # إضافة TextView إلى ScrolledWindow

        box_log.pack_start(self.log_scroll_window, True, True, 0)

        action_bar = Gtk.ActionBar()
        box_log.pack_start(action_bar, False, False, 0)
        clear_log_button = Gtk.Button(label="مسح السجل")
        clear_log_button.set_tooltip_text("مسح جميع الرسائل من نافذة السجل")
        try:
            clear_icon = Gtk.Image.new_from_icon_name("edit-clear-symbolic", Gtk.IconSize.BUTTON)
            clear_log_button.set_image(clear_icon); clear_log_button.set_always_show_image(True)
        except GLib.Error: pass
        clear_log_button.connect("clicked", self.on_clear_log)
        action_bar.pack_end(clear_log_button)

    def on_clear_log(self, widget):
        if self.logview:
            buffer = self.logview.get_buffer()
            buffer.set_text("")
            self.log("تم مسح السجل.")

    def set_buttons_sensitive(self, sensitive):
        GLib.idle_add(self._set_buttons_sensitive_idle, sensitive)

    def _set_buttons_sensitive_idle(self, sensitive):
        for btn in self.buttons:
            label_widget = self._find_child_label(btn)
            label_text = label_widget.get_text() if label_widget else ""
            if "عرض الحالة" not in label_text :
                btn.set_sensitive(sensitive)
        return False

    def _find_child_label(self, widget):
         if isinstance(widget, Gtk.Label): return widget
         if isinstance(widget, Gtk.Container):
             for child in widget.get_children():
                 found = self._find_child_label(child);
                 if found: return found
         return None

    def set_spinner_active(self, active):
         GLib.idle_add(self._set_spinner_active_idle, active)

    def _set_spinner_active_idle(self, active):
         if active: self.spinner.start(); self.spinner.show()
         else: self.spinner.stop(); self.spinner.hide()
         return False

    def optimize_performance(self):
        self.log("محاولة ضبط إعدادات الأداء الأولية...")
        sysctl_cmds = ["sysctl -w vm.swappiness=10", "sysctl -w vm.vfs_cache_pressure=50"]
        full_cmd = f"pkexec sh -c \"{ ' && '.join(sysctl_cmds) }\""
        success = True
        self.set_buttons_sensitive(False); self.set_spinner_active(True)
        try:
            result = subprocess.run(full_cmd, shell=True, check=True, capture_output=True, text=True, timeout=60)
            self.log(f"  ✅ نجحت أوامر sysctl الأولية.")
            if result.stdout and len(result.stdout.strip()) > 0 : self.log(f"     المخرج:\n        {result.stdout.strip().replace(' = ', '=')}")
        except subprocess.CalledProcessError as e:
            success = False; self.log(f"  ❌ فشلت أوامر sysctl الأولية."); self.log(f"     رمز الخطأ: {e.returncode}")
            if e.stderr and len(e.stderr.strip()) > 0 :
                 log_stderr = "\n        ".join(e.stderr.strip().splitlines()[:5]);
                 if len(e.stderr.strip().splitlines()) > 5: log_stderr += "\n        ... (تم اختصار الخطأ)"
                 self.log(f"     الخطأ:\n        {log_stderr}")
            if e.returncode in [126, 127]: self.log("     تم إلغاء العملية أو فشلت المصادقة.")
        except subprocess.TimeoutExpired: success = False; self.log(f"  ⌛ فشل: انتهت المهلة لأوامر sysctl الأولية")
        except FileNotFoundError: success = False; self.log(f"  ❓ فشل: هل 'pkexec' أو 'sysctl' مثبت؟")
        except Exception as e: success = False; self.log(f"  💥 فشل: خطأ غير متوقع: {e}")
        self.set_buttons_sensitive(True); self.set_spinner_active(False)
        if success: self.play_sound("success"); self.log("👍 تم ضبط إعدادات الأداء الأولية.")
        else: self.play_sound("error"); self.log("⚠️ فشل ضبط بعض إعدادات الأداء الأولية.")

    def perform_actions(self, cmds_or_cmd_string, action_name):
        def task():
            self.set_buttons_sensitive(False); self.set_spinner_active(True)
            self.log(f"⏳ بدء: {action_name}..."); self.play_sound("info")
            all_success = True; command_list_to_run = []

            if isinstance(cmds_or_cmd_string, str): command_list_to_run = [cmds_or_cmd_string]
            elif isinstance(cmds_or_cmd_string, list):
                 pkexec_group = []
                 for cmd in cmds_or_cmd_string:
                     if cmd.strip().startswith("pkexec"): pkexec_group.append(cmd.strip().replace("pkexec ", "", 1))
                     else:
                         if pkexec_group:
                              joined_cmds = " && ".join(pkexec_group)
                              command_list_to_run.append(f"pkexec sh -c \"{joined_cmds}\""); pkexec_group = []
                         command_list_to_run.append(cmd)
                 if pkexec_group:
                      joined_cmds = " && ".join(pkexec_group)
                      command_list_to_run.append(f"pkexec sh -c \"{joined_cmds}\"")
            else: self.log(f"❌ خطأ داخلي: نوع إدخال غير صالح: {type(cmds_or_cmd_string)}"); all_success = False

            for cmd_to_run in command_list_to_run:
                 is_pkexec_group = cmd_to_run.startswith("pkexec sh -c"); log_cmd_display = cmd_to_run
                 if is_pkexec_group:
                    inner_cmds = cmd_to_run.split('"')[1].split('&&'); log_cmd_display = f"مجموعة أوامر بصلاحيات ({len(inner_cmds)})"
                 elif cmd_to_run.strip().startswith(("sync", "find")): continue # تخطي تسجيل الأوامر البسيطة
                 self.log(f"  ‹‹ {log_cmd_display}")
                 try:
                    timeout_seconds = 180
                    result = subprocess.run(cmd_to_run, shell=True, check=True, capture_output=True, text=True, timeout=timeout_seconds)
                    if result.stdout and len(result.stdout.strip()) > 0 and not log_cmd_display.startswith(("sysctl", "echo", "sync", "مجموعة أوامر")):
                        output_lines = result.stdout.strip().splitlines(); log_output = "\n     ".join(output_lines[:5])
                        if len(output_lines) > 5: log_output += "\n     ... (تم اختصار المخرج)"
                        self.log(f"     {log_output}")
                 except subprocess.CalledProcessError as e:
                    all_success = False; self.log(f"  ❌ فشل تنفيذ: {log_cmd_display}"); self.log(f"     رمز الخطأ: {e.returncode}")
                    if e.stderr and len(e.stderr.strip()) > 0:
                         log_stderr = "\n        ".join(e.stderr.strip().splitlines()[:5])
                         if len(e.stderr.strip().splitlines()) > 5: log_stderr += "\n        ... (تم اختصار الخطأ)"
                         self.log(f"     الخطأ:\n        {log_stderr}")
                    if 'pkexec' in cmd_to_run and e.returncode in [126, 127]: self.log("     تم إلغاء نافذة المصادقة أو فشلت.")
                    break
                 except subprocess.TimeoutExpired: all_success = False; self.log(f"  ⌛ فشل: {log_cmd_display} (انتهت المهلة)"); break
                 except FileNotFoundError:
                    cmd_name = cmd_to_run.split(' ')[0]; msg = f"  ❓ فشل: الأمر '{cmd_name}' غير موجود."
                    if 'pkexec' in cmd_name: msg += " تأكد أيضًا من تثبيت 'pkexec'."
                    self.log(msg); all_success = False; break
                 except Exception as e: all_success = False; self.log(f"  💥 فشل: {log_cmd_display} بخطأ: {type(e).__name__} - {e}"); break

            self.set_buttons_sensitive(True); self.set_spinner_active(False)
            if all_success: self.play_sound("success"); self.log(f"🎉 اكتمل بنجاح: {action_name}")
            else: self.play_sound("error"); self.log(f"⚠️ اكتمل مع أخطاء: {action_name}")

        thread = threading.Thread(target=task, daemon=True); thread.start()

    def on_show_status(self, btn):
        cpu_usage = f"{self.system_info.get_cpu_usage():.1f}%"; ram_usage = f"{self.system_info.get_ram_usage():.1f}%"
        disk_usage_val = f"{self.system_info.get_disk_usage('/'):.1f}%"; temp_str = self.system_info.get_temperature()
        primary_text = "📊 <b>حالة النظام الحالية</b>"
        secondary_text = (f"<b>المعالج (CPU):</b> {cpu_usage} ({temp_str})\n"
                          f"<b>الذاكرة (RAM):</b> {ram_usage}\n"
                          f"<b>استهلاك القرص (/):</b> {disk_usage_val}")
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, text=primary_text)
        dialog.format_secondary_markup(secondary_text); dialog.set_title("حالة النظام")
        try: dialog.set_icon_name("utilities-system-monitor-symbolic") # أيقونة رمزية أخرى
        except GLib.Error: pass
        dialog.run(); dialog.destroy()

    def on_light_clean(self, btn):
        self.log("طلب إجراء: تنظيف خفيف")
        cmds = ["sync", "pkexec sh -c 'echo 1 > /proc/sys/vm/drop_caches'", "find ~/.cache/ -maxdepth 1 -type f -delete", "find ~/.cache/ -maxdepth 1 -mindepth 1 -type d -empty -delete"]
        self.perform_actions(cmds, "تنظيف خفيف")

    def on_deep_clean(self, btn):
        self.log("طلب إجراء: تنظيف عميق")
        cmds = ["sync", "pkexec sh -c 'echo 3 > /proc/sys/vm/drop_caches'", "find ~/.cache/ -maxdepth 1 -type f -delete", "find ~/.cache/ -maxdepth 1 -mindepth 1 -type d -exec rm -rf {} +", "pkexec journalctl --vacuum-size=100M"]
        self.perform_actions(cmds, "تنظيف عميق")

    def on_fix_errors(self, btn):
        self.log("طلب إجراء: إصلاح الحزم")
        cmds = ["pkexec apt-get update", "pkexec dpkg --configure -a", "pkexec apt-get install --fix-broken -y"]
        self.perform_actions(cmds, "إصلاح الحزم")

    def on_boost_performance(self, btn):
        self.log("طلب إجراء: تعزيز الأداء")
        services_to_stop = ["apt-daily.timer", "apt-daily-upgrade.timer"]
        current_pid = os.getpid(); cmds_to_run_privileged = []
        if services_to_stop: cmds_to_run_privileged.extend([f"systemctl stop {service}" for service in services_to_stop])
        cmds_to_run_privileged.append(f"renice -n -10 -p {current_pid}")
        full_cmd = f"pkexec sh -c \"{ ' && '.join(cmds_to_run_privileged) }\""
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.YES_NO, text="⚠️ تحذير: تعزيز الأداء (تجريبي)")
        warning_text = "سيقوم هذا الإجراء بمحاولة:\n";
        if services_to_stop: warning_text += f" - إيقاف الخدمات التالية: {', '.join(services_to_stop)}\n"
        warning_text += f" - زيادة أولوية التطبيق (PID: {current_pid}).\n\nهل أنت متأكد؟ (قد يتطلب كلمة المرور)"
        dialog.format_secondary_markup(warning_text); dialog.set_title("تأكيد تعزيز الأداء")
        response = dialog.run(); dialog.destroy()
        if response == Gtk.ResponseType.YES: self.perform_actions(full_cmd, "تعزيز الأداء")
        else: self.log("تم إلغاء عملية تعزيز الأداء.")

    def on_network_game_boost(self, btn):
        self.log("طلب إجراء: تعزيز الشبكة والألعاب")
        privileged_cmds = []
        network_tweaks = ["sysctl -w net.ipv4.tcp_low_latency=1", "sysctl -w net.core.netdev_max_backlog=50000", "sysctl -w net.ipv4.tcp_timestamps=0", "sysctl -w net.ipv4.tcp_sack=1"]
        privileged_cmds.extend(network_tweaks); self.log("  + تعديلات الشبكة (sysctl) جاهزة.")
        cpu_governor_cmd = None
        if self.system_info.check_command_exists("cpupower"): cpu_governor_cmd = "cpupower frequency-set -g performance"
        elif self.system_info.check_command_exists("cpufreq-set"): cpu_governor_cmd = "cpufreq-set -r -g performance"
        if cpu_governor_cmd: privileged_cmds.append(cpu_governor_cmd); self.log(f"  + سيتم محاولة تعيين حاكم المعالج إلى 'performance'.")
        else: self.log("  - أدوات cpupower/cpufreq-set غير موجودة.")
        wifi_interface = self.system_info.find_active_wifi_interface(); iw_exists = self.system_info.check_command_exists("iw")
        if wifi_interface and iw_exists: wifi_cmd = f"iw dev {wifi_interface} set power_save off"; privileged_cmds.append(wifi_cmd); self.log(f"  + سيتم محاولة تعطيل توفير الطاقة لـ '{wifi_interface}'.")
        elif not iw_exists: self.log("  - أداة 'iw' غير موجودة.")
        else: self.log("  - لم يتم العثور على واجهة واي فاي نشطة.")
        if privileged_cmds:
            full_cmd = f"pkexec sh -c \"{ ' && '.join(privileged_cmds) }\""
            dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING, buttons=Gtk.ButtonsType.YES_NO, text="⚠️ تحذير: تعزيز الشبكة والألعاب (تجريبي)")
            warning_text = ("سيطبق تعديلات مؤقتة على الشبكة والمعالج.\nهل أنت متأكد؟ (قد يتطلب كلمة المرور)")
            dialog.format_secondary_markup(warning_text); dialog.set_title("تأكيد تعزيز الشبكة والألعاب")
            response = dialog.run(); dialog.destroy()
            if response == Gtk.ResponseType.YES: self.perform_actions([full_cmd], "تعزيز الشبكة والألعاب") # تمرير كقائمة
            else: self.log("تم إلغاء عملية تعزيز الشبكة والألعاب.")
        else: self.log("  ! لا توجد أوامر بصلاحيات لتنفيذها."); self.play_sound("error")

    def log(self, msg):
        if not self.logview: return # التأكد من تهيئة logview
        def _log_idle():
            try:
                buf = self.logview.get_buffer(); end_iter = buf.get_end_iter()
                timestamp = datetime.now().strftime('%H:%M:%S'); clean_msg = GLib.markup_escape_text(msg)
                buf.insert(end_iter, f"[{timestamp}] {clean_msg}\n")
                GLib.timeout_add(50, self._scroll_log_to_end)
            except Exception as e: print(f"Error in logging: {e}")
            return False
        GLib.idle_add(_log_idle)

    def _scroll_log_to_end(self):
        if self.log_scroll_window: # التحقق من وجود نافذة التمرير
            try:
                adj = self.log_scroll_window.get_vadjustment() # استخدام الطريقة الصحيحة
                if adj: adj.set_value(adj.get_upper() - adj.get_page_size())
            except Exception as e: print(f"Error scrolling log: {e}")
        return False

    def play_sound(self, sound_type):
        if not pygame.mixer.get_init(): return
        try:
            freq, dur, amp_f = 0, 0, 0
            if sound_type == "success": freq, dur, amp_f = 523.25, 0.25, 0.4
            elif sound_type == "error": freq, dur, amp_f = 261.63, 0.4, 0.5
            elif sound_type == "info": freq, dur, amp_f = 659.25, 0.2, 0.3
            else: return
            sr = pygame.mixer.get_init()[0];
            if sr == 0: print("Error: Sample rate is 0."); return
            ns = int(sr * dur);
            if ns <= 0: return
            t = np.linspace(0., dur, ns, endpoint=False); amp = np.iinfo(np.int16).max * amp_f
            s = amp * np.sin(2. * np.pi * freq * t); fl = int(sr * 0.02);
            if ns > fl * 2: s[:fl] *= np.linspace(0., 1., fl); s[-fl:] *= np.linspace(1., 0., fl)
            sa = np.array(s, dtype=np.int16)
            if len(sa.shape) == 1: ssa = np.ascontiguousarray(np.column_stack((sa, sa)))
            else: ssa = np.ascontiguousarray(sa)
            sound = pygame.sndarray.make_sound(ssa); sound.play()
        except NameError: self.log("⚠️ مكتبة numpy غير موجودة.")
        except Exception as e: print(f"Sound Error: {type(e).__name__} - {e}")

    def update_info(self):
        try:
            cpu = self.system_info.get_cpu_usage(); self.cpu_bar.set_fraction(cpu / 100); self.cpu_bar.set_text(f"{cpu:.1f}%")
            ram_pct = self.system_info.get_ram_usage(); self.ram_bar.set_fraction(ram_pct / 100); self.ram_bar.set_text(f"{ram_pct:.1f}%")
            disk_pct = self.system_info.get_disk_usage('/'); self.disk_bar.set_fraction(disk_pct / 100); self.disk_bar.set_text(f"{disk_pct:.1f}%")
            temp = self.system_info.get_temperature(); self.cpu_temp_label.set_text(temp)
        except Exception as e: print(f"Update Info Error: {e}")
        return True

    def on_quit(self, widget):
        self.log("جاري إغلاق التطبيق...")
        if pygame.mixer.get_init(): pygame.mixer.quit(); print("Pygame mixer stopped.")
        Gtk.main_quit()

if __name__ == "__main__":
    lock_file_path = os.path.join(GLib.get_user_runtime_dir(), "flashboost_app.lock")
    lock_file = None
    try:
        lock_file = os.open(lock_file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NONBLOCK)
        os.write(lock_file, str(os.getpid()).encode())
        app = FlashBoostApp()
        app.show_all(); app.spinner.hide()
        Gtk.main()
    except FileExistsError:
        print("تطبيق FlashBoostApp يعمل بالفعل.")
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK, text="خطأ")
        dialog.format_secondary_text("يبدو أن تطبيق FlashBoostApp يعمل بالفعل في الخلفية.")
        dialog.run(); dialog.destroy()
    except OSError as e: print(f"خطأ في ملف القفل: {e}"); app = FlashBoostApp(); app.show_all(); app.spinner.hide(); Gtk.main() # تشغيل على أي حال
    finally:
        if lock_file is not None:
            try: os.close(lock_file); os.remove(lock_file_path)
            except OSError as e: print(f"خطأ في إزالة ملف القفل: {e}")
