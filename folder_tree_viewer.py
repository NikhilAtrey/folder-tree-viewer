import os
import sys
import json
import threading
import ctypes
import platform
import tempfile
import webbrowser
import re
from datetime import datetime
from functools import partial

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Try importing drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


class FolderScanner:
    """Handles folder scanning and tree generation"""
    
    def __init__(self, callback=None, status_callback=None):
        self.callback = callback
        self.status_callback = status_callback
        self.stop_event = threading.Event()
        self.current_thread = None
        
    def scan_folder(self, folder_path, include_files=True, max_depth=None, 
                   show_size=False, size_format="auto"):
        """Start scanning folder in a separate thread"""
        self.stop_event.clear()
        
        if self.current_thread and self.current_thread.is_alive():
            self.stop_event.set()
            self.current_thread.join()
            
        self.current_thread = threading.Thread(
            target=self._scan_folder_thread,
            args=(folder_path, include_files, max_depth, show_size, size_format)
        )
        self.current_thread.daemon = True
        self.current_thread.start()
        
    def _scan_folder_thread(self, folder_path, include_files, max_depth, show_size, size_format):
        """Thread function to scan folder and generate tree"""
        try:
            if self.status_callback:
                self.status_callback("Scanning folder structure...")
            
            result = []
            self._scan_directory(folder_path, result, "", include_files, 0, max_depth, show_size, size_format)
            
            if self.stop_event.is_set():
                if self.status_callback:
                    self.status_callback("Scan cancelled")
                return
                
            tree_text = "\n".join(result)
            
            if self.callback:
                self.callback(tree_text)
                
            if self.status_callback:
                self.status_callback(f"Scan complete. Found {len(result)} items.")
                
        except Exception as e:
            if self.status_callback:
                self.status_callback(f"Error: {str(e)}")
    
    def _scan_directory(self, path, result, prefix, include_files, current_depth, max_depth, show_size, size_format):
        """Recursively scan directory and build tree structure"""
        if self.stop_event.is_set():
            return
            
        if max_depth is not None and current_depth > max_depth:
            return
            
        try:
            items = os.listdir(path)
        except PermissionError:
            result.append(f"{prefix}├── [Access Denied]")
            return
        except Exception as e:
            result.append(f"{prefix}├── [Error: {str(e)}]")
            return
            
        # Sort items: directories first, then files
        dirs = []
        files = []
        
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            elif include_files:
                files.append(item)
                
        dirs.sort()
        files.sort()
        
        # Process directories
        for i, dir_name in enumerate(dirs):
            if self.stop_event.is_set():
                return
                
            is_last_dir = (i == len(dirs) - 1 and len(files) == 0)
            dir_path = os.path.join(path, dir_name)
            
            # Add size information if requested
            size_str = ""
            if show_size:
                try:
                    dir_size = self._get_dir_size(dir_path)
                    size_str = f" [{self._format_size(dir_size, size_format)}]"
                except:
                    size_str = " [size error]"
            
            if is_last_dir:
                result.append(f"{prefix}└── {dir_name}/{size_str}")
                new_prefix = prefix + "    "
            else:
                result.append(f"{prefix}├── {dir_name}/{size_str}")
                new_prefix = prefix + "│   "
                
            self._scan_directory(dir_path, result, new_prefix, include_files, 
                               current_depth + 1, max_depth, show_size, size_format)
        
        # Process files
        if include_files:
            for i, file_name in enumerate(files):
                if self.stop_event.is_set():
                    return
                    
                is_last = (i == len(files) - 1)
                
                # Add size information if requested
                size_str = ""
                if show_size:
                    try:
                        file_path = os.path.join(path, file_name)
                        file_size = os.path.getsize(file_path)
                        size_str = f" [{self._format_size(file_size, size_format)}]"
                    except:
                        size_str = " [size error]"
                
                if is_last:
                    result.append(f"{prefix}└── {file_name}{size_str}")
                else:
                    result.append(f"{prefix}├── {file_name}{size_str}")
    
    def _get_dir_size(self, path):
        """Calculate directory size recursively"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
                except:
                    pass
        return total_size
    
    def _format_size(self, size_bytes, format_type):
        """Format size in bytes to human-readable format"""
        if format_type == "bytes":
            return f"{size_bytes} B"
            
        if size_bytes == 0:
            return "0 B"
            
        size_names = ["B", "KB", "MB", "GB", "TB"]
        
        if format_type == "auto":
            i = 0
            while size_bytes >= 1024 and i < len(size_names) - 1:
                size_bytes /= 1024
                i += 1
            return f"{size_bytes:.2f} {size_names[i]}"
        else:
            # Use the specified format
            index = size_names.index(format_type)
            for _ in range(index):
                size_bytes /= 1024
            return f"{size_bytes:.2f} {format_type}"
    
    def stop_scan(self):
        """Stop the current scan operation"""
        if self.current_thread and self.current_thread.is_alive():
            self.stop_event.set()
            return True
        return False


class FolderTreeViewer:
    """Main application class for the Folder Tree Viewer"""
    
    def __init__(self, root):
        try:
            self.root = root
            self.root.title("Folder Tree Viewer")
            self.root.geometry("900x700")
            self.root.minsize(600, 400)
            
            # Set application icon
            try:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
                if os.path.exists(icon_path):
                    # For Windows
                    if platform.system() == "Windows":
                        self.root.iconbitmap(default=icon_path)
                    # For Linux/Unix
                    else:
                        img = tk.PhotoImage(file=icon_path)
                        self.root.tk.call('wm', 'iconphoto', self.root._w, img)
                    print(f"Icon loaded successfully from: {icon_path}")
                else:
                    print(f"Icon file not found at: {icon_path}")
            except Exception as e:
                print(f"Error loading icon: {str(e)}")
            
            # Initialize favorite folders
            self.favorite_folders = []
            self.recent_folders = []
            self.max_recent_folders = 10
            
            # Configuration
            self.config = {
                "include_files": True,
                "max_depth": None,
                "show_size": False,
                "size_format": "auto",
                "last_directory": os.path.expanduser("~"),
                "favorite_folders": [],
                "recent_folders": [],
                "default_depth": "",
                "default_export_location": os.path.expanduser("~"),
                "language": "en",
                "check_updates_on_startup": False
            }
            
            # Load config if exists
            self.load_config()
            
            # Initialize language system
            self.translations = {
                "en": {
                    "file": "File",
                    "edit": "Edit",
                    "view": "View",
                    "help": "Help",
                    "settings": "Settings",
                    "about": "About",
                    "general": "General",
                    "export": "Export",
                    "language": "Language",
                    "updates": "Updates",
                    "default_depth": "Default Depth",
                    "export_location": "Export Location",
                    "interface_language": "Interface Language",
                    "check_updates": "Check for Updates",
                    "check_updates_startup": "Check for updates on startup",
                    "check_updates_now": "Check for Updates Now",
                    "save": "Save",
                    "cancel": "Cancel",
                    "browse": "Browse",
                    "english": "English",
                    "spanish": "Spanish",
                    "french": "French",
                    "german": "German",
                    "restart_required": "Please restart the application for language changes to take effect.",
                    "settings_saved": "Settings saved successfully.",
                    "error_saving": "Error saving settings: {}"
                },
                "es": {
                    "file": "Archivo",
                    "edit": "Editar",
                    "view": "Ver",
                    "help": "Ayuda",
                    "settings": "Configuración",
                    "about": "Acerca de",
                    "general": "General",
                    "export": "Exportar",
                    "language": "Idioma",
                    "updates": "Actualizaciones",
                    "default_depth": "Profundidad Predeterminada",
                    "export_location": "Ubicación de Exportación",
                    "interface_language": "Idioma de la Interfaz",
                    "check_updates": "Buscar Actualizaciones",
                    "check_updates_startup": "Buscar actualizaciones al iniciar",
                    "check_updates_now": "Buscar Actualizaciones Ahora",
                    "save": "Guardar",
                    "cancel": "Cancelar",
                    "browse": "Examinar",
                    "english": "Inglés",
                    "spanish": "Español",
                    "french": "Francés",
                    "german": "Alemán",
                    "restart_required": "Por favor, reinicie la aplicación para que los cambios de idioma surtan efecto.",
                    "settings_saved": "Configuración guardada exitosamente.",
                    "error_saving": "Error al guardar la configuración: {}"
                },
                "fr": {
                    "file": "Fichier",
                    "edit": "Éditer",
                    "view": "Affichage",
                    "help": "Aide",
                    "settings": "Paramètres",
                    "about": "À propos",
                    "general": "Général",
                    "export": "Exporter",
                    "language": "Langue",
                    "updates": "Mises à jour",
                    "default_depth": "Profondeur par défaut",
                    "export_location": "Emplacement d'exportation",
                    "interface_language": "Langue de l'interface",
                    "check_updates": "Vérifier les mises à jour",
                    "check_updates_startup": "Vérifier les mises à jour au démarrage",
                    "check_updates_now": "Vérifier les mises à jour maintenant",
                    "save": "Enregistrer",
                    "cancel": "Annuler",
                    "browse": "Parcourir",
                    "english": "Anglais",
                    "spanish": "Espagnol",
                    "french": "Français",
                    "german": "Allemand",
                    "restart_required": "Veuillez redémarrer l'application pour que les changements de langue prennent effet.",
                    "settings_saved": "Paramètres enregistrés avec succès.",
                    "error_saving": "Erreur lors de l'enregistrement des paramètres: {}"
                },
                "de": {
                    "file": "Datei",
                    "edit": "Bearbeiten",
                    "view": "Ansicht",
                    "help": "Hilfe",
                    "settings": "Einstellungen",
                    "about": "Über",
                    "general": "Allgemein",
                    "export": "Exportieren",
                    "language": "Sprache",
                    "updates": "Aktualisierungen",
                    "default_depth": "Standardtiefe",
                    "export_location": "Exportort",
                    "interface_language": "Oberflächensprache",
                    "check_updates": "Nach Updates suchen",
                    "check_updates_startup": "Beim Start nach Updates suchen",
                    "check_updates_now": "Jetzt nach Updates suchen",
                    "save": "Speichern",
                    "cancel": "Abbrechen",
                    "browse": "Durchsuchen",
                    "english": "Englisch",
                    "spanish": "Spanisch",
                    "french": "Französisch",
                    "german": "Deutsch",
                    "restart_required": "Bitte starten Sie die Anwendung neu, damit die Sprachänderungen wirksam werden.",
                    "settings_saved": "Einstellungen erfolgreich gespeichert.",
                    "error_saving": "Fehler beim Speichern der Einstellungen: {}"
                }
            }
            
            # Initialize folder scanner
            self.folder_scanner = FolderScanner(
                callback=self.update_tree_display,
                status_callback=self.update_status
            )
            
            # Create UI elements
            self.create_menu()
            self.create_ui()
            
            # Enable drag and drop
            self.setup_drag_drop()
            
            # Update checkboxes based on config
            self.include_files_var.set(self.config["include_files"])
            self.show_size_var.set(self.config["show_size"])
            
            # Set max depth if configured
            if self.config["max_depth"] is not None:
                self.max_depth_var.set(str(self.config["max_depth"]))
                
            # Load favorite and recent folders
            self.favorite_folders = self.config.get("favorite_folders", [])
            self.recent_folders = self.config.get("recent_folders", [])
            
            # Update status
            self.update_status("Ready. Select a folder to begin.")
            
            # Check for updates on startup if enabled
            if self.config.get("check_updates_on_startup", False):
                self.root.after(2000, self.check_updates)
                
        except Exception as e:
            messagebox.showerror("Initialization Error", f"Failed to initialize application: {str(e)}")
            raise
    
    def create_menu(self):
        """Create application menu"""
        self.menu_bar = tk.Menu(self.root)
        
        # File menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(label="Open Folder", command=self.browse_folder, accelerator="Ctrl+O")
        
        # Add Favorites submenu
        self.favorites_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Favorites", menu=self.favorites_menu)
        self.update_favorites_menu()
        
        # Add Recent submenu
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent", menu=self.recent_menu)
        self.update_recent_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Export as Text", command=lambda: self.export_tree("txt"), accelerator="Ctrl+E")
        file_menu.add_command(label="Export as JSON", command=lambda: self.export_tree("json"), accelerator="Ctrl+Shift+E")
        file_menu.add_command(label="Export as CSV", command=lambda: self.export_tree("csv"), accelerator="Ctrl+Shift+C")
        file_menu.add_separator()
        file_menu.add_command(label="Settings", command=self.show_settings_dialog, accelerator="Ctrl+,")
        file_menu.add_separator()
        file_menu.add_command(label="Reset Application", command=self.reset_application, accelerator="Ctrl+R")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Edit menu
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        edit_menu.add_command(label="Copy to Clipboard", command=self.copy_to_clipboard, accelerator="Ctrl+C")
        edit_menu.add_separator()
        edit_menu.add_command(label="Select All", command=self.select_all, accelerator="Ctrl+A")
        
        # View menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        view_menu.add_command(label="Refresh", command=self.refresh_tree, accelerator="F5")
        
        # Help menu
        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Check for Updates", command=self.check_updates)
        
        # Add menus to menu bar
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=self.menu_bar)
        
        # Bind keyboard shortcuts
        self.root.bind("<Control-o>", lambda event: self.browse_folder())
        self.root.bind("<Control-c>", lambda event: self.copy_to_clipboard())
        self.root.bind("<Control-a>", lambda event: self.select_all())
        self.root.bind("<F5>", lambda event: self.refresh_tree())
        self.root.bind("<Control-e>", lambda event: self.export_tree("txt"))
        self.root.bind("<Control-E>", lambda event: self.export_tree("json"))
        self.root.bind("<Control-comma>", lambda event: self.show_settings_dialog())
        self.root.bind("<Control-r>", lambda event: self.reset_application())
    
    def create_ui(self):
        """Create the main UI elements"""
        # Main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top frame for controls
        self.top_frame = ttk.Frame(self.main_frame)
        self.top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Folder selection
        self.folder_frame = ttk.Frame(self.top_frame)
        self.folder_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.folder_frame, text="Folder:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.folder_var = tk.StringVar()
        self.folder_entry = ttk.Entry(self.folder_frame, textvariable=self.folder_var)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.browse_button = ttk.Button(self.folder_frame, text="Browse", command=self.browse_folder)
        self.browse_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.scan_button = ttk.Button(self.folder_frame, text="Scan", command=self.scan_folder)
        self.scan_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.reset_button = ttk.Button(self.folder_frame, text="Reset", command=self.reset_application)
        self.reset_button.pack(side=tk.LEFT)
        
        # Options frame
        self.options_frame = ttk.Frame(self.top_frame)
        self.options_frame.pack(fill=tk.X, pady=5)
        
        # Left options
        self.left_options = ttk.Frame(self.options_frame)
        self.left_options.pack(side=tk.LEFT)
        
        self.include_files_var = tk.BooleanVar(value=True)
        self.include_files_check = ttk.Checkbutton(
            self.left_options, 
            text="Include Files", 
            variable=self.include_files_var,
            command=self.refresh_tree
        )
        self.include_files_check.pack(side=tk.LEFT, padx=(0, 10))
        
        self.show_size_var = tk.BooleanVar(value=False)
        self.show_size_check = ttk.Checkbutton(
            self.left_options, 
            text="Show Size", 
            variable=self.show_size_var,
            command=self.refresh_tree
        )
        self.show_size_check.pack(side=tk.LEFT, padx=(0, 10))
        
        # Right options
        self.right_options = ttk.Frame(self.options_frame)
        self.right_options.pack(side=tk.RIGHT)
        
        # Create a frame for max depth with better layout
        max_depth_frame = ttk.LabelFrame(self.right_options, text="Max Depth")
        max_depth_frame.pack(side=tk.LEFT, padx=(0, 5))
        
        # Create a frame for the max depth entry and help button
        entry_frame = ttk.Frame(max_depth_frame)
        entry_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.max_depth_var = tk.StringVar(value="")
        self.max_depth_entry = ttk.Entry(entry_frame, textvariable=self.max_depth_var, width=5)
        self.max_depth_entry.pack(side=tk.LEFT)
        
        # Add a help button for max depth
        self.max_depth_help = ttk.Button(
            entry_frame, 
            text="?", 
            width=2,
            command=self.show_max_depth_help
        )
        self.max_depth_help.pack(side=tk.LEFT, padx=(2, 0))
        
        # Add a label for better explanation
        ttk.Label(max_depth_frame, text="(0-20, empty = unlimited)").pack(side=tk.LEFT, padx=5)
        
        # Bind validation to max depth entry
        self.max_depth_entry.bind('<KeyRelease>', self.validate_max_depth)
        self.max_depth_entry.bind('<FocusOut>', self.validate_max_depth)
        
        # Separator
        ttk.Separator(self.main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Tree display
        self.tree_frame = ttk.Frame(self.main_frame)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a frame for the text area with custom styling
        self.text_container = ttk.Frame(self.tree_frame)
        self.text_container.pack(fill=tk.BOTH, expand=True)
        
        # Create the text area with custom font
        self.tree_display = ScrolledText(
            self.text_container,
            wrap=tk.NONE,
            font=("Consolas", 10),
            padx=10,
            pady=10
        )
        self.tree_display.pack(fill=tk.BOTH, expand=True)
        
        # Create drag and drop message overlay
        self.drag_drop_frame = ttk.Frame(self.tree_frame, style="DragDrop.TFrame")
        self.drag_drop_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Create a style for the drag drop frame
        style = ttk.Style()
        style.configure("DragDrop.TFrame", background="#f0f0f0")
        
        # Add folder icon (emoji)
        self.folder_icon_label = ttk.Label(
            self.drag_drop_frame, 
            text="📁", 
            font=("Arial", 48),
            background="#f0f0f0"
        )
        self.folder_icon_label.pack(pady=(0, 10))
        
        # Add text message
        self.drag_drop_label = ttk.Label(
            self.drag_drop_frame, 
            text="Drop your folder here to begin", 
            font=("Arial", 14),
            background="#f0f0f0"
        )
        self.drag_drop_label.pack(pady=(0, 5))
        
        # Add hint text
        self.drag_drop_hint = ttk.Label(
            self.drag_drop_frame, 
            text="or use the Browse button above", 
            font=("Arial", 10),
            background="#f0f0f0",
            foreground="#666666"
        )
        self.drag_drop_hint.pack()
        
        # Button frame
        self.button_frame = ttk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Left buttons
        self.left_buttons = ttk.Frame(self.button_frame)
        self.left_buttons.pack(side=tk.LEFT)
        
        self.copy_button = ttk.Button(
            self.left_buttons, 
            text="Copy to Clipboard", 
            command=self.copy_to_clipboard
        )
        self.copy_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.export_button = ttk.Button(
            self.left_buttons, 
            text="Export", 
            command=self.show_export_menu
        )
        self.export_button.pack(side=tk.LEFT)
        
        # Status bar
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.status_bar = ttk.Label(
            self.status_frame, 
            text="Ready", 
            anchor=tk.W, 
            padding=(10, 5)
        )
        self.status_bar.pack(fill=tk.X, side=tk.LEFT, expand=True)
        
        # Progress bar (initially hidden)
        self.progress = ttk.Progressbar(
            self.status_frame, 
            mode="indeterminate", 
            length=100
        )
        
        # Version label
        self.version_label = ttk.Label(
            self.status_frame, 
            text="v1.0.0", 
            anchor=tk.E, 
            padding=(10, 5)
        )
        self.version_label.pack(side=tk.RIGHT)
        
        # Show the drag and drop message initially
        self.show_drag_drop_message()
    
    def show_drag_drop_message(self):
        """Show the drag and drop message"""
        self.drag_drop_frame.lift()
        self.drag_drop_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
    def hide_drag_drop_message(self):
        """Hide the drag and drop message"""
        self.drag_drop_frame.place_forget()
    
    def reset_application(self):
        """Reset the application by clearing results and path"""
        if messagebox.askyesno("Reset Application", "Are you sure you want to reset the application? This will clear the current results and path."):
            self.update_status("Resetting application...")
            
            # Clear the folder path
            self.folder_var.set("")
            
            # Clear the tree display
            self.tree_display.delete(1.0, tk.END)
            
            # Show the drag and drop message
            self.show_drag_drop_message()
            
            # Reset options to defaults
            self.include_files_var.set(True)
            self.show_size_var.set(False)
            self.max_depth_var.set("")
            
            # Update config
            self.config["include_files"] = True
            self.config["max_depth"] = None
            self.config["show_size"] = False
            self.save_config()
            
            # Update status
            self.update_status("Application reset. Select a folder to begin.")
    
    def setup_drag_drop(self):
        """Setup drag and drop functionality for the tree view"""
        if not DND_AVAILABLE:
            self.update_status("Drag and drop support not available. Install tkinterdnd2 package.")
            return
            
        try:
            # Make only the main window a drop target
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self._on_drop)
            
            # Enable drag and drop for the tree display
            self.tree_display.drop_target_register(DND_FILES)
            self.tree_display.dnd_bind('<<Drop>>', self._on_drop)
            
            # Enable drag and drop for the folder entry
            self.folder_entry.drop_target_register(DND_FILES)
            self.folder_entry.dnd_bind('<<Drop>>', self._on_drop)
            
            self.update_status("Drag and drop enabled. Drop folders or files to scan.")
            print("Drag and drop setup completed successfully")
        except Exception as e:
            self.update_status(f"Error setting up drag and drop: {str(e)}")
            print(f"Drag and drop setup error: {str(e)}")
        
    def _on_drop(self, event):
        """Handle dropped files"""
        try:
            print(f"Drop event received: {event.data}")
            # Get the dropped data
            data = event.data
            
            # Handle Windows file paths (they come with curly braces)
            if data.startswith('{') and data.endswith('}'):
                data = data[1:-1]
            
            # Convert to proper path
            file_path = os.path.normpath(data)
            print(f"Processing path: {file_path}")
            
            if os.path.exists(file_path):
                if os.path.isdir(file_path):
                    print(f"Directory found: {file_path}")
                    self.folder_var.set(file_path)
                    self.scan_folder()
                else:
                    # If it's a file, use its parent directory
                    parent_dir = os.path.dirname(file_path)
                    print(f"File found, using parent directory: {parent_dir}")
                    self.folder_var.set(parent_dir)
                    self.scan_folder()
            else:
                print(f"Path does not exist: {file_path}")
                self.update_status("Invalid path dropped")
        except Exception as e:
            error_msg = f"Error handling drop: {str(e)}"
            print(error_msg)
            self.update_status(error_msg)
    
    def browse_folder(self):
        """Open folder browser dialog"""
        folder_path = filedialog.askdirectory(
            initialdir=self.config["last_directory"],
            title="Select Folder"
        )
        
        if folder_path:
            self.folder_var.set(folder_path)
            self.config["last_directory"] = folder_path
            self.scan_folder()
    
    def scan_folder(self):
        """Start folder scanning process"""
        try:
            folder_path = self.folder_var.get().strip()
            
            if not folder_path:
                self.update_status("Please select a folder first.")
                return
                
            if not os.path.exists(folder_path):
                self.update_status("Invalid folder path.")
                messagebox.showerror("Error", "The selected folder does not exist.")
                return
                
            if not os.path.isdir(folder_path):
                self.update_status("Invalid folder path.")
                messagebox.showerror("Error", "The selected path is not a folder.")
                return
                
            try:
                # Test folder access
                os.listdir(folder_path)
            except PermissionError:
                self.update_status("Access denied.")
                messagebox.showerror("Error", "You don't have permission to access this folder.")
                return
            except Exception as e:
                self.update_status("Error accessing folder.")
                messagebox.showerror("Error", f"Failed to access folder: {str(e)}")
                return
                
            # Hide the drag and drop message
            self.hide_drag_drop_message()
                
            # Get options
            include_files = self.include_files_var.get()
            show_size = self.show_size_var.get()
            
            # Parse and validate max depth
            max_depth = None
            max_depth_str = self.max_depth_var.get().strip()
            
            if max_depth_str:
                try:
                    max_depth = int(max_depth_str)
                    if max_depth < 0:
                        self.update_status("Max depth cannot be negative. Using unlimited depth.")
                        max_depth = None
                    elif max_depth == 0:
                        self.update_status("Scanning current folder only (depth 0)")
                    elif max_depth > 20:
                        if not messagebox.askyesno("Large Depth", 
                            f"Scanning with a depth of {max_depth} may take a long time and use significant memory.\n\n"
                            f"This will scan:\n"
                            f"• The selected folder\n"
                            f"• {max_depth} levels of subfolders\n"
                            f"• All files in these folders\n\n"
                            "Do you want to continue?"):
                            return
                        self.update_status(f"Scanning with max depth: {max_depth}")
                    else:
                        self.update_status(f"Scanning with max depth: {max_depth}")
                except ValueError:
                    self.update_status("Invalid max depth value. Using unlimited depth.")
                    max_depth = None
            else:
                self.update_status("Scanning with unlimited depth")
            
            # Update config
            self.config["include_files"] = include_files
            self.config["max_depth"] = max_depth
            self.config["show_size"] = show_size
            self.save_config()
            
            # Add to recent folders
            self.add_to_recent_folders(folder_path)
            
            # Clear display
            self.tree_display.delete(1.0, tk.END)
            
            # Start progress bar
            self.progress.pack(side=tk.LEFT, padx=(0, 10))
            self.progress.start(10)
            
            # Start scanning
            self.folder_scanner.scan_folder(
                folder_path, 
                include_files=include_files,
                max_depth=max_depth,
                show_size=show_size,
                size_format=self.config["size_format"]
            )
            
        except Exception as e:
            self.update_status("Error during folder scan.")
            messagebox.showerror("Scan Error", f"An error occurred while scanning the folder: {str(e)}")
            self.progress.stop()
            self.progress.pack_forget()
    
    def update_tree_display(self, tree_text):
        """Update the tree display with scan results"""
        try:
            # Stop progress bar
            self.progress.stop()
            self.progress.pack_forget()
            
            # Update text display
            self.tree_display.delete(1.0, tk.END)
            
            # Add header
            header = f"Folder Tree: {self.folder_var.get()}\n"
            header += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            header += "-" * 80 + "\n\n"
            
            self.tree_display.insert(tk.END, header + tree_text)
            
            # Scroll to top
            self.tree_display.see("1.0")
            
        except Exception as e:
            self.update_status("Error updating tree display.")
            messagebox.showerror("Display Error", f"Failed to update tree display: {str(e)}")
    
    def update_status(self, message):
        """Update status bar message"""
        try:
            self.status_bar.config(text=message)
            self.root.update_idletasks()
        except Exception:
            pass  # Ignore status update errors to prevent crashes
    
    def copy_to_clipboard(self):
        """Copy tree content to clipboard"""
        try:
            text = self.tree_display.get(1.0, tk.END)
            if text.strip():
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.update_status("Tree copied to clipboard.")
            else:
                self.update_status("Nothing to copy.")
                messagebox.showinfo("Copy", "No folder tree data to copy.")
        except Exception as e:
            self.update_status("Error copying to clipboard.")
            messagebox.showerror("Copy Error", f"Failed to copy to clipboard: {str(e)}")
    
    def select_all(self):
        """Select all text in the display"""
        try:
            self.tree_display.tag_add(tk.SEL, "1.0", tk.END)
            self.tree_display.mark_set(tk.INSERT, "1.0")
            self.tree_display.see(tk.INSERT)
            return "break"  # Prevent default behavior
        except Exception:
            return "break"  # Prevent default behavior even if selection fails
    
    def refresh_tree(self):
        """Refresh the current tree view"""
        try:
            folder_path = self.folder_var.get().strip()
            
            if folder_path and os.path.isdir(folder_path):
                self.scan_folder()
            else:
                self.update_status("No folder selected to refresh.")
                messagebox.showinfo("Refresh", "No folder selected to refresh.")
        except Exception as e:
            self.update_status("Error refreshing tree.")
            messagebox.showerror("Refresh Error", f"Failed to refresh tree: {str(e)}")
    
    def show_export_menu(self):
        """Show export options menu"""
        try:
            export_menu = tk.Menu(self.root, tearoff=0)
            export_menu.add_command(label="Export as Text File", command=lambda: self.export_tree("txt"))
            export_menu.add_command(label="Export as JSON File", command=lambda: self.export_tree("json"))
            export_menu.add_command(label="Export as CSV File", command=lambda: self.export_tree("csv"))
            
            # Position the menu under the export button
            x = self.export_button.winfo_rootx()
            y = self.export_button.winfo_rooty() + self.export_button.winfo_height()
            export_menu.tk_popup(x, y)
        except Exception as e:
            messagebox.showerror("Menu Error", f"Failed to show export menu: {str(e)}")
    
    def export_tree(self, format_type):
        """Export tree to a file"""
        try:
            text = self.tree_display.get(1.0, tk.END)
            if not text.strip():
                self.update_status("Nothing to export.")
                messagebox.showinfo("Export", "No folder tree data to export.")
                return
                
            # Determine file type and extension
            if format_type == "txt":
                file_types = [("Text Files", "*.txt"), ("All Files", "*.*")]
                default_ext = ".txt"
                content = text
            elif format_type == "json":
                file_types = [("JSON Files", "*.json"), ("All Files", "*.*")]
                default_ext = ".json"
                
                try:
                    # Convert tree text to JSON structure
                    lines = text.split("\n")
                    tree_data = {
                        "folder": self.folder_var.get(),
                        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "structure": self._parse_tree_to_json(lines)
                    }
                    content = json.dumps(tree_data, indent=2)
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to convert tree to JSON: {str(e)}")
                    return
            elif format_type == "csv":
                file_types = [("CSV Files", "*.csv"), ("All Files", "*.*")]
                default_ext = ".csv"
                
                try:
                    # Convert tree text to CSV format
                    lines = text.split("\n")
                    csv_data = []
                    
                    # Add header
                    csv_data.append(["Type", "Name", "Path", "Size", "Modified"])
                    
                    # Process each line
                    current_path = []
                    for line in lines:
                        if not line.strip():
                            continue
                            
                        # Skip header lines
                        if line.startswith("Folder Tree:") or line.startswith("Generated:") or line.startswith("----"):
                            continue
                            
                        # Calculate depth and clean the line
                        depth = len(re.match(r'^(\s*)', line).group(1)) // 4
                        clean_line = line.strip()
                        
                        # Extract item information
                        if clean_line.startswith("├── ") or clean_line.startswith("└── "):
                            item_name = clean_line[4:]
                        else:
                            continue
                        
                        # Determine if it's a directory or file
                        is_dir = item_name.endswith("/")
                        if is_dir:
                            item_name = item_name[:-1]
                            current_path = current_path[:depth] + [item_name]
                        else:
                            current_path = current_path[:depth] + [item_name]
                        
                        # Extract size if present
                        size = ""
                        size_match = re.search(r'\[(.*?)\]$', item_name)
                        if size_match:
                            size = size_match.group(1)
                            item_name = item_name[:size_match.start()].strip()
                        
                        # Get full path
                        full_path = os.path.join(self.folder_var.get(), *current_path[:-1], item_name)
                        
                        # Get modification time if file exists
                        modified = ""
                        if os.path.exists(full_path):
                            try:
                                modified = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                        
                        # Add row to CSV data
                        csv_data.append([
                            "Directory" if is_dir else "File",
                            item_name,
                            os.path.dirname(full_path),
                            size,
                            modified
                        ])
                    
                    # Convert to CSV string
                    import csv
                    from io import StringIO
                    output = StringIO()
                    writer = csv.writer(output)
                    writer.writerows(csv_data)
                    content = output.getvalue()
                except Exception as e:
                    messagebox.showerror("Export Error", f"Failed to convert tree to CSV: {str(e)}")
                    return
            else:
                self.update_status(f"Unsupported export format: {format_type}")
                messagebox.showerror("Export Error", f"Unsupported export format: {format_type}")
                return
                
            # Ask for save location
            try:
                file_path = filedialog.asksaveasfilename(
                    defaultextension=default_ext,
                    filetypes=file_types,
                    initialdir=self.config["default_export_location"],
                    title=f"Export as {format_type.upper()}"
                )
                
                if not file_path:
                    return
                    
                # Ensure the directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Try to write the file
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                    
                self.update_status(f"Tree exported to {file_path}")
                
                # Update default export location
                self.config["default_export_location"] = os.path.dirname(file_path)
                self.save_config()
                
            except PermissionError:
                messagebox.showerror("Export Error", "Permission denied. Cannot write to the selected location.")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to export tree: {str(e)}")
                
        except Exception as e:
            self.update_status("Error during export.")
            messagebox.showerror("Export Error", f"An unexpected error occurred: {str(e)}")
    
    def _parse_tree_to_json(self, lines):
        """Parse tree text into JSON structure"""
        result = []
        stack = [(result, 0)]  # (current_list, depth)
        
        # Skip header lines
        start_line = 0
        for i, line in enumerate(lines):
            if line.startswith("----"):
                start_line = i + 2  # Skip the separator line and the blank line after it
                break
        
        for line in lines[start_line:]:
            if not line.strip():
                continue
                
            # Calculate depth based on indentation
            indent_match = re.match(r'^(\s*)', line)
            indent = len(indent_match.group(1)) if indent_match else 0
            
            # Extract item name and type
            clean_line = line.strip()
            
            if not clean_line:
                continue
                
            # Handle different line formats
            if clean_line.startswith("├── "):
                item_name = clean_line[4:]
            elif clean_line.startswith("└── "):
                item_name = clean_line[4:]
            elif clean_line.startswith("│   "):
                continue  # Skip connector lines
            else:
                item_name = clean_line
            
            # Determine if it's a directory or file
            is_dir = item_name.endswith("/")
            
            # Remove size information if present
            size_match = re.search(r'\s+\[.*\]$', item_name)
            if size_match:
                size_info = size_match.group(0)
                item_name = item_name[:-(len(size_info))]
            
            # Create item object
            item = {
                "name": item_name.rstrip("/"),
                "type": "directory" if is_dir else "file"
            }
            
            # Add to the appropriate level in the hierarchy
            while len(stack) > 1 and indent <= stack[-1][1]:
                stack.pop()
                
            current_list, _ = stack[-1]
            current_list.append(item)
            
            # If it's a directory, prepare for children
            if is_dir:
                item["children"] = []
                stack.append((item["children"], indent + 4))
        
        return result
    
    def show_about(self):
        """Show about dialog"""
        about = tk.Toplevel(self.root)
        about.title("About Folder Tree Viewer")
        about.geometry("500x400")
        about.transient(self.root)
        about.grab_set()
        
        # App icon
        icon_label = ttk.Label(about, text="📁", font=("Arial", 48))
        icon_label.pack(pady=(20, 0))
        
        # App name and version
        ttk.Label(about, text="Folder Tree Viewer", font=("Arial", 16, "bold")).pack(pady=(10, 0))
        ttk.Label(about, text="v1.0.0", font=("Arial", 10)).pack()
        
        # Description
        description = ttk.Label(about, text="""
A professional utility for visualizing folder structures.

Features:
• Responsive UI with threading
• Copy folder structure to clipboard
• Export to text or JSON
• Customizable view options
• Multi-language support
• Dark/Light theme
• Drag and drop support
""", justify=tk.CENTER)
        description.pack(pady=20)
        
        # Keyboard shortcuts
        ttk.Label(about, text="Keyboard Shortcuts", font=("Arial", 12, "bold")).pack(pady=(10, 5))
        shortcuts = ttk.Label(about, text="""
Ctrl+O: Open folder
Ctrl+E: Export as text
Ctrl+Shift+E: Export as JSON
Ctrl+C: Copy to clipboard
Ctrl+A: Select all
Ctrl+R: Reset application
Ctrl+,: Open settings
F5: Refresh
""", justify=tk.LEFT)
        shortcuts.pack()
        
        # Copyright
        ttk.Label(about, text="© 2024 Folder Tree Viewer", font=("Arial", 8)).pack(pady=(20, 0))
        
        # GitHub link
        github_frame = ttk.Frame(about)
        github_frame.pack(pady=10)
        ttk.Label(github_frame, text="Visit us on").pack(side=tk.LEFT)
        github_link = ttk.Label(github_frame, text="GitHub", foreground="blue", cursor="hand2")
        github_link.pack(side=tk.LEFT, padx=(5, 0))
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/yourusername/folder-tree-viewer"))
        
        # Close button
        ttk.Button(about, text="Close", command=about.destroy).pack(pady=10)
    
    def check_updates(self):
        """Check for updates on GitHub releases"""
        try:
            self.update_status("Checking for updates...")
            
            # Open GitHub releases page
            webbrowser.open("https://github.com/yourusername/folder-tree-viewer/releases")
            
            self.update_status("Opened GitHub releases page in your browser.")
        except Exception as e:
            self.update_status("Error checking for updates.")
            messagebox.showerror("Update Check Failed", 
                               "Could not check for updates. Please visit our GitHub page manually.")
    
    def load_config(self):
        """Load configuration from file"""
        try:
            config_path = self._get_config_path()
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        loaded_config = json.load(f)
                        self.config.update(loaded_config)
                except json.JSONDecodeError:
                    messagebox.showwarning("Config Error", "Configuration file is corrupted. Using default settings.")
                except Exception as e:
                    messagebox.showwarning("Config Error", f"Error loading configuration: {str(e)}")
        except Exception as e:
            messagebox.showwarning("Config Error", f"Failed to load configuration: {str(e)}")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config_path = self._get_config_path()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            messagebox.showwarning("Config Error", f"Failed to save configuration: {str(e)}")
    
    def _get_config_path(self):
        """Get the path to the configuration file"""
        if platform.system() == "Windows":
            app_data = os.environ.get("APPDATA", "")
            base_dir = os.path.join(app_data, "FolderTreeViewer")
        else:
            home = os.path.expanduser("~")
            base_dir = os.path.join(home, ".config", "FolderTreeViewer")
            
        return os.path.join(base_dir, "config.json")
    
    def show_max_depth_help(self):
        """Show help information about the max depth option"""
        help_text = """Max Depth Option:

• Controls how deep the folder scanner will go
• Empty = Unlimited depth (scans all subfolders)
• 0 = Current folder only
• 1 = Current folder + immediate subfolders
• 2-5 = Recommended for quick scans
• 6-10 = For detailed folder structures
• 11-20 = For very large folder structures
• Values above 20 are not allowed

Tips:
• Start with empty (unlimited) to see full structure
• Use lower values (1-3) for quick overviews
• Higher values may take longer to scan
• Consider folder size when choosing depth"""
        
        messagebox.showinfo("Max Depth Help", help_text)
    
    def validate_max_depth(self, event=None):
        """Validate and format max depth input"""
        try:
            value = self.max_depth_var.get().strip()
            
            # Allow empty value for unlimited depth
            if not value:
                self.max_depth_entry.configure(style='')
                return
                
            # Try to convert to integer
            depth = int(value)
            
            # Validate range
            if depth < 0:
                self.max_depth_var.set("0")
                self.max_depth_entry.configure(style='Error.TEntry')
                self.update_status("Max depth cannot be negative. Set to 0.")
            elif depth > 20:
                self.max_depth_var.set("20")
                self.max_depth_entry.configure(style='Error.TEntry')
                self.update_status("Max depth cannot exceed 20. Set to 20.")
            else:
                self.max_depth_entry.configure(style='')
                self.update_status(f"Max depth set to {depth}")
                
        except ValueError:
            # Clear invalid input
            self.max_depth_var.set("")
            self.max_depth_entry.configure(style='Error.TEntry')
            self.update_status("Invalid max depth value. Using unlimited depth.")
    
    def update_favorites_menu(self):
        """Update the favorites menu with current favorite folders"""
        self.favorites_menu.delete(0, tk.END)
        
        if not self.favorite_folders:
            self.favorites_menu.add_command(label="No favorites", state="disabled")
        else:
            for folder in self.favorite_folders:
                # Get folder name for display
                folder_name = os.path.basename(folder) or folder
                self.favorites_menu.add_command(
                    label=folder_name,
                    command=lambda f=folder: self.open_favorite_folder(f)
                )
                
        self.favorites_menu.add_separator()
        self.favorites_menu.add_command(
            label="Add Current to Favorites",
            command=self.add_current_to_favorites
        )
        self.favorites_menu.add_command(
            label="Manage Favorites",
            command=self.manage_favorites
        )
        
    def update_recent_menu(self):
        """Update the recent menu with recently opened folders"""
        self.recent_menu.delete(0, tk.END)
        
        if not self.recent_folders:
            self.recent_menu.add_command(label="No recent folders", state="disabled")
        else:
            for folder in self.recent_folders:
                # Get folder name for display
                folder_name = os.path.basename(folder) or folder
                self.recent_menu.add_command(
                    label=folder_name,
                    command=lambda f=folder: self.open_recent_folder(f)
                )
                
        self.recent_menu.add_separator()
        self.recent_menu.add_command(
            label="Clear Recent",
            command=self.clear_recent_folders
        )
        
    def add_current_to_favorites(self):
        """Add the current folder to favorites"""
        current_folder = self.folder_var.get().strip()
        
        if not current_folder:
            messagebox.showinfo("Add to Favorites", "No folder selected.")
            return
            
        if not os.path.isdir(current_folder):
            messagebox.showinfo("Add to Favorites", "Invalid folder path.")
            return
            
        if current_folder in self.favorite_folders:
            messagebox.showinfo("Add to Favorites", "This folder is already in your favorites.")
            return
            
        self.favorite_folders.append(current_folder)
        self.config["favorite_folders"] = self.favorite_folders
        self.save_config()
        self.update_favorites_menu()
        
        self.update_status(f"Added '{os.path.basename(current_folder) or current_folder}' to favorites.")
        
    def manage_favorites(self):
        """Open a dialog to manage favorite folders"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Manage Favorite Folders")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog on the main window
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Create main frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create listbox with scrollbar
        list_frame = ttk.LabelFrame(main_frame, text="Favorite Folders")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=listbox.yview)
        
        # Load and display favorite folders
        self.load_favorite_folders()  # Ensure favorites are loaded
        for folder in self.favorite_folders:
            folder_name = os.path.basename(folder) or folder
            listbox.insert(tk.END, f"{folder_name} ({folder})")
            
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        def load_selected():
            selected = listbox.curselection()
            if not selected:
                messagebox.showinfo("Load", "Please select a folder to load.")
                return
                
            index = selected[0]
            folder = self.favorite_folders[index]
            
            if os.path.exists(folder):
                self.folder_var.set(folder)
                self.scan_folder()
                dialog.destroy()
            else:
                messagebox.showerror("Error", f"Folder not found: {folder}")
                self.favorite_folders.remove(folder)
                self.config["favorite_folders"] = self.favorite_folders
                self.save_config()
                self.update_favorites_menu()
                
                # Update listbox
                listbox.delete(0, tk.END)
                for folder in self.favorite_folders:
                    folder_name = os.path.basename(folder) or folder
                    listbox.insert(tk.END, f"{folder_name} ({folder})")
        
        def remove_selected():
            selected = listbox.curselection()
            if not selected:
                messagebox.showinfo("Remove", "Please select a folder to remove.")
                return
                
            index = selected[0]
            folder = self.favorite_folders[index]
            
            if messagebox.askyesno("Remove", f"Remove '{os.path.basename(folder) or folder}' from favorites?"):
                self.favorite_folders.pop(index)
                self.config["favorite_folders"] = self.favorite_folders
                self.save_config()
                self.update_favorites_menu()
                
                # Update listbox
                listbox.delete(0, tk.END)
                for folder in self.favorite_folders:
                    folder_name = os.path.basename(folder) or folder
                    listbox.insert(tk.END, f"{folder_name} ({folder})")
                    
                self.update_status(f"Removed folder from favorites.")
                
        def move_up():
            selected = listbox.curselection()
            if not selected or selected[0] == 0:
                return
                
            index = selected[0]
            self.favorite_folders[index], self.favorite_folders[index-1] = self.favorite_folders[index-1], self.favorite_folders[index]
            self.config["favorite_folders"] = self.favorite_folders
            self.save_config()
            self.update_favorites_menu()
            
            # Update listbox
            listbox.delete(0, tk.END)
            for folder in self.favorite_folders:
                folder_name = os.path.basename(folder) or folder
                listbox.insert(tk.END, f"{folder_name} ({folder})")
                
            listbox.selection_set(index-1)
            
        def move_down():
            selected = listbox.curselection()
            if not selected or selected[0] == len(self.favorite_folders) - 1:
                return
                
            index = selected[0]
            self.favorite_folders[index], self.favorite_folders[index+1] = self.favorite_folders[index+1], self.favorite_folders[index]
            self.config["favorite_folders"] = self.favorite_folders
            self.save_config()
            self.update_favorites_menu()
            
            # Update listbox
            listbox.delete(0, tk.END)
            for folder in self.favorite_folders:
                folder_name = os.path.basename(folder) or folder
                listbox.insert(tk.END, f"{folder_name} ({folder})")
                
            listbox.selection_set(index+1)
        
        # Add double-click binding
        listbox.bind('<Double-Button-1>', lambda e: load_selected())
            
        # Buttons
        ttk.Button(button_frame, text="Load", command=load_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Remove", command=remove_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Move Up", command=move_up).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Move Down", command=move_down).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
        
        # Add status label
        status_label = ttk.Label(main_frame, text="Double-click a folder to load it")
        status_label.pack(pady=5)

    def load_favorite_folders(self):
        """Load favorite folders from config"""
        self.favorite_folders = self.config.get("favorite_folders", [])
        # Filter out non-existent folders
        self.favorite_folders = [f for f in self.favorite_folders if os.path.exists(f)]
        self.config["favorite_folders"] = self.favorite_folders
        self.save_config()

    def open_favorite_folder(self, folder):
        """Open a favorite folder"""
        if os.path.isdir(folder):
            self.folder_var.set(folder)
            self.scan_folder()
        else:
            messagebox.showerror("Error", f"Folder not found: {folder}")
            self.favorite_folders.remove(folder)
            self.config["favorite_folders"] = self.favorite_folders
            self.save_config()
            self.update_favorites_menu()
            
    def open_recent_folder(self, folder):
        """Open a recent folder"""
        if os.path.isdir(folder):
            self.folder_var.set(folder)
            self.scan_folder()
        else:
            messagebox.showerror("Error", f"Folder not found: {folder}")
            self.recent_folders.remove(folder)
            self.config["recent_folders"] = self.recent_folders
            self.save_config()
            self.update_recent_menu()
            
    def clear_recent_folders(self):
        """Clear all recent folders"""
        if messagebox.askyesno("Clear Recent", "Are you sure you want to clear all recent folders?"):
            self.recent_folders = []
            self.config["recent_folders"] = self.recent_folders
            self.save_config()
            self.update_recent_menu()
            self.update_status("Recent folders cleared.")
            
    def add_to_recent_folders(self, folder):
        """Add a folder to recent folders"""
        if folder in self.recent_folders:
            # Move to the top
            self.recent_folders.remove(folder)
            
        # Add to the beginning
        self.recent_folders.insert(0, folder)
        
        # Limit the number of recent folders
        if len(self.recent_folders) > self.max_recent_folders:
            self.recent_folders = self.recent_folders[:self.max_recent_folders]
            
        self.config["recent_folders"] = self.recent_folders
        self.save_config()
        self.update_recent_menu()
    
    def show_settings_dialog(self):
        """Show settings dialog"""
        settings = tk.Toplevel(self.root)
        settings.title(self.get_text("settings"))
        settings.geometry("500x400")
        settings.transient(self.root)
        settings.grab_set()
        
        # Center the dialog on the main window
        settings.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - settings.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - settings.winfo_height()) // 2
        settings.geometry(f"+{x}+{y}")
        
        # Create notebook for settings categories
        notebook = ttk.Notebook(settings)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # General settings
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text=self.get_text("general"))
        
        # Default depth
        depth_frame = ttk.LabelFrame(general_frame, text=self.get_text("default_depth"))
        depth_frame.pack(fill=tk.X, padx=10, pady=5)
        
        default_depth_var = tk.StringVar(value=self.config["default_depth"])
        default_depth_entry = ttk.Entry(depth_frame, textvariable=default_depth_var, width=10)
        default_depth_entry.pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Label(depth_frame, text="(empty = unlimited)").pack(side=tk.LEFT, padx=5)
        
        # Export settings
        export_frame = ttk.Frame(notebook)
        notebook.add(export_frame, text=self.get_text("export"))
        
        export_location_frame = ttk.LabelFrame(export_frame, text=self.get_text("export_location"))
        export_location_frame.pack(fill=tk.X, padx=10, pady=5)
        
        export_location_var = tk.StringVar(value=self.config["default_export_location"])
        export_location_entry = ttk.Entry(export_location_frame, textvariable=export_location_var)
        export_location_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        
        ttk.Button(export_location_frame, text=self.get_text("browse"), 
                   command=lambda: export_location_var.set(filedialog.askdirectory())).pack(side=tk.LEFT, padx=5)
        
        # Language settings
        language_frame = ttk.Frame(notebook)
        notebook.add(language_frame, text=self.get_text("language"))
        
        language_label_frame = ttk.LabelFrame(language_frame, text=self.get_text("interface_language"))
        language_label_frame.pack(fill=tk.X, padx=10, pady=5)
        
        language_var = tk.StringVar(value=self.config["language"])
        languages = [
            (self.get_text("english"), "en"),
            (self.get_text("spanish"), "es"),
            (self.get_text("french"), "fr"),
            (self.get_text("german"), "de")
        ]
        
        for lang_name, lang_code in languages:
            ttk.Radiobutton(language_label_frame, text=lang_name, value=lang_code, 
                           variable=language_var).pack(anchor=tk.W, padx=5, pady=2)
        
        # Updates settings
        updates_frame = ttk.Frame(notebook)
        notebook.add(updates_frame, text=self.get_text("updates"))
        
        updates_label_frame = ttk.LabelFrame(updates_frame, text=self.get_text("check_updates"))
        updates_label_frame.pack(fill=tk.X, padx=10, pady=5)
        
        check_updates_var = tk.BooleanVar(value=self.config["check_updates_on_startup"])
        ttk.Checkbutton(updates_label_frame, text=self.get_text("check_updates_startup"),
                       variable=check_updates_var).pack(anchor=tk.W, padx=5, pady=5)
        
        ttk.Button(updates_label_frame, text=self.get_text("check_updates_now"),
                  command=self.check_updates).pack(anchor=tk.W, padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(settings)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_settings():
            try:
                # Validate and save settings
                self.config["default_depth"] = default_depth_var.get()
                self.config["default_export_location"] = export_location_var.get()
                self.config["language"] = language_var.get()
                self.config["check_updates_on_startup"] = check_updates_var.get()
                
                self.save_config()
                settings.destroy()
                
                # Show restart message if language changed
                if language_var.get() != self.config.get("language"):
                    messagebox.showinfo("Restart Required", self.get_text("restart_required"))
                else:
                    messagebox.showinfo("Settings", self.get_text("settings_saved"))
            except Exception as e:
                messagebox.showerror("Error", self.get_text("error_saving").format(str(e)))
        
        ttk.Button(button_frame, text=self.get_text("cancel"), 
                  command=settings.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text=self.get_text("save"), 
                  command=save_settings).pack(side=tk.RIGHT, padx=5)
        
    def get_text(self, key):
        """Get translated text for the given key"""
        lang = self.config.get("language", "en")
        return self.translations.get(lang, {}).get(key, self.translations["en"][key])


def main():
    """Main entry point"""
    # Set DPI awareness on Windows
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    
    # Create root window with drag and drop support if available
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
            # Enable drag and drop for the root window
            root.drop_target_register(DND_FILES)
            print("TkinterDnD initialized successfully")
        except Exception as e:
            print(f"Error initializing TkinterDnD: {str(e)}")
            root = tk.Tk()
    else:
        root = tk.Tk()
    
    # Create application
    app = FolderTreeViewer(root)
    
    # Start main loop
    root.mainloop()


if __name__ == "__main__":
    main()