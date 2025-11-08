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
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, TCON, TPE2, COMM
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
        
        # Bind Ctrl+Q to quit application
        self.root.bind('<Control-q>', lambda e: self.quit_app())
        
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
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                self.music_root = config.get('music_root')
                
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
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=5)
        
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
        
        # Bind Space bar to play/stop
        # self.root.bind('<space>', lambda e: self.toggle_playback())
        
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
        self.context_menu.add_command(label="Open in File Explorer", command=self.open_in_explorer)
        self.context_menu.add_command(label="Delete File", command=self.delete_file)
        
        # Edit frame
        edit_frame = ttk.Frame(parent, padding="10")
        edit_frame.pack(fill=tk.X)
        
        ttk.Label(edit_frame, text="Selected song tags:").pack(side=tk.LEFT)
        self.tag_edit_var = tk.StringVar()
        self.tag_entry = ttk.Entry(edit_frame, textvariable=self.tag_edit_var, width=50)
        tag_edit_entry = self.tag_entry
        tag_edit_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(edit_frame, text="Update Tags", 
                   command=self.update_tags).pack(side=tk.LEFT)
    
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
                if file_path.suffix.lower() == '.mp3' and MUTAGEN_AVAILABLE:
                    audio = MP3(file_path)
                    self.song_length = audio.info.length
                else:
                    # For non-MP3 files, we can't easily get the length
                    # Set to 0 to disable seeking
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
                    
                    copied = 0
                    for song in songs:
                        source = Path(self.music_root) / song['relative_path']
                        destination_file = playlist_dir / song['filename']
                        try:
                            shutil.copy2(source, destination_file)
                            copied += 1
                        except Exception as e:
                            print(f"Error copying {song['filename']}: {e}")
                    
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
            
            # Try to read ID3 metadata for MP3 files
            artist = ""
            album = ""
            if file_path.suffix.lower() == '.mp3' and MUTAGEN_AVAILABLE:
                try:
                    audio = MP3(file_path, ID3=ID3)
                    if audio.tags:
                        if 'TPE1' in audio.tags:
                            artist = str(audio.tags['TPE1'])
                        if 'TALB' in audio.tags:
                            album = str(audio.tags['TALB'])
                except:
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
                messagebox.showinfo("Success", f"File renamed to: {new_filename}")
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
                fields[field_name] = var
        
        scrollable_frame.columnconfigure(1, weight=1)

        # Button frame
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side="bottom", fill="x", pady=10)

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
        
        ttk.Button(button_frame, text="Save", command=save_metadata, 
                  style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Bind Escape key to cancel
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    def open_in_explorer(self):
        """Open the selected file in the system file explorer"""
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
        
        # Open file explorer with the file selected
        try:
            if sys.platform == 'win32':
                os.startfile(file_path.parent)
            elif sys.platform == 'darwin':  # macOS
                os.system(f'open "{file_path.parent}"')
            else:  # Linux
                os.system(f'xdg-open "{file_path.parent}"')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file explorer: {str(e)}")
    
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
            
    def update_tags(self):
        """Update tags for selected song"""
        if not hasattr(self, 'current_edit_id'):
            messagebox.showwarning("Warning", "Please select a song first")
            return
            
        new_tags = self.tag_edit_var.get()
        self.cursor.execute("UPDATE songs SET tags = ? WHERE id = ?", 
                           (new_tags, self.current_edit_id))
        self.conn.commit()
        self.update_library_list()
            
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
