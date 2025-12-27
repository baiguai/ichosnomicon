import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import os
import sys
import shutil
from pathlib import Path
import json

try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    from mutagen.id3._frames import TIT2, TPE1, TALB, TDRC, TRCK, TCON, TPE2, COMM
    from mutagen.flac import FLAC
    from mutagen.oggvorbis import OggVorbis
    from mutagen.mp4 import MP4
    from mutagen.easyid3 import EasyID3
    from mutagen._file import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

class MusicPlaylistManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Music Playlist Manager")
        self.root.geometry("1600x700")
        
        # Apply dark theme
        self.setup_dark_theme()
        
        # Bind keyboard shortcuts
        self.root.bind('<Control-q>', lambda e: self.quit_app())
        self.root.bind('<Control-o>', lambda e: self.select_root())
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        self.root.bind('<Control-n>', lambda e: self.scan_directory())
        self.root.bind('<Control-p>', lambda e: self.create_playlist_dialog())
        self.root.bind('<Delete>', lambda e: self.delete_selected_files())
        self.root.bind('<F2>', lambda e: self.rename_selected_file())
        self.root.bind('<F5>', lambda e: self.update_library_list())
        self.root.bind('<Control-a>', lambda e: self.select_all())
        self.root.bind('<Escape>', lambda e: self.clear_selection())
        
        # Audio playback state
        self.currently_playing = None
        self.is_playing = False
        self.current_volume = 0.7
        self.song_length = 0
        self.is_seeking = False  # Flag to prevent update loop during manual seek
        self.song_start_time = 0  # Track when song started for accurate positioning
        
        # App directory - use script location even when frozen by PyInstaller
        if getattr(sys, 'frozen', False):
            import inspect
            script_path = Path(inspect.getfile(self.__class__))
            if script_path.name.startswith('music_mgr'):
                self.app_dir = Path(sys.argv[0]).parent.resolve()
            else:
                self.app_dir = Path(sys.executable).parent
        else:
            self.app_dir = Path(__file__).parent
        
        self.music_root = None
        self.conn = None
        self.cursor = None
        
        # Config path is still in app directory
        self.config_path = self.app_dir / "config.json"
        self.playlists_path = self.app_dir / "playlists"
        
        # Create playlists directory if it doesn't exist
        self.playlists_path.mkdir(exist_ok=True)
        
        self.load_config()
        if self.music_root:
            self.load_database()
        self.create_widgets()
        if self.music_root:
            self.update_library_list()
    
    def setup_dark_theme(self):
        """Configure dark theme colors and styles"""
        # Dark theme colors
        self.colors = {
            'bg': '#1e1e1e',
            'fg': '#e0e0e0',
            'select_bg': '#2d2d30',
            'select_fg': '#ffffff',
            'button_bg': '#3c3c3c',
            'entry_bg': '#2d2d30',
            'entry_fg': '#e0e0e0',
            'accent': '#6a7482',
            'accent_hover': '#005a9e',
            'border': '#3c3c3c',
            'highlight': '#6a7482',
        }
        
        # Configure root window
        self.root.configure(bg=self.colors['bg'])
        
        # Configure ttk styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure general styles
        style.configure('.',
                       background=self.colors['bg'],
                       foreground=self.colors['fg'],
                       fieldbackground=self.colors['entry_bg'],
                       bordercolor=self.colors['border'],
                       darkcolor=self.colors['bg'],
                       lightcolor=self.colors['bg'],
                       troughcolor=self.colors['select_bg'],
                       selectbackground=self.colors['accent'],
                       selectforeground=self.colors['select_fg'])
        
        # Frame
        style.configure('TFrame', background=self.colors['bg'])
        
        # Label
        style.configure('TLabel',
                       background=self.colors['bg'],
                       foreground=self.colors['fg'])
        
        # Button
        style.configure('TButton',
                       background=self.colors['button_bg'],
                       foreground=self.colors['fg'],
                       bordercolor=self.colors['border'],
                       lightcolor=self.colors['button_bg'],
                       darkcolor=self.colors['button_bg'])
        style.map('TButton',
                 background=[('active', self.colors['accent']),
                           ('pressed', self.colors['accent_hover'])],
                 foreground=[('active', self.colors['select_fg'])])
        
        # Accent Button
        style.configure('Accent.TButton',
                       background=self.colors['accent'],
                       foreground=self.colors['select_fg'])
        style.map('Accent.TButton',
                 background=[('active', self.colors['accent_hover']),
                           ('pressed', '#004578')])
        
        # Entry
        style.configure('TEntry',
                       fieldbackground=self.colors['entry_bg'],
                       foreground=self.colors['fg'],
                       bordercolor=self.colors['border'],
                       insertcolor=self.colors['fg'])
        
        # Treeview
        style.configure('Treeview',
                       background=self.colors['select_bg'],
                       foreground=self.colors['fg'],
                       fieldbackground=self.colors['select_bg'],
                       bordercolor=self.colors['border'])
        style.map('Treeview',
                 background=[('selected', self.colors['accent'])],
                 foreground=[('selected', self.colors['select_fg'])])
        style.configure('Treeview.Heading',
                       background=self.colors['button_bg'],
                       foreground=self.colors['fg'],
                       bordercolor=self.colors['border'])
        style.map('Treeview.Heading',
                 background=[('active', self.colors['accent'])])
        
        # Scrollbar
        style.configure('Vertical.TScrollbar',
                       background=self.colors['button_bg'],
                       troughcolor=self.colors['bg'],
                       bordercolor=self.colors['border'],
                       arrowcolor=self.colors['fg'])
    
    def quit_app(self):
        """Cleanly close the application"""
        if PYGAME_AVAILABLE and self.is_playing:
            pygame.mixer.music.stop()
        if self.conn:
            self.conn.close()
        self.root.quit()
    
    def focus_search(self):
        """Focus on the search field"""
        self.search_entry.focus_set()
    
    def delete_selected_files(self):
        """Delete all selected files"""
        selected_items = self.library_tree.selection()
        if not selected_items:
            return
        
        if len(selected_items) == 1:
            # Use existing single file delete method
            self.delete_file()
        else:
            # Bulk delete
            count = len(selected_items)
            if not messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to delete {count} selected files?\n\n"
                                       "This action cannot be undone!"):
                return
            
            deleted = 0
            errors = []
            
            for item_id in selected_items:
                try:
                    item = self.library_tree.item(item_id)
                    song_id = item['text']
                    filename = item['values'][0]
                    
                    # Get file path
                    self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (song_id,))
                    row = self.cursor.fetchone()
                    if row:
                        file_path = Path(self.music_root) / row[0]
                        
                        # Delete file
                        if file_path.exists():
                            file_path.unlink()
                        
                        # Remove from database
                        self.cursor.execute("DELETE FROM songs WHERE id = ?", (song_id,))
                        deleted += 1
                    else:
                        errors.append(f"{filename}: Not found in database")
                        
                except Exception as e:
                    errors.append(f"{filename}: {str(e)}")
            
            self.conn.commit()
            self.update_library_list()
            
            msg = f"Successfully deleted {deleted} files."
            if errors:
                msg += f"\n\nErrors:\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... and {len(errors) - 5} more errors"
            
            messagebox.showinfo("Bulk Delete Complete", msg)
    
    def rename_selected_file(self):
        """Rename the selected file"""
        selection = self.library_tree.selection()
        if selection:
            self.rename_file()
    
    def select_all(self):
        """Select all items in the library tree"""
        all_items = self.library_tree.get_children()
        self.library_tree.selection_set(all_items)
        self.update_selection_count()
    
    def clear_selection(self):
        """Clear all selections"""
        self.library_tree.selection_remove(self.library_tree.selection())
        self.update_selection_count()
    
    def load_database(self):
        """Load or create database in the music root directory"""
        if not self.music_root:
            return
        
        # Store database in the music root directory
        db_path = Path(self.music_root) / ".music_manager.db"
        
        # Close existing connection if any
        if self.conn:
            self.conn.close()
            
        self.conn = sqlite3.connect(str(db_path))
        self.cursor = self.conn.cursor()
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database"""
        if not self.conn:
            return
            
        # Create tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relative_path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                tags TEXT,
                artist TEXT,
                album TEXT
            )
        ''')
        
        # Check if we need to add the new columns to existing database
        self.cursor.execute("PRAGMA table_info(songs)")
        columns = [col[1] for col in self.cursor.fetchall()]
        
        if 'artist' not in columns:
            self.cursor.execute("ALTER TABLE songs ADD COLUMN artist TEXT")
        if 'album' not in columns:
            self.cursor.execute("ALTER TABLE songs ADD COLUMN album TEXT")
        
        self.conn.commit()
        
    def load_config(self):
        """Load configuration including music root directory"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.music_root = config.get('music_root')
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load config file: {e}")
                print("Creating new config file...")
                # Optionally backup the corrupted file
                if self.config_path.exists():
                    backup_path = self.config_path.with_suffix('.json.backup')
                    shutil.copy(self.config_path, backup_path)
                    print(f"Backed up corrupted config to: {backup_path}")
                # Initialize with default values
                self.music_root = None
                
    def save_config(self):
        """Save configuration"""
        config = {'music_root': self.music_root}
        with open(self.config_path, 'w') as f:
            json.dump(config, f)
            
    def create_widgets(self):
        """Create the GUI layout"""
        
        # Top frame - Music root selection
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Music Root Directory:").pack(side=tk.LEFT)
        self.root_label = ttk.Label(top_frame, text=self.music_root or "Not set", 
                                     foreground=self.colors['accent'])
        self.root_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(top_frame, text="Select Root", 
                   command=self.select_root).pack(side=tk.LEFT)
        ttk.Button(top_frame, text="Scan Directory", 
                   command=self.scan_directory).pack(side=tk.LEFT, padx=5)
        
        # Separator
        ttk.Separator(top_frame, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        # Selection info
        self.selection_label = ttk.Label(top_frame, text="0 selected")
        self.selection_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(top_frame, text="Create Playlist", 
                   command=self.create_playlist_dialog,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        # ttk.Button(top_frame, text="Manage Playlists", 
        #            command=self.manage_playlists_dialog).pack(side=tk.LEFT, padx=5)
        
        # Play button
        self.play_button = ttk.Button(top_frame, text="▶ Play", 
                                      command=self.toggle_playback)
        self.play_button.pack(side=tk.LEFT, padx=5)
        
        self.now_playing_label = ttk.Label(top_frame, text="", 
                                           foreground=self.colors['accent'])
        self.now_playing_label.pack(side=tk.LEFT, padx=10)

        # Seek bar
        self.seek_slider = ttk.Scale(top_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                     length=300, command=self.on_seek)
        self.seek_slider.pack(side=tk.LEFT, padx=5)
        self.seek_slider.config(state='disabled')

        # Time labels
        self.time_label = ttk.Label(top_frame, text="0:00 / 0:00", width=12)
        self.time_label.pack(side=tk.LEFT, padx=5)

        self.now_playing_label = ttk.Label(top_frame, text="", 
                                           foreground=self.colors['accent'])
        self.now_playing_label.pack(side=tk.LEFT, padx=10)

        # Volume control
        ttk.Label(top_frame, text="Volume:").pack(side=tk.LEFT, padx=(10, 5))

        self.volume_label = ttk.Label(top_frame, text=f"{int(self.current_volume * 100)}%",
                                       width=4)
        self.volume_slider = ttk.Scale(top_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                        length=100, command=self.on_volume_change)
        self.volume_slider.set(self.current_volume * 100)
        self.volume_slider.pack(side=tk.LEFT, padx=5)

        self.volume_label.pack(side=tk.LEFT)

        self.now_playing_label = ttk.Label(top_frame, text="", 
                                           foreground=self.colors['accent'])
        self.now_playing_label.pack(side=tk.LEFT, padx=10)
        
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.create_library_view(main_frame)
        
    def create_library_view(self, parent):
        """Create the library management view"""
        
        # Search frame
        search_frame = ttk.Frame(parent, padding="10")
        search_frame.pack(fill=tk.X)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.update_library_list())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(search_frame, text="Tags:").pack(side=tk.LEFT, padx=(20, 5))
        self.tag_filter_var = tk.StringVar()
        self.tag_filter_var.trace('w', lambda *args: self.update_library_list())
        tag_filter_entry = ttk.Entry(search_frame, textvariable=self.tag_filter_var, width=20)
        tag_filter_entry.pack(side=tk.LEFT)
        
        ttk.Label(search_frame, text="Artist:").pack(side=tk.LEFT, padx=(20, 5))
        self.artist_filter_var = tk.StringVar()
        self.artist_filter_var.trace('w', lambda *args: self.update_library_list())
        artist_filter_entry = ttk.Entry(search_frame, textvariable=self.artist_filter_var, width=20)
        artist_filter_entry.pack(side=tk.LEFT)
        
        ttk.Label(search_frame, text="Album:").pack(side=tk.LEFT, padx=(20, 5))
        self.album_filter_var = tk.StringVar()
        self.album_filter_var.trace('w', lambda *args: self.update_library_list())
        album_filter_entry = ttk.Entry(search_frame, textvariable=self.album_filter_var, width=20)
        album_filter_entry.pack(side=tk.LEFT)

        ttk.Label(search_frame, text="Path:").pack(side=tk.LEFT, padx=(20, 5))
        self.path_filter_var = tk.StringVar()
        self.path_filter_var.trace('w', lambda *args: self.update_library_list())
        path_filter_entry = ttk.Entry(search_frame, textvariable=self.path_filter_var, width=20)
        path_filter_entry.pack(side=tk.LEFT)
        
        # Library list with scrollbar
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.library_tree = ttk.Treeview(list_frame, columns=('Filename', 'Path', 'Artist', 'Album', 'Tags'), 
                                          yscrollcommand=scrollbar.set, selectmode='extended')
        self.library_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.library_tree.yview)
        
        self.library_tree.heading('#0', text='ID')
        self.library_tree.heading('Filename', text='Filename')
        self.library_tree.heading('Path', text='Path')
        self.library_tree.heading('Artist', text='Artist')
        self.library_tree.heading('Album', text='Album')
        self.library_tree.heading('Tags', text='Tags')
        
        self.library_tree.column('#0', width=50)
        self.library_tree.column('Filename', width=250)
        self.library_tree.column('Path', width=300)
        self.library_tree.column('Artist', width=150)
        self.library_tree.column('Album', width=150)
        self.library_tree.column('Tags', width=200)
        
        self.library_tree.bind('<Double-Button-1>', self.edit_tags)
        self.library_tree.bind('<Button-3>', self.show_context_menu)
        self.library_tree.bind('<<TreeviewSelect>>', self.update_selection_count)
        

        
        # Bind column headers for sorting
        for col in ['#0', 'Filename', 'Path', 'Artist', 'Album', 'Tags']:
            self.library_tree.heading(col, command=lambda c=col: self.sort_column(c, False))
        
        # Store sort state
        self.sort_column_name = None
        self.sort_reverse = False
        
        # Create context menu with dark theme
        self.context_menu = tk.Menu(self.library_tree, tearoff=0,
                                    bg=self.colors['button_bg'],
                                    fg=self.colors['fg'],
                                    activebackground=self.colors['accent'],
                                    activeforeground=self.colors['select_fg'])
        self.context_menu.add_command(label="Rename File", command=self.rename_file)
        self.context_menu.add_command(label="Edit ID3 Metadata", command=self.edit_id3_metadata)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy File Path", command=self.copy_file_path)
        self.context_menu.add_command(label="Delete File", command=self.delete_file)
        
        # Autocomplete frame (initially hidden)
        self.autocomplete_frame = ttk.Frame(parent)
        # Initially hidden, will be positioned at bottom when shown
        
        # Autocomplete listbox
        self.autocomplete_listbox = tk.Listbox(self.autocomplete_frame, height=6,
                                             bg=self.colors['entry_bg'],
                                             fg=self.colors['fg'],
                                             selectbackground=self.colors['accent'],
                                             selectforeground=self.colors['select_fg'],
                                             borderwidth=1,
                                             relief='solid',
                                             exportselection=False)
        self.autocomplete_scrollbar = ttk.Scrollbar(self.autocomplete_frame, orient="vertical", 
                                                  command=self.autocomplete_listbox.yview)
        self.autocomplete_listbox.configure(yscrollcommand=self.autocomplete_scrollbar.set)
        
        self.autocomplete_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.autocomplete_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Hide autocomplete frame initially
        self.autocomplete_frame.pack_forget()
        
        # Edit frame
        edit_frame = ttk.Frame(parent, padding="10")
        edit_frame.pack(fill=tk.X)
        
        ttk.Label(edit_frame, text="Selected song tags:").pack(side=tk.LEFT)
        self.tag_edit_var = tk.StringVar()
        self.tag_entry = ttk.Entry(edit_frame, textvariable=self.tag_edit_var, width=50)
        tag_edit_entry = self.tag_entry
        tag_edit_entry.pack(side=tk.LEFT, padx=5)
        
        # Bind events for autocomplete
        self.tag_edit_var.trace('w', self.on_tag_entry_change)
        self.tag_entry.bind('<KeyRelease>', self.on_tag_key_release)
        self.tag_entry.bind('<Return>', self.on_tag_enter)
        self.tag_entry.bind('<Escape>', self.hide_autocomplete)
        self.tag_entry.bind('<FocusOut>', self.on_tag_entry_focus_out)
        self.tag_entry.bind('<Down>', lambda e: self.select_autocomplete_suggestion(1))
        self.tag_entry.bind('<Up>', lambda e: self.select_autocomplete_suggestion(-1))
        self.autocomplete_listbox.bind('<<ListboxSelect>>', self.on_autocomplete_listbox_select)
        self.autocomplete_listbox.bind('<Double-Button-1>', self.on_autocomplete_listbox_double_click)
        
        ttk.Button(edit_frame, text="Update Tags", 
                   command=self.update_tags).pack(side=tk.LEFT)
        ttk.Button(edit_frame, text="Bulk Edit Tags", 
                   command=self.bulk_edit_tags_dialog).pack(side=tk.LEFT, padx=5)
    
    def update_selection_count(self, event=None):
        """Update the selection count label"""
        selected = len(self.library_tree.selection())
        self.selection_label.config(text=f"{selected} selected")
    
    def sort_column(self, col, reverse):
        """Sort treeview contents when a column header is clicked"""
        # Get all items
        items = [(self.library_tree.set(item, col), item) for item in self.library_tree.get_children('')]
        
        # Sort items
        if col == '#0':
            # Sort by ID (numeric)
            items.sort(key=lambda x: int(self.library_tree.item(x[1])['text']), reverse=reverse)
        else:
            # Sort alphabetically, case-insensitive
            items.sort(key=lambda x: x[0].lower(), reverse=reverse)
        
        # Rearrange items in sorted positions
        for index, (val, item) in enumerate(items):
            self.library_tree.move(item, '', index)
        
        # Update column heading to show sort direction
        col_name = col if col != '#0' else 'ID'
        arrow = ' ↓' if reverse else ' ↑'
        
        # Reset all column headers
        self.library_tree.heading('#0', text='ID')
        self.library_tree.heading('Filename', text='Filename')
        self.library_tree.heading('Path', text='Path')
        self.library_tree.heading('Artist', text='Artist')
        self.library_tree.heading('Album', text='Album')
        self.library_tree.heading('Tags', text='Tags')
        
        # Add arrow to sorted column
        if col == '#0':
            self.library_tree.heading('#0', text='ID' + arrow)
        else:
            self.library_tree.heading(col, text=col + arrow)
        
        # Reverse sort next time
        self.library_tree.heading(col, command=lambda: self.sort_column(col, not reverse))
    
    def toggle_playback(self):
        """Play or stop the selected song"""
        if not PYGAME_AVAILABLE:
            messagebox.showerror("Error", 
                               "pygame library not installed.\n"
                               "Install it with: pip install pygame")
            return
        
        selection = self.library_tree.selection()
        if not selection:
            if self.is_playing:
                self.stop_playback()
            else:
                messagebox.showwarning("Warning", "Please select a song to play")
            return
        
        # Get the selected song
        item = self.library_tree.item(selection[0])
        song_id = item['text']
        
        # If already playing this song, stop it
        if self.is_playing and self.currently_playing == song_id:
            self.stop_playback()
            return
        
        # Stop current playback if playing different song
        if self.is_playing:
            self.stop_playback()
        
        # Get file path
        self.cursor.execute("SELECT relative_path, filename FROM songs WHERE id = ?", (song_id,))
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Error", "Song not found in database")
            return
        
        file_path = Path(self.music_root) / row[0]
        filename = row[1]
        
        if not file_path.exists():
            messagebox.showerror("Error", f"File not found: {file_path}")
            return
        
        try:
            # Load and play the audio file
            pygame.mixer.music.load(str(file_path))
            pygame.mixer.music.set_volume(self.current_volume)
            pygame.mixer.music.play()
            
            # Get song length
            try:
                if MUTAGEN_AVAILABLE:
                    audio_file = MutagenFile(file_path)
                    if audio_file is not None and hasattr(audio_file, 'info'):
                        self.song_length = audio_file.info.length
                    else:
                        self.song_length = 0
                else:
                    self.song_length = 0
            except:
                self.song_length = 0
           
            self.song_start_time = 0
            self.is_playing = True
            self.currently_playing = song_id
            self.play_button.config(text="⏸ Stop")
            self.now_playing_label.config(text=f"♪ {filename}")
            
            # Enable seek bar and start updating it
            if self.song_length > 0:
                self.seek_slider.config(state='normal')
                self.seek_slider.set(0)
                # Initialize time label
                total_time = self.format_time(self.song_length)
                self.time_label.config(text=f"0:00 / {total_time}")
                self.update_seek_bar()
            else:
                self.seek_slider.config(state='disabled')
                self.time_label.config(text="--:-- / --:--")
            
            # Check when song finishes playing
            self.check_playback_status()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play audio: {str(e)}")
            self.stop_playback()
    
    def stop_playback(self):
        """Stop audio playback"""
        if PYGAME_AVAILABLE and self.is_playing:
            pygame.mixer.music.stop()
        
        self.is_playing = False
        self.currently_playing = None
        self.song_length = 0
        self.song_start_time = 0
        self.is_seeking = False
        self.play_button.config(text="▶ Play")
        self.now_playing_label.config(text="")
        self.seek_slider.config(state='disabled')
        self.seek_slider.set(0)
        self.time_label.config(text="0:00 / 0:00")
    
    def check_playback_status(self):
        """Check if audio is still playing and update UI accordingly"""
        if self.is_playing:
            if not pygame.mixer.music.get_busy():
                # Song finished playing
                self.stop_playback()
            else:
                # Check again in 100ms
                self.root.after(100, self.check_playback_status)

    def on_seek(self, value):
        """Handle seek bar changes"""
        if not PYGAME_AVAILABLE or self.song_length <= 0:
            return
        
        # Only allow seeking if we have a valid song loaded
        if not self.currently_playing:
            return
        
        # Mark that we're seeking
        self.is_seeking = True
        
        # Get the desired position in seconds
        position = (float(value) / 100) * self.song_length
        
        # Get the current file path
        self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (self.currently_playing,))
        row = self.cursor.fetchone()
        if not row:
            self.is_seeking = False
            return
        
        file_path = Path(self.music_root) / row[0]
        
        try:
            # Reload the music file and play from position
            pygame.mixer.music.load(str(file_path))
            pygame.mixer.music.set_volume(self.current_volume)
            
            # For MP3 files, set_pos works in seconds
            pygame.mixer.music.play(start=position)
            
            # Update start time for accurate position tracking
            self.song_start_time = position
            
            # Resume playing state
            if not self.is_playing:
                self.is_playing = True
                self.play_button.config(text="⏸ Stop")
                self.check_playback_status()
            
        except Exception as e:
            print(f"Seek error: {e}")
        
        finally:
            # Re-enable the update loop after a short delay
            self.root.after(200, lambda: setattr(self, 'is_seeking', False))

    def update_seek_bar(self):
        """Update the seek bar position based on current playback position"""
        if not self.is_playing or not PYGAME_AVAILABLE:
            return
            
        if not self.is_seeking:
            try:
                # Get current position in milliseconds, convert to seconds
                pos_ms = pygame.mixer.music.get_pos()
                
                # get_pos() returns time since start of current play, not file position
                # Add the start time offset for accurate position
                if pos_ms >= 0:
                    current_pos = (pos_ms / 1000.0) + self.song_start_time
                    
                    # Clamp to song length
                    if current_pos > self.song_length:
                        current_pos = self.song_length
                    
                    if self.song_length > 0:
                        # Update slider position
                        percentage = (current_pos / self.song_length) * 100
                        self.seek_slider.set(percentage)
                        
                        # Update time label
                        current_time = self.format_time(current_pos)
                        total_time = self.format_time(self.song_length)
                        self.time_label.config(text=f"{current_time} / {total_time}")
            except Exception as e:
                print(f"Seek bar update error: {e}")
        
        # Continue updating every 100ms while playing
        if self.is_playing:
            self.root.after(100, self.update_seek_bar)

    def format_time(self, seconds):
        """Format seconds into MM:SS"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

    def on_volume_change(self, value):
        """Handle volume slider changes"""
        if PYGAME_AVAILABLE:
            self.current_volume = float(value) / 100
            self.volume_label.config(text=f"{int(float(value))}%")
            pygame.mixer.music.set_volume(self.current_volume)

    def create_playlist_dialog(self):
        """Show dialog to create a playlist from selected songs"""
        selected_items = self.library_tree.selection()
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select songs to add to the playlist")
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Create Playlist")
        dialog.geometry("600x410")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Title
        ttk.Label(dialog, text=f"Create Playlist ({len(selected_items)} songs)", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=15)
        
        # Playlist name
        name_frame = ttk.Frame(dialog)
        name_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(name_frame, text="Playlist Name:").pack(side=tk.LEFT)
        playlist_name_var = tk.StringVar(value="My Playlist")
        name_entry = ttk.Entry(name_frame, textvariable=playlist_name_var, width=40)
        name_entry.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()
        
        # Options frame
        options_frame = ttk.LabelFrame(dialog, text="Playlist Type", padding="15")
        options_frame.pack(fill=tk.X, padx=20, pady=10)
        
        playlist_type = tk.StringVar(value="folder")
        
        ttk.Radiobutton(options_frame, text="Folder - Copy files to a new folder", 
                       variable=playlist_type, value="folder").pack(anchor=tk.W, pady=5)
        
        ttk.Radiobutton(options_frame, text="M3U Playlist - Create .m3u playlist file", 
                       variable=playlist_type, value="m3u").pack(anchor=tk.W, pady=5)
        
        ttk.Radiobutton(options_frame, text="PLS Playlist - Create .pls playlist file", 
                       variable=playlist_type, value="pls").pack(anchor=tk.W, pady=5)
        
        # Destination
        dest_frame = ttk.Frame(dialog)
        dest_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(dest_frame, text="Destination:").pack(side=tk.LEFT)
        dest_label = ttk.Label(dest_frame, text="Not selected", foreground="#808080")
        dest_label.pack(side=tk.LEFT, padx=10)
        
        destination = {'path': None}
        
        def select_dest():
            if playlist_type.get() == "folder":
                path = filedialog.askdirectory(title="Select Destination Folder")
            else:
                path = filedialog.asksaveasfilename(
                    title="Save Playlist File",
                    defaultextension=f".{playlist_type.get()}",
                    filetypes=[(f"{playlist_type.get().upper()} Files", f"*.{playlist_type.get()}")]
                )
            
            if path:
                destination['path'] = path
                dest_label.config(text=path, foreground=self.colors['accent'])
        
        ttk.Button(dest_frame, text="Browse...", command=select_dest).pack(side=tk.LEFT)
        
        # Spacer
        ttk.Frame(dialog).pack(fill=tk.BOTH, expand=True)
        
        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=15)
        
        # Center the buttons
        button_container = ttk.Frame(button_frame)
        button_container.pack()
        
        def create_playlist():
            playlist_name = playlist_name_var.get().strip()
            if not playlist_name:
                messagebox.showerror("Error", "Please enter a playlist name")
                return
            
            if not destination['path']:
                messagebox.showerror("Error", "Please select a destination")
                return
            
            try:
                # Get selected song info
                songs = []
                for item_id in selected_items:
                    item = self.library_tree.item(item_id)
                    song_id = item['text']
                    self.cursor.execute("SELECT relative_path, filename FROM songs WHERE id = ?", (song_id,))
                    row = self.cursor.fetchone()
                    if row:
                        songs.append({'relative_path': row[0], 'filename': row[1]})
                
                if playlist_type.get() == "folder":
                    # Create folder and copy files
                    playlist_dir = Path(destination['path']) / playlist_name
                    
                    if playlist_dir.exists():
                        if not messagebox.askyesno("Confirm", 
                                                   f"Folder '{playlist_name}' already exists. Overwrite?"):
                            return
                        shutil.rmtree(playlist_dir)
                    
                    playlist_dir.mkdir(parents=True)
                    
                    # Create progress dialog
                    progress_dialog = tk.Toplevel(dialog)
                    progress_dialog.title("Creating Playlist")
                    progress_dialog.geometry("500x150")
                    progress_dialog.transient(dialog)
                    progress_dialog.grab_set()
                    progress_dialog.configure(bg=self.colors['bg'])

                    progress_dialog.update_idletasks()
                    x = dialog.winfo_x() + (dialog.winfo_width() // 2) - (progress_dialog.winfo_width() // 2)
                    y = dialog.winfo_y() + (dialog.winfo_height() // 2) - (progress_dialog.winfo_height() // 2)
                    progress_dialog.geometry(f"+{x}+{y}")

                    ttk.Label(progress_dialog, text=f"Copying files to '{playlist_name}'...",
                             font=('TkDefaultFont', 10, 'bold')).pack(pady=10)

                    progress_label = ttk.Label(progress_dialog, text=f"0 / {len(songs)}")
                    progress_label.pack(pady=5)

                    progress_bar = ttk.Progressbar(progress_dialog, length=400, mode='determinate', maximum=len(songs))
                    progress_bar.pack(pady=10)

                    current_file_label = ttk.Label(progress_dialog, text="", wraplength=450)
                    current_file_label.pack(pady=5)
                    
                    copied = 0
                    for idx, song in enumerate(songs):
                        source = Path(self.music_root) / song['relative_path']
                        destination_file = playlist_dir / song['filename']
                        
                        progress_label.config(text=f"{idx + 1} / {len(songs)}")
                        current_file_label.config(text=f"Copying: {song['filename']}")
                        progress_dialog.update()

                        try:
                            shutil.copy2(source, destination_file)
                            copied += 1
                        except Exception as e:
                            print(f"Error copying {song['filename']}: {e}")

                        progress_bar['value'] = idx + 1
                        progress_dialog.update()
                    
                    progress_dialog.destroy()
                    
                    messagebox.showinfo("Success", 
                                       f"Created playlist folder with {copied} files at:\n{playlist_dir}")
                
                elif playlist_type.get() == "m3u":
                    # Create M3U playlist
                    playlist_file = Path(destination['path'])
                    
                    with open(playlist_file, 'w', encoding='utf-8') as f:
                        f.write("#EXTM3U\n")
                        for song in songs:
                            full_path = Path(self.music_root) / song['relative_path']
                            f.write(f"{full_path}\n")
                    
                    messagebox.showinfo("Success", 
                                       f"Created M3U playlist with {len(songs)} songs at:\n{playlist_file}")
                
                elif playlist_type.get() == "pls":
                    # Create PLS playlist
                    playlist_file = Path(destination['path'])
                    
                    with open(playlist_file, 'w', encoding='utf-8') as f:
                        f.write("[playlist]\n")
                        for idx, song in enumerate(songs, 1):
                            full_path = Path(self.music_root) / song['relative_path']
                            f.write(f"File{idx}={full_path}\n")
                        f.write(f"NumberOfEntries={len(songs)}\n")
                        f.write("Version=2\n")
                    
                    messagebox.showinfo("Success", 
                                       f"Created PLS playlist with {len(songs)} songs at:\n{playlist_file}")
                
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create playlist: {str(e)}")
        
        ttk.Button(button_container, text="Create", command=create_playlist, 
                  style='Accent.TButton', width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Cancel", command=dialog.destroy, 
                  width=15).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key
        dialog.bind('<Return>', lambda e: create_playlist())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def manage_playlists_dialog(self):
        """Show dialog to manage saved playlists"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Manage Playlists")
        dialog.geometry("700x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Title
        ttk.Label(dialog, text="Saved Playlists", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=15)
        
        # Playlist list with scrollbar
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        playlist_tree = ttk.Treeview(list_frame, columns=('Name', 'Type', 'Songs', 'Path'), 
                                   yscrollcommand=scrollbar.set, selectmode='browse')
        playlist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=playlist_tree.yview)
        
        playlist_tree.heading('#0', text='ID')
        playlist_tree.heading('Name', text='Name')
        playlist_tree.heading('Type', text='Type')
        playlist_tree.heading('Songs', text='Songs')
        playlist_tree.heading('Path', text='Path')
        
        playlist_tree.column('#0', width=50)
        playlist_tree.column('Name', width=150)
        playlist_tree.column('Type', width=80)
        playlist_tree.column('Songs', width=80)
        playlist_tree.column('Path', width=300)
        
        # Load existing playlists
        self.load_saved_playlists(playlist_tree)
        
        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=15)
        
        def load_playlist():
            selection = playlist_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a playlist to load")
                return
            
            item = playlist_tree.item(selection[0])
            playlist_path = item['values'][3]
            
            if not Path(playlist_path).exists():
                messagebox.showerror("Error", f"Playlist file not found: {playlist_path}")
                return
            
            # Load playlist and filter library
            self.load_playlist_to_library(playlist_path)
            dialog.destroy()
        
        def delete_playlist():
            selection = playlist_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a playlist to delete")
                return
            
            item = playlist_tree.item(selection[0])
            playlist_name = item['values'][0]
            playlist_path = item['values'][3]
            
            if not messagebox.askyesno("Confirm Delete", 
                                       f"Are you sure you want to delete '{playlist_name}'?"):
                return
            
            try:
                Path(playlist_path).unlink()
                playlist_tree.delete(selection[0])
                messagebox.showinfo("Success", f"Playlist '{playlist_name}' deleted")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete playlist: {str(e)}")
        
        def export_playlist():
            selection = playlist_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a playlist to export")
                return
            
            item = playlist_tree.item(selection[0])
            playlist_path = item['values'][3]
            
            export_path = filedialog.asksaveasfilename(
                title="Export Playlist",
                defaultextension=".json",
                filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
            )
            
            if export_path:
                try:
                    import shutil
                    shutil.copy2(playlist_path, export_path)
                    messagebox.showinfo("Success", f"Playlist exported to: {export_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to export playlist: {str(e)}")
        
        # Center buttons
        button_container = ttk.Frame(button_frame)
        button_container.pack()
        
        ttk.Button(button_container, text="Load", command=load_playlist, 
                  style='Accent.TButton', width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Delete", command=delete_playlist, 
                  width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Export", command=export_playlist, 
                  width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Close", command=dialog.destroy, 
                  width=12).pack(side=tk.LEFT, padx=5)
        
        # Bind double-click to load
        playlist_tree.bind('<Double-Button-1>', lambda e: load_playlist())
        
        # Bind Escape key
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def load_saved_playlists(self, tree):
        """Load saved playlists into the treeview"""
        # Clear existing items
        tree.delete(*tree.get_children())
        
        # Scan for playlist files
        playlist_files = []
        
        # Look for .m3u files
        for m3u_file in self.playlists_path.glob("*.m3u"):
            playlist_files.append(('M3U', m3u_file))
        
        # Look for .pls files  
        for pls_file in self.playlists_path.glob("*.pls"):
            playlist_files.append(('PLS', pls_file))
        
        # Look for .json playlist files (our custom format)
        for json_file in self.playlists_path.glob("*.json"):
            playlist_files.append(('JSON', json_file))
        
        # Add to tree
        for idx, (playlist_type, file_path) in enumerate(playlist_files, 1):
            try:
                if playlist_type == 'JSON':
                    # Count songs in JSON playlist
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        song_count = len(data.get('songs', []))
                elif playlist_type == 'M3U':
                    # Count lines in M3U file (excluding #EXTM3U)
                    with open(file_path, 'r') as f:
                        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                        song_count = len(lines)
                elif playlist_type == 'PLS':
                    # Count File entries in PLS file
                    with open(file_path, 'r') as f:
                        content = f.read()
                        song_count = content.count('File')
                else:
                    song_count = 0
                
                tree.insert('', tk.END, text=idx, 
                          values=(file_path.stem, playlist_type, song_count, str(file_path)))
                          
            except Exception as e:
                print(f"Error loading playlist {file_path}: {e}")
    
    def load_playlist_to_library(self, playlist_path):
        """Load a playlist and filter the library to show only those songs"""
        playlist_path = Path(playlist_path)
        playlist_songs = set()
        
        try:
            if playlist_path.suffix.lower() == '.json':
                # Load JSON playlist
                with open(playlist_path, 'r') as f:
                    data = json.load(f)
                    for song in data.get('songs', []):
                        playlist_songs.add(song.get('relative_path', ''))
                        
            elif playlist_path.suffix.lower() == '.m3u':
                # Load M3U playlist
                with open(playlist_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Convert absolute path to relative if needed
                            line_path = Path(line)
                            if line_path.is_absolute():
                                try:
                                    rel_path = str(line_path.relative_to(Path(self.music_root)))
                                    playlist_songs.add(rel_path)
                                except ValueError:
                                    # Path is not relative to music root
                                    pass
                            else:
                                playlist_songs.add(line)
                                
            elif playlist_path.suffix.lower() == '.pls':
                # Load PLS playlist
                with open(playlist_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('File'):
                            file_path = line.split('=', 1)[1]
                            line_path = Path(file_path)
                            if line_path.is_absolute():
                                try:
                                    rel_path = str(line_path.relative_to(Path(self.music_root)))
                                    playlist_songs.add(rel_path)
                                except ValueError:
                                    pass
                            else:
                                playlist_songs.add(file_path)
            
            # Filter library to show only playlist songs
            self.filter_library_to_playlist(playlist_songs)
            
            # Show status
            self.now_playing_label.config(text=f"♪ Loaded playlist: {playlist_path.stem} ({len(playlist_songs)} songs)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load playlist: {str(e)}")
    
    def filter_library_to_playlist(self, playlist_songs):
        """Filter the library tree to show only songs in the playlist"""
        # Clear current selection
        self.library_tree.selection_remove(self.library_tree.get_children())
        
        # Select and show only playlist songs
        for item in self.library_tree.get_children():
            item_data = self.library_tree.item(item)
            song_id = item_data['text']
            
            # Get relative path from database
            self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (song_id,))
            row = self.cursor.fetchone()
            if row and row[0] in playlist_songs:
                self.library_tree.selection_add(item)
        
        # Update selection count
        self.update_selection_count()
        
    def select_root(self):
        """Select the music root directory"""
        directory = filedialog.askdirectory(title="Select Music Root Directory")
        if directory:
            self.music_root = directory
            self.root_label.config(text=directory)
            self.save_config()
            self.load_database()
            self.update_library_list()
            
            # Check if database has songs
            self.cursor.execute("SELECT COUNT(*) FROM songs")
            count = self.cursor.fetchone()[0]
            
            if count > 0:
                messagebox.showinfo("Database Loaded", 
                                  f"Loaded existing database with {count} songs.\n"
                                  "Your tags and data have been preserved!")
            else:
                messagebox.showinfo("New Database", 
                                  "New database created. Click 'Scan Directory' to add songs.")
            
    def scan_directory(self):
        """Scan the music directory and populate database, preserving existing tags"""
        if not self.music_root:
            messagebox.showerror("Error", "Please select a music root directory first")
            return
            
        if not os.path.exists(self.music_root):
            messagebox.showerror("Error", "Music root directory does not exist")
            return
        
        # First, get all existing songs with their tags
        self.cursor.execute("SELECT relative_path, tags FROM songs")
        existing_songs = {row[0]: row[1] for row in self.cursor.fetchall()}
        
        # Clear existing songs
        self.cursor.execute("DELETE FROM songs")
        
        audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
        music_root_path = Path(self.music_root)
        
        # First pass: collect all audio files
        audio_files = []
        for file_path in music_root_path.rglob('*'):
            if file_path.suffix.lower() in audio_extensions:
                audio_files.append(file_path)
        
        total_files = len(audio_files)
        if total_files == 0:
            messagebox.showinfo("No Files", "No audio files found in the selected directory")
            return
        
        # Create progress dialog
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("Scanning Directory")
        progress_dialog.geometry("500x150")
        progress_dialog.transient(self.root)
        progress_dialog.grab_set()
        progress_dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        progress_dialog.update_idletasks()
        x = (progress_dialog.winfo_screenwidth() // 2) - (progress_dialog.winfo_width() // 2)
        y = (progress_dialog.winfo_screenheight() // 2) - (progress_dialog.winfo_height() // 2)
        progress_dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(progress_dialog, text="Scanning audio files...", 
                 font=('TkDefaultFont', 10, 'bold')).pack(pady=10)
        
        progress_label = ttk.Label(progress_dialog, text="0 / 0")
        progress_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(progress_dialog, length=400, mode='determinate', maximum=total_files)
        progress_bar.pack(pady=10)
        
        current_file_label = ttk.Label(progress_dialog, text="", wraplength=450)
        current_file_label.pack(pady=5)
        
        count = 0
        preserved_tags = 0
        
        # Process files
        for idx, file_path in enumerate(audio_files):
            relative_path = str(file_path.relative_to(music_root_path))
            filename = file_path.name
            
            # Use existing tags if available, otherwise empty string
            tags = existing_songs.get(relative_path, "")
            if relative_path in existing_songs and tags:
                preserved_tags += 1
            
            # Try to read metadata for various audio formats
            artist = ""
            album = ""
            if MUTAGEN_AVAILABLE:
                try:
                    # Use mutagen's universal File class for broad format support
                    audio_file = MutagenFile(file_path)
                    
                    if audio_file is not None:
                        # Handle different format types
                        if file_path.suffix.lower() == '.mp3':
                            # MP3 with ID3 tags
                            if hasattr(audio_file, 'tags') and audio_file.tags:
                                if 'TPE1' in audio_file.tags:
                                    artist = str(audio_file.tags['TPE1'])
                                if 'TALB' in audio_file.tags:
                                    album = str(audio_file.tags['TALB'])
                        
                        elif file_path.suffix.lower() == '.flac':
                            # FLAC format
                            if hasattr(audio_file, 'tags') and audio_file.tags:
                                artist = audio_file.tags.get('ARTIST', [''])[0]
                                album = audio_file.tags.get('ALBUM', [''])[0]
                        
                        elif file_path.suffix.lower() in ['.ogg', '.oga']:
                            # OGG Vorbis format
                            if hasattr(audio_file, 'tags') and audio_file.tags:
                                artist = audio_file.tags.get('ARTIST', [''])[0]
                                album = audio_file.tags.get('ALBUM', [''])[0]
                        
                        elif file_path.suffix.lower() in ['.m4a', '.mp4']:
                            # MP4/AAC format
                            if hasattr(audio_file, 'tags') and audio_file.tags:
                                artist = audio_file.tags.get('\xa9ART', [''])[0]
                                album = audio_file.tags.get('\xa9alb', [''])[0]
                        
                        else:
                            # Try EasyID3 for other formats that support it
                            try:
                                easy_audio = EasyID3(file_path)
                                artist = easy_audio.get('artist', [''])[0]
                                album = easy_audio.get('album', [''])[0]
                            except:
                                pass  # EasyID3 not supported for this format
                
                except Exception:
                    pass  # Skip files with read errors
            
            self.cursor.execute(
                "INSERT OR IGNORE INTO songs (relative_path, filename, tags, artist, album) VALUES (?, ?, ?, ?, ?)",
                (relative_path, filename, tags, artist, album)
            )
            count += 1
            
            # Update progress every 10 files or on last file
            if idx % 10 == 0 or idx == total_files - 1:
                progress_bar['value'] = idx + 1
                progress_label.config(text=f"{idx + 1} / {total_files}")
                current_file_label.config(text=f"Processing: {filename}")
                progress_dialog.update()
        
        self.conn.commit()
        progress_dialog.destroy()
        self.update_library_list()
        
        msg = f"Scanned {count} audio files"
        if preserved_tags > 0:
            msg += f"\nPreserved tags for {preserved_tags} existing songs"
        messagebox.showinfo("Success", msg)
        
    def update_library_list(self):
        """Update the library list based on search filters"""
        if not self.conn:
            return
            
        self.library_tree.delete(*self.library_tree.get_children())
        
        search_term = self.search_var.get().lower()
        tag_filter = self.tag_filter_var.get().lower()
        artist_filter = self.artist_filter_var.get().lower()
        album_filter = self.album_filter_var.get().lower()
        path_filter = self.path_filter_var.get().lower()
        
        query = "SELECT id, filename, relative_path, artist, album, tags FROM songs WHERE 1=1"
        params = []
        
        # If path filter is used, only apply path filter
        if path_filter:
            query += " AND LOWER(relative_path) LIKE ?"
            params.append(f"{path_filter}%")
        else:
            # Otherwise apply all other filters
            if search_term:
                query += " AND LOWER(filename) LIKE ?"
                params.append(f"%{search_term}%")
                
            if tag_filter:
                query += " AND LOWER(tags) LIKE ?"
                params.append(f"%{tag_filter}%")
            
            if artist_filter:
                query += " AND LOWER(artist) LIKE ?"
                params.append(f"%{artist_filter}%")
            
            if album_filter:
                query += " AND LOWER(album) LIKE ?"
                params.append(f"%{album_filter}%")
            
        self.cursor.execute(query, params)
        
        for row in self.cursor.fetchall():
            song_id, filename, relative_path, artist, album, tags = row
            # Extract parent directory path without filename
            parent_path = str(Path(relative_path).parent)
            # Show "." for files in root directory
            if parent_path == '.':
                parent_path = '(root)'
            self.library_tree.insert('', tk.END, text=song_id, 
                            values=(filename, parent_path, artist or '', album or '', tags or ''))
        
        self.update_selection_count()
            
    def edit_tags(self, event):
        """Load selected song tags for editing"""
        selection = self.library_tree.selection()
        if selection:
            item = self.library_tree.item(selection[0])
            song_id = item['text']
            tags = item['values'][4]
            self.tag_edit_var.set(tags)
            self.current_edit_id = song_id
            self.root.after(10, lambda: self.tag_entry.focus_set() and self.tag_entry.select_range(0, tk.END))
    
    def show_context_menu(self, event):
        """Show context menu on right-click"""
        # Select the item under the cursor
        item = self.library_tree.identify_row(event.y)
        if item:
            self.library_tree.selection_set(item)
            
            # Check if it's an MP3 file to enable/disable ID3 editing
            item_data = self.library_tree.item(item)
            filename = item_data['values'][0]
            is_mp3 = filename.lower().endswith('.mp3')
            
            # Update menu state
            if is_mp3 and MUTAGEN_AVAILABLE:
                self.context_menu.entryconfig("Edit ID3 Metadata", state="normal")
            else:
                self.context_menu.entryconfig("Edit ID3 Metadata", state="disabled")
            
            self.context_menu.post(event.x_root, event.y_root)
    
    def rename_file(self):
        """Rename the selected file"""
        selection = self.library_tree.selection()
        if not selection:
            return
        
        item = self.library_tree.item(selection[0])
        song_id = item['text']
        current_filename = item['values'][0]
        
        # Get the file info from database
        self.cursor.execute("SELECT relative_path, filename FROM songs WHERE id = ?", (song_id,))
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Error", "Song not found in database")
            return
        
        relative_path, db_filename = row
        file_path = Path(self.music_root) / relative_path
        
        if not file_path.exists():
            messagebox.showerror("Error", f"File not found: {file_path}")
            return
        
        # Create dialog for new filename with dark theme
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename File")
        dialog.geometry("500x150")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(dialog, text="Current filename:", padding="10").pack()
        ttk.Label(dialog, text=current_filename, font=('TkDefaultFont', 10, 'bold')).pack()
        
        ttk.Label(dialog, text="New filename:", padding="10").pack()
        new_name_var = tk.StringVar(value=current_filename)
        entry = ttk.Entry(dialog, textvariable=new_name_var, width=60)
        entry.pack(padx=10, pady=5)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        def do_rename():
            new_filename = new_name_var.get().strip()
            if not new_filename:
                messagebox.showerror("Error", "Filename cannot be empty")
                return
            
            if new_filename == current_filename:
                dialog.destroy()
                return
            
            # Check if file extension is preserved
            old_ext = file_path.suffix
            new_path = file_path.parent / new_filename
            
            if new_path.suffix.lower() != old_ext.lower():
                if not messagebox.askyesno("Confirm", 
                    f"Warning: File extension changed from '{old_ext}' to '{new_path.suffix}'.\n"
                    "This may make the file unplayable. Continue?"):
                    return
            
            # Check if target exists
            if new_path.exists():
                messagebox.showerror("Error", f"A file named '{new_filename}' already exists")
                return
            
            try:
                # Rename the actual file
                file_path.rename(new_path)
                
                # Update database
                new_relative_path = str(new_path.relative_to(Path(self.music_root)))
                self.cursor.execute(
                    "UPDATE songs SET relative_path = ?, filename = ? WHERE id = ?",
                    (new_relative_path, new_filename, song_id)
                )
                self.conn.commit()
                
                # Update the display
                self.update_library_list()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to rename file: {str(e)}")
        
        ttk.Button(button_frame, text="Rename", command=do_rename).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Bind Enter key to rename
        entry.bind('<Return>', lambda e: do_rename())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def edit_id3_metadata(self):
        """Edit ID3 metadata for the selected MP3 file"""
        if not MUTAGEN_AVAILABLE:
            messagebox.showerror("Error", "Mutagen library not installed.\n"
                               "Install it with: pip install mutagen")
            return
        
        selection = self.library_tree.selection()
        if not selection:
            return
        
        item = self.library_tree.item(selection[0])
        song_id = item['text']
        current_filename = item['values'][0]
        
        # Verify it's an MP3 file
        if not current_filename.lower().endswith('.mp3'):
            messagebox.showerror("Error", "ID3 metadata editing is only available for MP3 files")
            return
        
        # Get the file path from database
        self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (song_id,))
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Error", "Song not found in database")
            return
        
        file_path = Path(self.music_root) / row[0]
        
        if not file_path.exists():
            messagebox.showerror("Error", f"File not found: {file_path}")
            return
        
        try:
            # Load the MP3 file
            audio = MP3(file_path, ID3=ID3)
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                audio.add_tags()
            
            # Get current values
            current_values = {
                'title': str(audio.tags.get('TIT2', [''])[0]) if 'TIT2' in audio.tags else '',
                'artist': str(audio.tags.get('TPE1', [''])[0]) if 'TPE1' in audio.tags else '',
                'album': str(audio.tags.get('TALB', [''])[0]) if 'TALB' in audio.tags else '',
                'year': str(audio.tags.get('TDRC', [''])[0]) if 'TDRC' in audio.tags else '',
                'track': str(audio.tags.get('TRCK', [''])[0]) if 'TRCK' in audio.tags else '',
                'genre': str(audio.tags.get('TCON', [''])[0]) if 'TCON' in audio.tags else '',
                'album_artist': str(audio.tags.get('TPE2', [''])[0]) if 'TPE2' in audio.tags else '',
                'comment': str(audio.tags.get('COMM::eng', [''])[0]) if 'COMM::eng' in audio.tags else '',
            }
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read ID3 tags: {str(e)}")
            return
        
        # Create dialog for editing metadata
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit ID3 Metadata - {current_filename}")
        dialog.geometry("600x450")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Main content frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill="both", expand=True)

        # Create scrollable frame
        canvas = tk.Canvas(main_frame, bg=self.colors['bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Title label
        title_label = ttk.Label(scrollable_frame, text=f"Editing: {current_filename}", 
                               font=('TkDefaultFont', 10, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=10, padx=10, sticky='w')
        
        # Create input fields
        fields = {}
        entries = []
        field_definitions = [
            ('title', 'Title:'),
            ('artist', 'Artist:'),
            ('album', 'Album:'),
            ('album_artist', 'Album Artist:'),
            ('year', 'Year:'),
            ('track', 'Track Number:'),
            ('genre', 'Genre:'),
            ('comment', 'Comment:'),
        ]
        
        for idx, (field_name, field_label) in enumerate(field_definitions, start=1):
            ttk.Label(scrollable_frame, text=field_label).grid(row=idx, column=0, 
                                                               sticky='w', padx=10, pady=5)
            
            if field_name == 'comment':
                # Multi-line text widget for comment
                text_widget = tk.Text(scrollable_frame, width=50, height=4,
                                     bg=self.colors['entry_bg'],
                                     fg=self.colors['fg'],
                                     insertbackground=self.colors['fg'],
                                     highlightthickness=1,
                                     highlightbackground=self.colors['border'],
                                     highlightcolor=self.colors['accent'])
                text_widget.grid(row=idx, column=1, padx=10, pady=5, sticky='ew')
                text_widget.insert('1.0', current_values[field_name])
                fields[field_name] = text_widget
            else:
                var = tk.StringVar(value=current_values[field_name])
                entry = ttk.Entry(scrollable_frame, textvariable=var, width=50)
                entry.grid(row=idx, column=1, padx=10, pady=5, sticky='ew')
                entries.append(entry)
                fields[field_name] = var
        
        scrollable_frame.columnconfigure(1, weight=1)

        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side="bottom", fill="x", pady=10)

        # Center buttons
        button_container = ttk.Frame(button_frame)
        button_container.pack()

        def save_metadata():
            try:
                # Get new values
                new_values = {}
                for field_name, widget in fields.items():
                    if isinstance(widget, tk.Text):
                        new_values[field_name] = widget.get('1.0', 'end-1c').strip()
                    else:
                        new_values[field_name] = widget.get().strip()
                
                # Update ID3 tags
                audio = MP3(file_path, ID3=ID3)
                if audio.tags is None:
                    audio.add_tags()
                
                # Set each field
                if new_values['title']:
                    audio.tags['TIT2'] = TIT2(encoding=3, text=new_values['title'])
                elif 'TIT2' in audio.tags:
                    del audio.tags['TIT2']
                
                if new_values['artist']:
                    audio.tags['TPE1'] = TPE1(encoding=3, text=new_values['artist'])
                elif 'TPE1' in audio.tags:
                    del audio.tags['TPE1']
                
                if new_values['album']:
                    audio.tags['TALB'] = TALB(encoding=3, text=new_values['album'])
                elif 'TALB' in audio.tags:
                    del audio.tags['TALB']
                
                if new_values['year']:
                    audio.tags['TDRC'] = TDRC(encoding=3, text=new_values['year'])
                elif 'TDRC' in audio.tags:
                    del audio.tags['TDRC']
                
                if new_values['track']:
                    audio.tags['TRCK'] = TRCK(encoding=3, text=new_values['track'])
                elif 'TRCK' in audio.tags:
                    del audio.tags['TRCK']
                
                if new_values['genre']:
                    audio.tags['TCON'] = TCON(encoding=3, text=new_values['genre'])
                elif 'TCON' in audio.tags:
                    del audio.tags['TCON']
                
                if new_values['album_artist']:
                    audio.tags['TPE2'] = TPE2(encoding=3, text=new_values['album_artist'])
                elif 'TPE2' in audio.tags:
                    del audio.tags['TPE2']
                
                if new_values['comment']:
                    audio.tags['COMM::eng'] = COMM(encoding=3, lang='eng', 
                                                   desc='', text=new_values['comment'])
                elif 'COMM::eng' in audio.tags:
                    del audio.tags['COMM::eng']
                
                # Save the file
                audio.save()
                
                # Update artist and album in database
                artist_value = new_values['artist'] if new_values['artist'] else None
                album_value = new_values['album'] if new_values['album'] else None
                self.cursor.execute(
                    "UPDATE songs SET artist = ?, album = ? WHERE id = ?",
                    (artist_value, album_value, song_id)
                )
                self.conn.commit()
                
                # Refresh the library list to show updated values
                self.update_library_list()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save ID3 tags: {str(e)}")
        
        ttk.Button(button_container, text="Save", command=save_metadata, 
                  style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        def save_and_break(event=None):
            save_metadata()
            return "break"

        for entry in entries:
            entry.bind('<Return>', save_and_break)

        # Auto-focus the title field
        def focus_title():
            title_entry = None
            for field_name, widget in fields.items():
                if field_name == 'title' and isinstance(widget, tk.StringVar):
                    # Find the entry widget associated with this StringVar
                    for child in scrollable_frame.winfo_children():
                        if isinstance(child, ttk.Entry) and child.cget('textvariable') == str(widget):
                            title_entry = child
                            break
                    break
            
            if title_entry:
                title_entry.focus_set()
                title_entry.select_range(0, tk.END)
                title_entry.icursor(tk.END)
        
        # Call after dialog is fully rendered
        dialog.after(10, focus_title)

        # Bind Escape key to cancel
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def copy_file_path(self):
        """Copy the full path of the selected file to clipboard"""
        selection = self.library_tree.selection()
        if not selection:
            return
        
        item = self.library_tree.item(selection[0])
        song_id = item['text']
        
        # Get the file path from database
        self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (song_id,))
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Error", "Song not found in database")
            return
        
        file_path = Path(self.music_root) / row[0]
        
        if not file_path.exists():
            messagebox.showerror("Error", f"File not found: {file_path}")
            return
        
        # Copy to clipboard
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(file_path))
            self.root.update()  # Keep the clipboard content after window closes
            
            # Show a brief confirmation in the status area
            original_text = self.now_playing_label.cget("text")
            self.now_playing_label.config(text="✓ Path copied to clipboard")
            self.root.after(2000, lambda: self.now_playing_label.config(text=original_text))
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy path: {str(e)}")
    
    def delete_file(self):
        """Delete the selected file"""
        selection = self.library_tree.selection()
        if not selection:
            return
        
        item = self.library_tree.item(selection[0])
        song_id = item['text']
        filename = item['values'][0]
        
        # Get the file path from database
        self.cursor.execute("SELECT relative_path FROM songs WHERE id = ?", (song_id,))
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Error", "Song not found in database")
            return
        
        file_path = Path(self.music_root) / row[0]
        
        # Confirm deletion
        if not messagebox.askyesno("Confirm Delete", 
                                   f"Are you sure you want to delete this file?\n\n{filename}\n\n"
                                   "This action cannot be undone!"):
            return
        
        try:
            # Delete the file
            if file_path.exists():
                file_path.unlink()
            
            # Remove from database
            self.cursor.execute("DELETE FROM songs WHERE id = ?", (song_id,))
            self.conn.commit()
            
            # Update the display
            self.update_library_list()
            messagebox.showinfo("Success", f"File deleted: {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete file: {str(e)}")
            
    def get_existing_tags(self):
        """Get all existing tags from the database"""
        if not self.conn:
            return []
        
        try:
            self.cursor.execute("SELECT tags FROM songs WHERE tags IS NOT NULL AND tags != ''")
            all_tags = set()
            for row in self.cursor.fetchall():
                if row[0]:
                    # Split tags by comma and clean them
                    tags = [tag.strip() for tag in row[0].split(',') if tag.strip()]
                    all_tags.update(tags)
            return sorted(list(all_tags))
        except:
            return []
    
    def update_tags(self):
        """Update tags for selected song"""
        # Get the currently selected song if current_edit_id is not set
        if not hasattr(self, 'current_edit_id') or self.current_edit_id is None:
            selection = self.library_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a song first")
                return
            item = self.library_tree.item(selection[0])
            self.current_edit_id = item['text']
            
        new_tags = self.tag_edit_var.get()
        self.cursor.execute("UPDATE songs SET tags = ? WHERE id = ?", 
                           (new_tags, self.current_edit_id))
        self.conn.commit()
        
        # Store the current song ID to restore selection after update
        updated_song_id = self.current_edit_id
        
        # Update the library list
        self.update_library_list()
        
        # Restore the selection to the updated song
        for item in self.library_tree.get_children():
            item_data = self.library_tree.item(item)
            if item_data['text'] == str(updated_song_id):
                self.library_tree.selection_set(item)
                self.library_tree.see(item)  # Scroll to the item if needed
                break
            
    def on_tag_entry_change(self, *args):
        """Handle changes in the tag entry field"""
        current_text = self.tag_edit_var.get()
        
        if not current_text:
            self.hide_autocomplete()
            return
        
        # Get current cursor position to find the tag being edited
        cursor_pos = self.tag_entry.index(tk.INSERT)
        
        # Find the start of the current tag (go back to find comma or start)
        text_before_cursor = current_text[:cursor_pos]
        last_comma = text_before_cursor.rfind(',')
        
        if last_comma >= 0:
            current_tag_start = last_comma + 1
            current_tag = text_before_cursor[current_tag_start:].strip()
        else:
            current_tag = text_before_cursor.strip()
        
        if not current_tag:
            self.hide_autocomplete()
            return
        
        # Get matching tags
        all_tags = self.get_existing_tags()
        matching_tags = [tag for tag in all_tags if current_tag.lower() in tag.lower()]
        
        if matching_tags:
            self.show_autocomplete(matching_tags)
        else:
            self.hide_autocomplete()
    
    def show_autocomplete(self, tags):
        """Show autocomplete panel with matching tags"""
        # Clear existing suggestions
        self.autocomplete_listbox.delete(0, tk.END)
        
        # Add matching tags
        for tag in tags[:10]:  # Limit to 10 suggestions
            self.autocomplete_listbox.insert(tk.END, tag)
        
        # Calculate listbox height (max 6 items, but fewer if less matches)
        listbox_height = min(6, len(tags))
        self.autocomplete_listbox.config(height=listbox_height)
        
        # Show autocomplete frame at the bottom of the parent (below songs list)
        self.autocomplete_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Select first item
        if tags:
            self.autocomplete_listbox.selection_set(0)
            self.autocomplete_listbox.see(0)
    
    def hide_autocomplete(self, *args):
        """Hide autocomplete panel"""
        self.autocomplete_frame.pack_forget()
    
    def on_tag_key_release(self, event):
        """Handle key release events in tag entry"""
        # Don't process navigation keys
        if event.keysym in ['Up', 'Down', 'Return', 'Escape', 'Tab']:
            return
        
        # Update suggestions
        self.on_tag_entry_change()
    
    def on_tag_enter(self, event):
        """Handle Enter key in tag entry"""
        if self.autocomplete_frame.winfo_ismapped():
            # If suggestions are visible, apply the selected one
            selection = self.autocomplete_listbox.curselection()
            if selection:
                self.apply_autocomplete_suggestion(self.autocomplete_listbox.get(selection[0]))
            else:
                self.hide_autocomplete()
        else:
            # If no suggestions visible, hide them just in case
            self.hide_autocomplete()
        return "break"  # Prevent default behavior
    
    def on_tag_entry_focus_out(self, event):
        """Handle focus out event for tag entry"""
        # Hide suggestions when focus is lost (with a small delay to allow clicking on listbox)
        self.root.after(200, self.hide_autocomplete)
    
    def select_autocomplete_suggestion(self, direction):
        """Select next/previous suggestion in autocomplete listbox"""
        if not self.autocomplete_frame.winfo_ismapped():
            return
        
        selection = self.autocomplete_listbox.curselection()
        if selection:
            current_index = selection[0]
            new_index = current_index + direction
            
            if 0 <= new_index < self.autocomplete_listbox.size():
                self.autocomplete_listbox.selection_clear(0, tk.END)
                self.autocomplete_listbox.selection_set(new_index)
                self.autocomplete_listbox.see(new_index)
        elif direction > 0 and self.autocomplete_listbox.size() > 0:
            # Select first item if going down and nothing is selected
            self.autocomplete_listbox.selection_set(0)
            self.autocomplete_listbox.see(0)
    
    def on_autocomplete_listbox_select(self, event):
        """Handle selection in autocomplete listbox"""
        selection = self.autocomplete_listbox.curselection()
        if selection:
            self.apply_autocomplete_suggestion(self.autocomplete_listbox.get(selection[0]))
    
    def on_autocomplete_listbox_double_click(self, event):
        """Handle double click in autocomplete listbox"""
        selection = self.autocomplete_listbox.curselection()
        if selection:
            self.apply_autocomplete_suggestion(self.autocomplete_listbox.get(selection[0]))
    
    def apply_autocomplete_suggestion(self, selected_tag):
        """Apply selected tag suggestion"""
        current_text = self.tag_edit_var.get()
        cursor_pos = self.tag_entry.index(tk.INSERT)
        
        # Find the start of the current tag
        text_before_cursor = current_text[:cursor_pos]
        last_comma = text_before_cursor.rfind(',')
        
        if last_comma >= 0:
            # Replace the current tag
            new_text = (current_text[:last_comma + 1] + ' ' + selected_tag + 
                       current_text[cursor_pos:])
        else:
            # Replace the entire text
            new_text = selected_tag + current_text[cursor_pos:]
        
        # Update the entry field
        self.tag_edit_var.set(new_text.strip())
        
        # Position cursor after the inserted tag
        new_cursor_pos = len(new_text.strip()) - len(current_text[cursor_pos:])
        self.tag_entry.icursor(new_cursor_pos)
        
        # Hide suggestions immediately
        self.hide_autocomplete()
    
    def bulk_edit_tags_dialog(self):
        """Show dialog for bulk editing tags of selected songs"""
        selected_items = self.library_tree.selection()
        
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select songs to bulk edit tags")
            return
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Bulk Edit Tags ({len(selected_items)} songs)")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=self.colors['bg'])
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Title
        ttk.Label(dialog, text=f"Bulk Edit Tags for {len(selected_items)} songs", 
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=15)
        
        # Main content frame
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill="both", expand=True, padx=20)
        
        # Tag operation selection
        operation_frame = ttk.LabelFrame(main_frame, text="Tag Operation", padding="10")
        operation_frame.pack(fill=tk.X, pady=10)
        
        operation_var = tk.StringVar(value="add")
        ttk.Radiobutton(operation_frame, text="Add tags", variable=operation_var, 
                       value="add").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(operation_frame, text="Replace tags", variable=operation_var, 
                       value="replace").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(operation_frame, text="Remove tags", variable=operation_var, 
                       value="remove").pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(operation_frame, text="Clear all tags", variable=operation_var, 
                       value="clear").pack(anchor=tk.W, pady=2)
        
        # Tags input
        tags_frame = ttk.LabelFrame(main_frame, text="Tags", padding="10")
        tags_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(tags_frame, text="Enter tags (comma-separated):").pack(anchor=tk.W)
        tags_var = tk.StringVar()
        tags_entry = ttk.Entry(tags_frame, textvariable=tags_var, width=60)
        tags_entry.pack(fill=tk.X, pady=5)
        
        # Show existing tags summary
        existing_tags = set()
        for item_id in selected_items:
            item = self.library_tree.item(item_id)
            tags = item['values'][4]
            if tags:
                existing_tags.update(tag.strip() for tag in tags.split(',') if tag.strip())
        
        if existing_tags:
            summary_text = f"Current tags in selection: {', '.join(sorted(existing_tags))}"
            ttk.Label(tags_frame, text=summary_text, wraplength=550, 
                     foreground=self.colors['accent']).pack(anchor=tk.W, pady=5)
        
        # Preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        preview_text = tk.Text(preview_frame, height=8, wrap=tk.WORD,
                              bg=self.colors['entry_bg'],
                              fg=self.colors['fg'],
                              insertbackground=self.colors['fg'],
                              highlightthickness=1,
                              highlightbackground=self.colors['border'],
                              highlightcolor=self.colors['accent'])
        preview_scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", 
                                        command=preview_text.yview)
        preview_text.configure(yscrollcommand=preview_scrollbar.set)
        
        preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def update_preview(*args):
            """Update preview based on operation and tags"""
            operation = operation_var.get()
            new_tags = [tag.strip() for tag in tags_var.get().split(',') if tag.strip()]
            
            preview_content = []
            for item_id in selected_items:
                item = self.library_tree.item(item_id)
                filename = item['values'][0]
                current_tags = [tag.strip() for tag in item['values'][4].split(',') if tag.strip()] if item['values'][4] else []
                
                if operation == "add":
                    final_tags = current_tags + [tag for tag in new_tags if tag not in current_tags]
                elif operation == "replace":
                    final_tags = new_tags
                elif operation == "remove":
                    final_tags = [tag for tag in current_tags if tag not in new_tags]
                elif operation == "clear":
                    final_tags = []
                else:
                    final_tags = current_tags
                
                preview_content.append(f"{filename}: {', '.join(final_tags) if final_tags else '(no tags)'}")
            
            preview_text.delete('1.0', tk.END)
            preview_text.insert('1.0', '\n'.join(preview_content))
        
        # Bind preview update
        operation_var.trace('w', update_preview)
        tags_var.trace('w', update_preview)
        
        # Initial preview
        update_preview()
        
        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side="bottom", fill="x", pady=15)
        
        def apply_bulk_tags():
            """Apply bulk tag changes"""
            operation = operation_var.get()
            new_tags = [tag.strip() for tag in tags_var.get().split(',') if tag.strip()]
            
            updated = 0
            errors = []
            
            for item_id in selected_items:
                try:
                    item = self.library_tree.item(item_id)
                    song_id = item['text']
                    current_tags = [tag.strip() for tag in item['values'][4].split(',') if tag.strip()] if item['values'][4] else []
                    
                    if operation == "add":
                        final_tags = current_tags + [tag for tag in new_tags if tag not in current_tags]
                    elif operation == "replace":
                        final_tags = new_tags
                    elif operation == "remove":
                        final_tags = [tag for tag in current_tags if tag not in new_tags]
                    elif operation == "clear":
                        final_tags = []
                    else:
                        final_tags = current_tags
                    
                    # Update database
                    final_tags_str = ', '.join(final_tags) if final_tags else ''
                    self.cursor.execute("UPDATE songs SET tags = ? WHERE id = ?", 
                                       (final_tags_str, song_id))
                    updated += 1
                    
                except Exception as e:
                    errors.append(f"Error updating {item['values'][0]}: {str(e)}")
            
            if updated > 0:
                self.conn.commit()
                self.update_library_list()
            
            # Show result
            if errors:
                msg = f"Updated {updated} songs with {len(errors)} errors:\n\n" + '\n'.join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... and {len(errors) - 5} more errors"
                messagebox.showwarning("Partial Success", msg)
            else:
                messagebox.showinfo("Success", f"Successfully updated tags for {updated} songs")
            
            dialog.destroy()
        
        # Center buttons
        button_container = ttk.Frame(button_frame)
        button_container.pack()
        
        ttk.Button(button_container, text="Apply", command=apply_bulk_tags, 
                  style='Accent.TButton', width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_container, text="Cancel", command=dialog.destroy, 
                  width=15).pack(side=tk.LEFT, padx=5)
        
        # Focus on tags entry
        tags_entry.focus_set()
        
        # Bind Enter key to apply
        dialog.bind('<Return>', lambda e: apply_bulk_tags())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

def main():
    root = tk.Tk()
    app = MusicPlaylistManager(root)
    root.mainloop()

if __name__ == "__main__":
    main()
