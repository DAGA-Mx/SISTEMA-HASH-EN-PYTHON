# =====================================================================
# PROYECTO: Detector de Archivos Duplicados
# AUTORS: [Dilan A. González Alatriste / Equipo de Desarrollo]
# MATERIA: Estructuras de Datos y sus Aplicaciones
# DESCRIPCIÓN: Interfaz gráfica moderna (CustomTkinter) de alto rendimiento.
#              Permite seleccionar carpetas, configurar filtros, ver
#              progreso en tiempo real, exportar CSV y eliminar duplicados.
# =====================================================================

import os
import csv
import queue
import threading
import sys
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Importar el escáner del módulo scanner.py
from scanner import DuplicateScanner, is_hidden_or_system

# Configurar apariencia por defecto de CustomTkinter
ctk.set_appearance_mode("dark")  # Modos: "system", "light", "dark"
ctk.set_default_color_theme("blue")  # Temas: "blue", "green", "dark-blue"


def format_size(size_bytes: int) -> str:
    """Formatea bytes en formato legible (B, KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class CustomConfirmDialog(ctk.CTkToplevel):
    """
    Ventana de diálogo personalizada y estilizada para confirmación de acciones críticas.
    """
    def __init__(self, parent, title: str, message: str, on_confirm: callable):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Centrar ventana con respecto al padre
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 225
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 110
        self.geometry(f"+{x}+{y}")

        self.on_confirm = on_confirm
        self.confirmed = False

        # Configuración de grid
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Contenedor del mensaje
        self.message_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.message_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=20, sticky="nsew")
        
        self.msg_label = ctk.CTkLabel(
            self.message_frame, 
            text=message, 
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wraplength=400,
            justify="center"
        )
        self.msg_label.pack(expand=True, fill="both")

        # Botones de Acción
        self.btn_cancel = ctk.CTkButton(
            self, 
            text="Cancelar", 
            fg_color="#4a4a4a",
            hover_color="#5a5a5a",
            command=self.close
        )
        self.btn_cancel.grid(row=1, column=0, padx=(20, 10), pady=(0, 20), sticky="ew")

        self.btn_confirm = ctk.CTkButton(
            self, 
            text="Confirmar Eliminación", 
            fg_color="#d9534f",
            hover_color="#c9302c",
            command=self.confirm
        )
        self.btn_confirm.grid(row=1, column=1, padx=(10, 20), pady=(0, 20), sticky="ew")

    def confirm(self):
        self.confirmed = True
        self.on_confirm()
        self.close()

    def close(self):
        self.grab_release()
        self.destroy()


class DuplicateDetectorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración de Ventana
        self.title("Deduplicador de Archivos Inteligente (3 Etapas)")
        self.geometry("1100x700")
        self.minsize(950, 600)

        # Variables de estado
        self.scan_directories = []
        self.scan_queue = queue.Queue()
        self.scanner = DuplicateScanner()
        self.duplicates = {}  # { full_hash: [(path, size), ...] }
        self.checkbox_vars = {}  # { filepath: StringVar/BooleanVar }
        self.scan_thread = None

        # Configuración de Grid Principal (Layout de 2 Columnas)
        # Columna 0: Sidebar (Configuración)
        # Columna 1: Panel Principal (Estadísticas y Resultados)
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Crear componentes UI
        self.create_sidebar()
        self.create_main_panel()

        # Iniciar polling para cola de progreso
        self.poll_queue()

    # =====================================================================
    # CREACIÓN DE LA INTERFAZ GRÁFICA
    # =====================================================================
    def create_sidebar(self):
        """Crea el panel lateral izquierdo con controles de configuración."""
        self.sidebar = ctk.CTkFrame(self, corner_radius=0, width=280)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(7, weight=1)  # Expandir espacio inferior

        # Título del Logo
        self.logo_label = ctk.CTkLabel(
            self.sidebar, 
            text="⚙ DETECTOR HASH", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#1f538d"
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 5))

        self.subtitle_label = ctk.CTkLabel(
            self.sidebar, 
            text="Deduplicador en 3 Etapas", 
            font=ctk.CTkFont(family="Segoe UI", size=12, slant="italic"),
            text_color="#a0a0a0"
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Sección Directorios
        self.dir_frame_label = ctk.CTkLabel(
            self.sidebar, 
            text="Carpetas de Escaneo", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        self.dir_frame_label.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")

        # Lista de Directorios Agregados (Caja de texto no editable)
        self.dir_list_box = ctk.CTkTextbox(
            self.sidebar, 
            height=120, 
            width=240, 
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled"
        )
        self.dir_list_box.grid(row=3, column=0, padx=20, pady=5)

        # Botones para gestionar directorios
        self.dir_btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.dir_btn_frame.grid(row=4, column=0, padx=20, pady=5, sticky="ew")
        self.dir_btn_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_add_dir = ctk.CTkButton(
            self.dir_btn_frame, 
            text="+ Agregar", 
            height=28,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.add_directory
        )
        self.btn_add_dir.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_clear_dirs = ctk.CTkButton(
            self.dir_btn_frame, 
            text="🗑 Limpiar", 
            height=28,
            fg_color="#4a4a4a",
            hover_color="#5a5a5a",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.clear_directories
        )
        self.btn_clear_dirs.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Filtros de Extensión
        self.filter_label = ctk.CTkLabel(
            self.sidebar, 
            text="Filtro de Extensiones", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
        )
        self.filter_label.grid(row=5, column=0, padx=20, pady=(20, 5), sticky="w")

        self.checkbox_filter = ctk.CTkCheckBox(
            self.sidebar, 
            text="Habilitar Filtros", 
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self.toggle_filter_entry
        )
        self.checkbox_filter.grid(row=6, column=0, padx=20, pady=5, sticky="w")
        self.checkbox_filter.select()

        self.entry_extensions = ctk.CTkEntry(
            self.sidebar, 
            placeholder_text="txt, jpg, png", 
            width=240,
            font=ctk.CTkFont(family="Segoe UI", size=12)
        )
        self.entry_extensions.grid(row=7, column=0, padx=20, pady=5, sticky="nw")
        self.entry_extensions.insert(0, "txt, jpg")

        # Selector de Tema (Oscuro/Claro)
        self.theme_label = ctk.CTkLabel(
            self.sidebar, 
            text="Tema de Interfaz", 
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        self.theme_label.grid(row=8, column=0, padx=20, pady=(10, 0), sticky="w")

        self.theme_option = ctk.CTkOptionMenu(
            self.sidebar, 
            values=["Oscuro", "Claro"], 
            width=240,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self.change_theme
        )
        self.theme_option.grid(row=9, column=0, padx=20, pady=(5, 20), sticky="s")

    def create_main_panel(self):
        """Crea el panel principal derecho con estadísticas y visualizador de duplicados."""
        self.main_panel = ctk.CTkFrame(self, fg_color="transparent")
        self.main_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_panel.grid_columnconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(3, weight=1)  # Dar peso al panel de resultados scrollable

        # 1. Cabecera y Botones de Acción de Escaneo
        self.header_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.header_frame.grid_columnconfigure(0, weight=1)
        self.header_frame.grid_columnconfigure((1, 2), weight=0)

        self.header_title = ctk.CTkLabel(
            self.header_frame, 
            text="Panel de Control y Deduplicación", 
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
        )
        self.header_title.grid(row=0, column=0, sticky="w")

        self.btn_start = ctk.CTkButton(
            self.header_frame, 
            text="Iniciar Escaneo", 
            fg_color="#1f538d",
            hover_color="#14375e",
            width=140,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.start_scanning
        )
        self.btn_start.grid(row=0, column=1, padx=10, sticky="e")

        self.btn_cancel = ctk.CTkButton(
            self.header_frame, 
            text="Cancelar", 
            state="disabled",
            fg_color="#4a4a4a",
            hover_color="#5a5a5a",
            width=110,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self.cancel_scanning
        )
        self.btn_cancel.grid(row=0, column=2, sticky="e")

        # 2. Barra de Progreso y Estado
        self.progress_frame = ctk.CTkFrame(self.main_panel)
        self.progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15), padx=2)
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame, 
            text="Estado: En espera de directorios...", 
            font=ctk.CTkFont(family="Segoe UI", size=12),
            anchor="w"
        )
        self.progress_label.grid(row=0, column=0, padx=15, pady=(10, 5), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="ew")
        self.progress_bar.set(0)

        # 3. Tarjetas de Estadísticas (Fila de 3 Tarjetas)
        self.stats_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.stats_frame.grid(row=2, column=0, sticky="ew", pady=(0, 15))
        self.stats_frame.grid_columnconfigure((0, 1, 2), weight=1, uniform="stats")

        # Tarjeta 1: Total archivos analizados
        self.card_total = ctk.CTkFrame(self.stats_frame)
        self.card_total.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.lbl_card_total_title = ctk.CTkLabel(self.card_total, text="Archivos Analizados", font=ctk.CTkFont(size=11, slant="italic"), text_color="#a0a0a0")
        self.lbl_card_total_title.pack(pady=(10, 2))
        self.lbl_card_total_val = ctk.CTkLabel(self.card_total, text="0", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_card_total_val.pack(pady=(2, 10))

        # Tarjeta 2: Grupos duplicados encontrados
        self.card_groups = ctk.CTkFrame(self.stats_frame)
        self.card_groups.grid(row=0, column=1, padx=5, sticky="nsew")
        self.lbl_card_groups_title = ctk.CTkLabel(self.card_groups, text="Grupos Duplicados", font=ctk.CTkFont(size=11, slant="italic"), text_color="#a0a0a0")
        self.lbl_card_groups_title.pack(pady=(10, 2))
        self.lbl_card_groups_val = ctk.CTkLabel(self.card_groups, text="0", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_card_groups_val.pack(pady=(2, 10))

        # Tarjeta 3: Espacio recuperable (Destacado)
        self.card_space = ctk.CTkFrame(self.stats_frame, border_color="#2b753f", border_width=1)
        self.card_space.grid(row=0, column=2, padx=(10, 0), sticky="nsew")
        self.lbl_card_space_title = ctk.CTkLabel(self.card_space, text="Espacio Potencial Recuperable", font=ctk.CTkFont(size=11, slant="italic"), text_color="#a0a0a0")
        self.lbl_card_space_title.pack(pady=(10, 2))
        self.lbl_card_space_val = ctk.CTkLabel(self.card_space, text="0.00 B", font=ctk.CTkFont(size=20, weight="bold"), text_color="#2ecc71")
        self.lbl_card_space_val.pack(pady=(2, 10))

        # 4. Panel de Resultados de Duplicados
        self.results_title_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.results_title_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        self.results_title_frame.grid_columnconfigure(0, weight=1)
        
        self.results_label = ctk.CTkLabel(
            self.results_title_frame, 
            text="Resultados de Grupos Duplicados", 
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        )
        self.results_label.grid(row=0, column=0, sticky="w")
        
        self.lbl_errors_badge = ctk.CTkLabel(
            self.results_title_frame, 
            text="", 
            font=ctk.CTkFont(family="Segoe UI", size=11), 
            text_color="#e74c3c",
            cursor="hand2"
        )
        self.lbl_errors_badge.grid(row=0, column=1, sticky="e")
        self.lbl_errors_badge.bind("<Button-1>", self.show_error_log)

        # Scrollable Frame para albergar las tarjetas de grupos duplicados
        self.results_scroll = ctk.CTkScrollableFrame(self.main_panel, label_text="")
        self.results_scroll.grid(row=4, column=0, sticky="nsew", pady=(0, 15))

        # 5. Barra de Acciones Finales (Pie de Página)
        self.footer_frame = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.footer_frame.grid(row=5, column=0, sticky="ew")
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure((1, 2), weight=0)

        self.status_bar_info = ctk.CTkLabel(
            self.footer_frame, 
            text="Listo.", 
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#808080"
        )
        self.status_bar_info.grid(row=0, column=0, sticky="w")

        self.btn_export_csv = ctk.CTkButton(
            self.footer_frame, 
            text="Exportar Reporte CSV", 
            state="disabled",
            fg_color="#2b753f",
            hover_color="#1e522c",
            width=160,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self.export_csv
        )
        self.btn_export_csv.grid(row=0, column=1, padx=10, sticky="e")

        self.btn_delete_selected = ctk.CTkButton(
            self.footer_frame, 
            text="Eliminar Seleccionados", 
            state="disabled",
            fg_color="#d9534f",
            hover_color="#c9302c",
            width=180,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self.confirm_and_delete
        )
        self.btn_delete_selected.grid(row=0, column=2, sticky="e")

    # =====================================================================
    # ACCIONES DE INTERFAZ GRÁFICA
    # =====================================================================
    def change_theme(self, choice):
        """Cambia el tema de color entre Oscuro y Claro."""
        if choice == "Oscuro":
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")

    def toggle_filter_entry(self):
        """Habilita o deshabilita la caja de texto del filtro de extensiones."""
        if self.checkbox_filter.get():
            self.entry_extensions.configure(state="normal")
        else:
            self.entry_extensions.configure(state="disabled")

    def add_directory(self):
        """Abre un selector de carpetas y lo agrega a la lista de escaneo."""
        path = filedialog.askdirectory(title="Seleccionar Carpeta para Escaneo")
        if path:
            path = os.path.abspath(path)
            if path not in self.scan_directories:
                self.scan_directories.append(path)
                self.update_directory_textbox()
                self.status_bar_info.configure(text=f"Carpeta agregada: {path}")

    def clear_directories(self):
        """Limpia los directorios seleccionados."""
        self.scan_directories.clear()
        self.update_directory_textbox()
        self.status_bar_info.configure(text="Lista de carpetas limpia.")

    def update_directory_textbox(self):
        """Actualiza el texto en la caja de lista de directorios."""
        self.dir_list_box.configure(state="normal")
        self.dir_list_box.delete("1.0", tk.END)
        for d in self.scan_directories:
            self.dir_list_box.insert(tk.END, f"{d}\n")
        self.dir_list_box.configure(state="disabled")

    def show_error_log(self, event=None):
        """Muestra los errores reportados durante el escaneo en una ventana emergente."""
        if not self.scanner.errors:
            return
        
        err_win = ctk.CTkToplevel(self)
        err_win.title("Registro de Errores del Escáner")
        err_win.geometry("600x400")
        err_win.transient(self)
        
        lbl = ctk.CTkLabel(err_win, text="Se registraron las siguientes advertencias/errores (archivos bloqueados u omitidos):", font=ctk.CTkFont(weight="bold"))
        lbl.pack(padx=20, pady=10, anchor="w")
        
        text = ctk.CTkTextbox(err_win, font=ctk.CTkFont(family="Consolas", size=11))
        text.pack(expand=True, fill="both", padx=20, pady=(0, 20))
        
        for err in self.scanner.errors:
            text.insert(tk.END, f"- {err}\n")
        text.configure(state="disabled")

    # =====================================================================
    # LÓGICA DE PROCESAMIENTO HILADA (THREADED BACKGROUND SCAN)
    # =====================================================================
    def poll_queue(self):
        """Revisa periódicamente la cola para actualizaciones desde el hilo de escaneo."""
        try:
            while True:
                msg_type, val1, val2, details = self.scan_queue.get_nowait()
                self.process_scan_event(msg_type, val1, val2, details)
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def process_scan_event(self, msg_type: str, val1: Any, val2: Any, details: str):
        """Procesa un evento recibido de la cola de escaneo."""
        if msg_type == 'scanning':
            self.progress_label.configure(text=details)
            # Progreso indeterminado durante escaneo inicial
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self.lbl_card_total_val.configure(text=str(val1))
            
        elif msg_type == 'scanning_done':
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
            self.progress_label.configure(text=details)
            self.lbl_card_total_val.configure(text=str(val2))
            
        elif msg_type == 'partial_hashing':
            self.progress_label.configure(text=details)
            if val2 > 0:
                self.progress_bar.set(val1 / val2)
                
        elif msg_type == 'partial_done':
            self.progress_label.configure(text=details)
            self.progress_bar.set(0)
            
        elif msg_type == 'full_hashing':
            self.progress_label.configure(text=details)
            if val2 > 0:
                self.progress_bar.set(val1 / val2)
                
        elif msg_type == 'completed':
            self.progress_bar.set(1.0)
            self.progress_label.configure(text=details)
            self.lbl_card_groups_val.configure(text=str(val1))
            self.lbl_card_total_val.configure(text=str(val2))
            self.duplicates = self.scanner.scan_result_dict  # Recuperar datos
            self.display_results()
            self.finalize_scan_ui()
            
            # Mostrar botón de error si hay errores
            if self.scanner.errors:
                self.lbl_errors_badge.configure(text=f"⚠️ {len(self.scanner.errors)} Errores/Advertencias (Click para ver)")
            else:
                self.lbl_errors_badge.configure(text="")
                
        elif msg_type == 'error':
            self.progress_bar.stop()
            self.progress_label.configure(text=f"Error en escaneo: {details}")
            self.finalize_scan_ui()
            messagebox.showerror("Error de Escaneo", details)

    def start_scanning(self):
        """Inicia el proceso de deduplicación en un hilo separado."""
        if not self.scan_directories:
            messagebox.showwarning("Falta Información", "Por favor, seleccione al menos una carpeta para escanear.")
            return

        # Preparar filtros
        extensions = set()
        if self.checkbox_filter.get():
            ext_text = self.entry_extensions.get()
            extensions = {e.strip() for e in ext_text.split(',') if e.strip()}

        # Limpiar resultados anteriores
        self.clear_results_display()
        self.duplicates.clear()
        self.checkbox_vars.clear()
        
        # Bloquear botones de inicio
        self.btn_start.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.btn_export_csv.configure(state="disabled")
        self.btn_delete_selected.configure(state="disabled")
        self.lbl_errors_badge.configure(text="")

        # Configurar hilo
        def run():
            try:
                def progress_cb(stage, current, total, text):
                    self.scan_queue.put((stage, current, total, text))
                
                # Ejecutar
                res = self.scanner.scan(self.scan_directories, extensions, progress_cb)
                self.scanner.scan_result_dict = res  # Guardar temporalmente
            except Exception as e:
                self.scan_queue.put(('error', 0, 0, str(e)))

        self.scan_thread = threading.Thread(target=run, daemon=True)
        self.scan_thread.start()
        self.status_bar_info.configure(text="Escaneo iniciado...")

    def cancel_scanning(self):
        """Indica al escáner que se detenga."""
        if self.scanner:
            self.scanner.cancel()
            self.status_bar_info.configure(text="Cancelando escaneo...")
            self.btn_cancel.configure(state="disabled")

    def finalize_scan_ui(self):
        """Restaura los botones de la interfaz después del escaneo o cancelación."""
        self.btn_start.configure(state="normal")
        self.btn_cancel.configure(state="disabled")
        if self.duplicates:
            self.btn_export_csv.configure(state="normal")
            self.btn_delete_selected.configure(state="normal")
        self.status_bar_info.configure(text="Operación finalizada.")

    # =====================================================================
    # RENDERIZADO Y CONTROL DE RESULTADOS
    # =====================================================================
    def clear_results_display(self):
        """Elimina todos los widgets del panel scrollable de resultados."""
        for widget in self.results_scroll.winfo_children():
            widget.destroy()
        self.lbl_card_groups_val.configure(text="0")
        self.lbl_card_space_val.configure(text="0.00 B")
        self.lbl_card_space_val.configure(text_color="#2ecc71")

    def display_results(self):
        """Dibuja en pantalla las tarjetas con los grupos duplicados."""
        self.clear_results_display()
        
        if not self.duplicates:
            no_dup_label = ctk.CTkLabel(
                self.results_scroll, 
                text="No se encontraron archivos duplicados en la selección actual.",
                font=ctk.CTkFont(family="Segoe UI", size=13, slant="italic"),
                pady=40
            )
            no_dup_label.pack(expand=True, fill="both")
            return

        total_recoverable_space = 0
        group_idx = 1
        
        # Ordenar duplicados por tamaño descendente para priorizar espacio recuperable
        sorted_groups = sorted(self.duplicates.items(), key=lambda x: x[1][0][1], reverse=True)

        for hash_val, files in sorted_groups:
            # files es una lista de tuplas [(path, size), (path, size), ...]
            file_size = files[0][1]
            num_files = len(files)
            # El espacio recuperable de este grupo es (N-1) * tamaño
            group_recoverable = (num_files - 1) * file_size
            total_recoverable_space += group_recoverable

            # Crear tarjeta contenedora para este grupo
            group_card = ctk.CTkFrame(self.results_scroll, border_color="#3a3a3a", border_width=1)
            group_card.pack(fill="x", padx=5, pady=8, expand=True)

            # Encabezado del grupo
            header_frame = ctk.CTkFrame(group_card, fg_color="#1f538d", height=32, corner_radius=4)
            header_frame.pack(fill="x", padx=2, pady=2)
            
            lbl_title = ctk.CTkLabel(
                header_frame, 
                text=f"Grupo #{group_idx}   |   Tamaño: {format_size(file_size)}   |   Duplicados: {num_files}   |   Recuperable: {format_size(group_recoverable)}",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color="white"
            )
            lbl_title.pack(side="left", padx=10)

            # Botón "Seleccionar recomendados" (marcar todos menos uno para este grupo)
            btn_select_rec = ctk.CTkButton(
                header_frame,
                text="Marcar Copias",
                height=22,
                width=100,
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                fg_color="#34495e",
                hover_color="#2c3e50",
                command=lambda f_list=files: self.select_copies_only(f_list)
            )
            btn_select_rec.pack(side="right", padx=10, pady=5)

            # Lista de archivos del grupo
            files_frame = ctk.CTkFrame(group_card, fg_color="transparent")
            files_frame.pack(fill="x", padx=10, pady=5)

            for idx, (path, size) in enumerate(files):
                row_frame = ctk.CTkFrame(files_frame, fg_color="transparent")
                row_frame.pack(fill="x", pady=2)

                # Checkbox de selección
                var = tk.BooleanVar()
                self.checkbox_vars[path] = var
                
                chk = ctk.CTkCheckBox(
                    row_frame, 
                    text="", 
                    variable=var, 
                    width=20,
                    checkbox_width=18,
                    checkbox_height=18,
                    command=self.update_stats_live
                )
                chk.pack(side="left", padx=(0, 5))

                # Ruta del archivo
                lbl_path = ctk.CTkLabel(
                    row_frame, 
                    text=path, 
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    anchor="w",
                    justify="left"
                )
                lbl_path.pack(side="left", fill="x", expand=True, padx=5)

                # Botón abrir carpeta contenedora
                btn_open = ctk.CTkButton(
                    row_frame, 
                    text="📂", 
                    width=28, 
                    height=24,
                    fg_color="transparent",
                    text_color="#a0a0a0",
                    hover_color="#2b2b2b",
                    font=ctk.CTkFont(size=12),
                    command=lambda p=path: self.open_file_folder(p)
                )
                btn_open.pack(side="right", padx=5)

            group_idx += 1

        # Actualizar tarjetas superiores
        self.lbl_card_groups_val.configure(text=str(len(self.duplicates)))
        self.lbl_card_space_val.configure(text=format_size(total_recoverable_space))
        if total_recoverable_space > 0:
            self.lbl_card_space_val.configure(text_color="#2ecc71")  # Verde si hay espacio
        else:
            self.lbl_card_space_val.configure(text_color="#a0a0a0")

    def select_copies_only(self, files_list: List[Tuple[str, int]]):
        """Marca automáticamente para eliminación todas las copias menos la primera del grupo."""
        if not files_list:
            return
        # La primera ruta queda desmarcada (se conserva)
        first_path = files_list[0][0]
        if first_path in self.checkbox_vars:
            self.checkbox_vars[first_path].set(False)
            
        # El resto se marcan para eliminación (copias)
        for path, _ in files_list[1:]:
            if path in self.checkbox_vars:
                self.checkbox_vars[path].set(True)
                
        self.update_stats_live()

    def open_file_folder(self, filepath: str):
        """Abre la carpeta contenedora en el explorador de archivos de Windows."""
        try:
            folder = os.path.dirname(filepath)
            if os.path.exists(folder):
                os.startfile(folder)
            else:
                messagebox.showerror("Error", f"No se pudo encontrar el directorio:\n{folder}")
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al abrir carpeta: {str(e)}")

    def update_stats_live(self):
        """Calcula dinámicamente cuántos archivos seleccionó el usuario y el espacio a liberar."""
        selected_count = 0
        selected_bytes = 0

        # Mapear rutas rápidas de tamaño para sumar
        path_to_size = {}
        for hash_val, files in self.duplicates.items():
            for p, sz in files:
                path_to_size[p] = sz

        for filepath, var in self.checkbox_vars.items():
            if var.get():
                selected_count += 1
                selected_bytes += path_to_size.get(filepath, 0)

        # Actualizar etiqueta del botón de eliminación y barra de estado
        if selected_count > 0:
            self.btn_delete_selected.configure(
                text=f"Eliminar {selected_count} Archivos",
                fg_color="#d9534f"
            )
            self.status_bar_info.configure(
                text=f"Seleccionados: {selected_count} archivos | Espacio a recuperar de inmediato: {format_size(selected_bytes)}"
            )
        else:
            self.btn_delete_selected.configure(
                text="Eliminar Seleccionados",
                fg_color="#a94442"
            )
            self.status_bar_info.configure(text="Ningún archivo seleccionado para eliminación.")

    # =====================================================================
    # ELIMINACIÓN SEGURA Y EXPORTACIÓN A CSV
    # =====================================================================
    def confirm_and_delete(self):
        """Solicita confirmación e inicia el proceso de eliminación segura de los archivos marcados."""
        # 1. Obtener archivos seleccionados
        selected_files = [path for path, var in self.checkbox_vars.items() if var.get()]
        
        if not selected_files:
            messagebox.showinfo("Información", "Por favor, marque los archivos que desea eliminar usando los checkboxes del panel.")
            return

        # Calcular tamaño total a eliminar
        path_to_size = {}
        for hash_val, files in self.duplicates.items():
            for p, sz in files:
                path_to_size[p] = sz

        total_bytes = sum(path_to_size.get(p, 0) for p in selected_files)
        
        # 2. Mostrar diálogo de confirmación personalizado
        msg = f"¿Está seguro de que desea eliminar permanentemente {len(selected_files)} archivo(s)?\n\n" \
              f"Se liberará un espacio en disco de {format_size(total_bytes)}.\n\n" \
              f"⚠️ ATENCIÓN: Esta acción es irreversible y no pasará por la Papelera de Reciclaje."
        
        def execute_deletion():
            success_count = 0
            fail_count = 0
            failed_paths = []

            for path in selected_files:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        success_count += 1
                    else:
                        # El archivo ya no existe en el disco
                        fail_count += 1
                        failed_paths.append(f"{path} (El archivo no existe)")
                except Exception as e:
                    fail_count += 1
                    failed_paths.append(f"{path} (Error: {str(e)})")

            # 3. Refrescar dinámicamente el estado de duplicados sin re-escanear
            self.clean_deleted_files_from_results(selected_files)
            self.display_results()
            self.update_stats_live()

            # 4. Notificar resultados
            result_msg = f"Se eliminaron exitosamente {success_count} archivos."
            if fail_count > 0:
                result_msg += f"\n\nFallo al eliminar {fail_count} archivos:"
                # Mostrar los primeros 3 errores en el cuadro de diálogo
                for fp in failed_paths[:3]:
                    result_msg += f"\n- {fp}"
                if len(failed_paths) > 3:
                    result_msg += f"\n- Y {len(failed_paths) - 3} más..."
                messagebox.showwarning("Eliminación Parcial", result_msg)
            else:
                messagebox.showinfo("Eliminación Completada", result_msg)

        CustomConfirmDialog(self, "Confirmar Eliminación Segura", msg, execute_deletion)

    def clean_deleted_files_from_results(self, deleted_paths: List[str]):
        """Elimina las rutas borradas de la estructura interna de datos para refrescar la UI sin escanear."""
        deleted_set = set(deleted_paths)
        updated_duplicates = {}

        for hash_val, files in self.duplicates.items():
            # Filtrar archivos que no fueron eliminados
            remaining_files = [(path, size) for path, size in files if path not in deleted_set]
            
            # Si queda más de un archivo en el grupo, sigue siendo un duplicado
            if len(remaining_files) > 1:
                updated_duplicates[hash_val] = remaining_files
                
        self.duplicates = updated_duplicates
        self.scanner.scan_result_dict = updated_duplicates

    def export_csv(self):
        """Exporta los resultados actuales de duplicados a un archivo CSV estructurado."""
        if not self.duplicates:
            messagebox.showinfo("Exportar Reporte", "No hay resultados para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Guardar Reporte CSV",
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv")],
            initialfile=f"duplicados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if not file_path:
            return

        try:
            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Encabezados
                writer.writerow(["ID_Grupo", "Hash_Completo_SHA256", "Nombre_Archivo", "Ruta_Completa", "Tamaño_Bytes", "Tamaño_Formateado"])
                
                group_id = 1
                for hash_val, files in self.duplicates.items():
                    for path, size in files:
                        filename = os.path.basename(path)
                        writer.writerow([
                            group_id,
                            hash_val,
                            filename,
                            path,
                            size,
                            format_size(size)
                        ])
                    group_id += 1
            
            messagebox.showinfo("Reporte Exportado", f"El reporte ha sido exportado exitosamente a:\n{file_path}")
            self.status_bar_info.configure(text=f"Reporte exportado: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error de Exportación", f"No se pudo guardar el archivo CSV:\n{str(e)}")


if __name__ == "__main__":
    # Asegurar soporte de alta densidad (DPI) en Windows para fuentes nítidas
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = DuplicateDetectorApp()
    app.mainloop()


"""
AVISO DE DERECHOS DE AUTOR Y DESCARGO DE RESPONSABILIDAD (COPYRIGHT DISCLAIMER)

Este software y su código fuente son propiedad del autor. Se otorgan derechos 
exclusivamente para fines de evaluación académica, revisión y calificación 
como parte del proyecto final del curso.

Queda estrictamente prohibida la reproducción, distribución, modificación 
o uso comercial de este código, total o parcial, sin la autorización 
expresa y por escrito del titular de los derechos de autor.

Este proyecto puede contener fragmentos de código, librerías de código abierto 
o recursos de terceros con fines educativos, los cuales están protegidos por 
sus respectivas licencias y se utilizan bajo la doctrina de uso legítimo.

EL SOFTWARE SE PROPORCIONA "TAL CUAL", SIN GARANTÍA DE NINGÚN TIPO, EXPRESA 
O IMPLÍCITA. EL AUTOR NO SE HACE RESPONSABLE DE NINGUNA RECLAMACIÓN, DAÑO 
U OTRA RESPONSABILIDAD QUE SURJA DEL USO DE ESTE SOFTWARE.

© 2026 [Dilan Alejandro González Alatriste]. Todos los derechos reservados.
"""
