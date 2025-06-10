import tkinter as tk
from tkinter import filedialog, Label, Entry, Button, Listbox, Scrollbar, IntVar, Checkbutton, messagebox
from PIL import Image, ImageSequence
import struct

# Class Area

class staticCur:
    image_data = 0
    hotspot_x = 0
    hotspot_y = 0

    def __init__(self, image_data, hotspot_x, hotspot_y):
        self.image_data = image_data
        self.hotspot_x = hotspot_x
        self.hotspot_y = hotspot_y

    def setup(self):
        if isinstance(self.image_data, dict) and 'image_data' in self.image_data:
            image = self.image_data['image_data'].convert("RGBA")
            width = self.image_data['width']
            height = self.image_data['height']
            pixels = list(image.getdata())
        elif isinstance(self.image_data, Image.Image):
            image = self.image_data.convert("RGBA")
            width, height = image.size
            pixels = list(image.getdata())
        else:
            raise ValueError("Invalid image_data format")

        # --- Bitmap Data (32-bit BGRA) ---
        bitmap_data = bytearray()
        mask_bits = []  # 1=transparent, 0=opaque
        for y in reversed(range(height)):    # bottom-up!
            for x in range(width):
                r, g, b, a = pixels[y * width + x]
                bitmap_data.extend([b, g, r, a])
                mask_bits.append(0 if a > 0 else 1)

        # --- AND mask (1 bit per pixel per row, pad rows to DWORD) ---
        # ...rest of setup()...
        mask_bytes = bytearray()
        row_bytes = ((width + 31) // 32) * 4
        for y in range(height):
            byte = 0
            bits = 0
            row = []
            for x in range(width):
                idx = y * width + x
                bit = mask_bits[idx]
                byte = (byte << 1) | bit
                bits += 1
                if bits == 8:
                    row.append(byte)
                    byte = 0
                    bits = 0
            if bits > 0:
                byte = byte << (8 - bits)
                row.append(byte)
            while len(row) < row_bytes:
                row.append(0)
            mask_bytes.extend(row)

        # --- BITMAPINFOHEADER (40 bytes), critical: height*2! ---
        bih = struct.pack(
            "<IIIHHIIIIII",
            40,             # biSize
            width,          # biWidth
            height * 2,     # biHeight **MUST be double**
            1,              # biPlanes
            32,             # biBitCount
            0,              # biCompression
            len(bitmap_data) + len(mask_bytes),
            0, 0, 0, 0
        )

        # --- Directory Entry (16 bytes) ---
        de = struct.pack(
            "<BBBBHHII",
            width if width < 256 else 0,
            height if height < 256 else 0,
            0, 0, self.hotspot_x, self.hotspot_y,
            len(bih) + len(bitmap_data) + len(mask_bytes),
            6 + 16
        )

        header = struct.pack("<HHH", 0, 2, 1)

        return header + de + bih + bytes(bitmap_data) + bytes(mask_bytes)

class dynamicCur:
    image_data = 0
    hotspot_x = 0
    hotspot_y = 0
    def __init__(self, image_data, hotspot_x, hotspot_y):
        pass

class staticPNG:
    def __init__(self):
        pass

class dynamicPNG:
    def __init__(self):
        pass

class PNGtoCURConverter:
    def __init__(self, master):
        self.master = master
        master.title("PNG to CUR Converter")

        # --- Input File Selection ---
        self.input_label = Label(master, text="Select PNG File(s):")
        self.input_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.file_path = tk.StringVar()
        self.file_entry = Entry(master, textvariable=self.file_path, width=40)
        self.file_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.browse_button = Button(master, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=0, column=2, padx=5, pady=5)

        # --- Animated PNG Frames (ListBox with Scrollbar) ---
        self.frames_label = Label(master, text="Frames:")
        self.frames_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.frames_scrollbar = Scrollbar(master)
        self.frames_listbox = Listbox(master, yscrollcommand=self.frames_scrollbar.set, width=40, height=5)
        self.frames_listbox.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.frames_scrollbar.config(command=self.frames_listbox.yview)
        self.frames_scrollbar.grid(row=1, column=2, sticky="ns", pady=5)

        self.delay_label = Label(master, text="Delay (ms):")
        self.delay_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.delay_entry = Entry(master, width=10)
        self.delay_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.add_delay_button = Button(master, text="Add Delay", command=self.add_frame_delay)
        self.add_delay_button.grid(row=2, column=2, padx=5, pady=5)

        # --- Hotspot Setting ---
        self.hotspot_label = Label(master, text="Hotspot (X, Y):")
        self.hotspot_label.grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.hotspot_x_label = Label(master, text="X:")
        self.hotspot_x_label.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.hotspot_x_entry = Entry(master, width=5)
        self.hotspot_x_entry.grid(row=3, column=1, padx=(25, 45), pady=5) # extra left space

        self.hotspot_y_label = Label(master, text="Y:")
        self.hotspot_y_label.grid(row=3, column=2, sticky="w", padx=5, pady=5)
        self.hotspot_y_entry = Entry(master, width=5)
        self.hotspot_y_entry.grid(row=3, column=2, padx=(20, 5), pady=5)

        self.hotspot_x_entry.insert(0, "0")
        self.hotspot_y_entry.insert(0, "0")

        # --- Compression Options ---
        self.compression_label = Label(master, text="Compression:")
        self.compression_label.grid(row=4, column=0, sticky="w", padx=5, pady=5)

        self.binary_transparency_var = IntVar()
        self.binary_transparency_check = Checkbutton(master, text="Binary Transparency", variable=self.binary_transparency_var)
        self.binary_transparency_check.grid(row=4, column=1, sticky="w", padx=5, pady=5)

        self.variable_transparency_var = IntVar()
        self.variable_transparency_check = Checkbutton(master, text="Variable Transparency", variable=self.variable_transparency_var)
        self.variable_transparency_check.grid(row=5, column=1, sticky="w", padx=5, pady=5)

        self.color_label = Label(master, text="Color:")
        self.color_label.grid(row=6, column=0, sticky="w", padx=5, pady=5)

        # Add radio buttons for Black and White, Grayscale, Color later

        # --- Convert Button ---
        self.convert_button = Button(master, text="Convert to CUR", command=self.convert_png_to_cur)
        self.convert_button.grid(row=7, column=1, pady=10)
        self.frames_data = [] # To store frame data and delays
        self.apng_frames_compressed_data = {} # To store compressed data for each frame

    def browse_file(self):
        filepath = filedialog.askopenfilename(
            title="Select PNG File(s)",
            filetypes=(("PNG files", "*.png"), ("All files", "*.*"))
        )
        if filepath:
            self.file_path.set(filepath)
            self.load_png_info(filepath)

    def load_png_info(self, filepath):
        try:
            img = Image.open(filepath)
            self.frames_listbox.delete(0, tk.END)
            self.frames_data = []
            # Handle animated (APNG) or normal PNG
            if getattr(img, "is_animated", False):
                for i, frame in enumerate(ImageSequence.Iterator(img)):
                    f = frame.convert("RGBA")
                    delay = frame.info.get("duration", 100)  # ms
                    self.frames_data.append({
                        "image_data": f,
                        "delay": delay,
                        "width": f.width,
                        "height": f.height
                    })
                    self.frames_listbox.insert(
                        tk.END,
                        f"Frame {i+1} (Delay: {delay} ms, Size: {f.width}x{f.height})"
                    )
            else:
                f = img.convert("RGBA")
                self.frames_data.append({
                    "image_data": f,
                    "delay": 0,
                    "width": f.width,
                    "height": f.height
                })
                self.frames_listbox.insert(tk.END, "Single Frame")
        except Exception as e:
            messagebox.showerror("Error", f"Error loading PNG info:\n{e}")

    def add_frame_delay(self):
        selected_indices = self.frames_listbox.curselection()
        delay_str = self.delay_entry.get()
        try:
            delay = float(delay_str)
            if delay >= 0:
                for index in selected_indices:
                    if 0 <= index < len(self.frames_data):
                        self.frames_data[index]["delay"] = delay
                        current_text = self.frames_listbox.get(index)
                        new_text = f"Frame {index+1} (Delay: {delay:.2f} ms, Size: {self.frames_data[index].get('width', '?')}x{self.frames_data[index].get('height', '?')})"
                        self.frames_listbox.delete(index)
                        self.frames_listbox.insert(index, new_text)
            else:
                messagebox.showerror("Error", "Delay must be a non-negative number.")
        except ValueError:
            messagebox.showerror("Error", "Invalid delay value. Please enter a number.")

    def convert_png_to_cur(self):
        if not self.frames_data:
            messagebox.showerror("Error", "No frames loaded.")
            return

        hotspot_x_str = self.hotspot_x_entry.get()
        hotspot_y_str = self.hotspot_y_entry.get()
        try:
            hotspot_x = int(hotspot_x_str) if hotspot_x_str else 0
            hotspot_y = int(hotspot_y_str) if hotspot_y_str else 0
        except ValueError:
            messagebox.showerror("Error", "Invalid hotspot values. Please enter integers.")
            return

        output_filepath = filedialog.asksaveasfilename(
            defaultextension=".ani",
            filetypes=(("Animated Cursor files", "*.ani"), ("Cursor files", "*.cur"), ("All files", "*.*")),
            title="Save as Animated Cursor file" if len(self.frames_data) > 1 else "Save as Cursor file"
        )
        if not output_filepath:
            return

        if len(self.frames_data) == 1:
            # Static cursor
            try:
                new_cur_data = staticCur(self.frames_data[0], hotspot_x, hotspot_y)
                cur_data = new_cur_data.setup()
                with open(output_filepath, 'wb') as f:
                    f.write(cur_data)
                messagebox.showinfo("Info", f"Static cursor saved to {output_filepath}")
            except ValueError as e:
                messagebox.showerror("Error", str(e))
            except Exception as e:
                messagebox.showerror("Error", f"Error creating static CUR file: {e}")
        else:
            # Animated cursor (.ani)
            try:
                num_frames = len(self.frames_data)
                cur_data_list = []
                durations = []
                width = self.frames_data[0].get('width', 0)
                height = self.frames_data[0].get('height', 0)
                bit_count = 32
                planes = 1

                for frame_info in self.frames_data:
                    new_cur_data = staticCur(frame_info, hotspot_x, hotspot_y)
                    cur_data = new_cur_data.setup()
                    cur_data_list.append(cur_data)
                    durations.append(int(frame_info.get('delay', 100)))  # ms per frame

                def make_chunk(chunk_id: bytes, chunk_data: bytes) -> bytes:
                    if len(chunk_data) % 2 == 1:
                        chunk_data += b'\x00'
                    return chunk_id + struct.pack('<I', len(chunk_data)) + chunk_data

                # --- anih chunk ---
                anih_payload = struct.pack(
                    "<9I",
                    36,              # cbSizeOf
                    num_frames,      # nFrames
                    num_frames,      # nSteps
                    width,
                    height,
                    bit_count,
                    planes,
                    0,               # displayRate
                    0                # flags
                )
                anih_chunk = make_chunk(b'anih', anih_payload)

                # --- rate chunk ---
                rates = [max(1, int(d * 60 / 1000)) for d in durations]
                rate_payload = struct.pack("<{}I".format(num_frames), *rates)
                rate_chunk = make_chunk(b'rate', rate_payload)

                # --- seq chunk ---
                seq_payload = struct.pack("<{}I".format(num_frames), *range(num_frames))
                seq_chunk = make_chunk(b'seq ', seq_payload)

                # --- Frame LIST 'fram' ---
                frames_blob = b''.join(cur_data_list)
                if len(frames_blob) % 2 == 1:
                    frames_blob += b'\x00'
                fram_chunk_size = 4 + len(frames_blob)
                fram_chunk = struct.pack("<4sI4s", b'LIST', fram_chunk_size, b'fram') + frames_blob

                ani_chunks = anih_chunk + rate_chunk + seq_chunk + fram_chunk
                riff_size = 4 + len(ani_chunks)
                riff_header = struct.pack("<4sI4s", b'RIFF', riff_size, b'ACON')
                ani_data = riff_header + ani_chunks

                with open(output_filepath, 'wb') as f:
                    f.write(ani_data)
                messagebox.showinfo("Info", f"Animated cursor saved to {output_filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Error creating animated ANI file: {e}")

# Launch Area

root = tk.Tk()
converter = PNGtoCURConverter(root)
root.mainloop()
