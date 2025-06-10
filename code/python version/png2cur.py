# Import Area

import tkinter as tk
from tkinter import filedialog, Label, Entry, Button, Listbox, Scrollbar, IntVar, Checkbutton, messagebox
from PIL import Image, ImageSequence
import struct

# Class Area

class staticCUR:
    def __init__(self, image_data, hotspot_x, hotspot_y):
        self.image_data = image_data
        self.hotspot_x = hotspot_x
        self.hotspot_y = hotspot_y

    def get_cur_data(self):
        if isinstance(self.image_data, dict) and 'image_data' in self.image_data:
            image = self.image_data['image_data'].convert("RGBA")
            width = self.image_data['width']
            height = self.image_data['height']
        elif isinstance(self.image_data, Image.Image):
            image = self.image_data.convert("RGBA")
            width, height = image.size
        else:
            raise ValueError("Invalid image_data format: Expected Pillow Image or a dictionary with 'image_data' (Pillow Image).")

        pixels = list(image.getdata())

        # --- XOR Mask (Color data + Alpha) ---
        # Stored BGRA, bottom-up
        bitmap_data = bytearray()
        for y in reversed(range(height)): # Pixels are stored bottom-up
            for x in range(width):
                r, g, b, a = pixels[y * width + x]
                bitmap_data.extend([b, g, r, a]) # BGRA order

        # --- AND Mask (1-bit transparency mask) ---
        # Stored 1 bit per pixel, padded to 32-bit boundary per row, bottom-up
        mask_bytes = bytearray()
        
        # Calculate row byte width for the 1-bit mask, padded to 4-byte boundary (32 bits)
        # Each row of the 1-bit mask is (width + 7) // 8 bytes long, then padded to a multiple of 4 bytes.
        row_mask_byte_width = ((width + 31) // 32) * 4 

        for y in reversed(range(height)): # Mask is also typically bottom-up
            row_bits = []
            for x in range(width):
                # For 32-bit cursors, the AND mask usually indicates full transparency (1)
                # for pixels with alpha 0, and full opacity (0) for others.
                # This ensures backward compatibility if alpha channel is ignored,
                # though modern Windows mostly relies on alpha for 32-bit.
                alpha = pixels[y * width + x][3]
                # If alpha is 0 (fully transparent), set mask bit to 1.
                # Otherwise (opaque or semi-transparent), set mask bit to 0.
                row_bits.append(1 if alpha == 0 else 0)

            # Pack bits into bytes
            byte_index = 0
            current_byte = 0
            for bit in row_bits:
                current_byte = (current_byte << 1) | bit
                byte_index += 1
                if byte_index == 8: # If a full byte is accumulated
                    mask_bytes.append(current_byte)
                    current_byte = 0
                    byte_index = 0
            # Append any remaining bits in the last partial byte
            if byte_index > 0:
                current_byte = current_byte << (8 - byte_index) # Pad with zeros to fill byte
                mask_bytes.append(current_byte)

            # Pad the current row to the required 4-byte boundary
            while len(mask_bytes) % row_mask_byte_width != 0:
                mask_bytes.append(0)

        # --- BITMAPINFOHEADER ---
        # biHeight MUST be 2 * image height for cursors, even for 32-bit.
        bih = struct.pack(
            "<IIIHHIIIIII",
            40,         # biSize (size of BITMAPINFOHEADER)
            width,      # biWidth
            height * 2, # biHeight (CRITICAL: height * 2 for cursors)
            1,          # biPlanes
            32,         # biBitCount (32-bit RGBA)
            0,          # biCompression (BI_RGB)
            len(bitmap_data) + len(mask_bytes), # biSizeImage (total raw image data size: XOR + AND masks)
            0, 0, 0, 0  # biXPelsPerMeter, biYPelsPerMeter, biClrUsed, biClrImportant
        )

        # --- IconDirEntry (for single CUR file) ---
        # The offset points to the start of the BITMAPINFOHEADER.
        image_offset = 6 + 16 # Header (6 bytes) + IconDirEntry (16 bytes)
        total_image_data_size = len(bih) + len(bitmap_data) + len(mask_bytes)

        de = struct.pack(
            "<BBBBHHII",
            width if width < 256 else 0,   # bWidth (0 if 256)
            height if height < 256 else 0, # bHeight (0 if 256)
            0,                             # bColors (0 for true color)
            0,                             # bReserved (must be 0)
            self.hotspot_x,                # wXHotspot
            self.hotspot_y,                # wYHotspot
            total_image_data_size,         # dwBytesInRes (size of BITMAPINFOHEADER + XOR data + AND data)
            image_offset                   # dwImageOffset (offset from start of file to BITMAPINFOHEADER)
        )

        # --- IconDir Header (for single CUR file) ---
        header = struct.pack(
            "<HHH",
            0,  # idReserved (must be 0)
            2,  # idType (2 for CUR)
            1   # idCount (number of images in file, always 1 for .cur)
        )

        return header + de + bih + bytes(bitmap_data) + bytes(mask_bytes)

class animatedANI:
    def __init__(self, frames_data, hotspot_x, hotspot_y):
        self.frames_data = frames_data
        self.hotspot_x = hotspot_x
        self.hotspot_y = hotspot_y

    def get_ani_data(self):
        num_frames = len(self.frames_data)
        chunked_cur_data_list = []
        durations_in_jiffies = []
        # Use dimensions from the first frame for anih header.
        # All frames in an ANI should ideally have the same dimensions.
        width = self.frames_data[0]["width"]
        height = self.frames_data[0]["height"]

        def make_chunk(chunk_id: bytes, chunk_data: bytes) -> bytes:
            padded_data = chunk_data + (b'\x00' if len(chunk_data) % 2 == 1 else b'')
            return chunk_id + struct.pack('<I', len(padded_data)) + padded_data

        for frame_info in self.frames_data:
            cur_obj = staticCUR(frame_info, self.hotspot_x, self.hotspot_y)
            raw_cur_data = cur_obj.get_cur_data()
            icon_chunk = make_chunk(b'icon', raw_cur_data)
            chunked_cur_data_list.append(icon_chunk)
            
            delay_ms = max(1, frame_info.get('delay', 100))
            jiffies = round(delay_ms / (1000 / 60))
            durations_in_jiffies.append(max(1, int(jiffies)))

        # --- anih chunk ---
        flags = 0x3 if num_frames > 1 else 0x1 # AF_DONTCAREANIMATION and AF_ANIMATED
        anih_payload = struct.pack(
            "<9I",
            36, # cbSizeof (size of anih chunk data in bytes)
            num_frames, # cFrames
            num_frames, # cSteps (number of frames to animate over, usually same as cFrames)
            width,      # cx (width of the cursor)
            height,     # cy (height of the cursor)
            32,         # cBitCount (bits per pixel, 32 for RGBA)
            1,          # cPlanes (always 1 for cursors)
            0,          # jifRate (default frame rate in jiffies, 0 for default from 'rate' chunk)
            flags       # fl (flags, e.g., AF_ANIMATED)
        )
        anih_chunk = make_chunk(b'anih', anih_payload)

        # --- rate chunk ---
        rate_chunk = make_chunk(b'rate', struct.pack("<{}I".format(num_frames), *durations_in_jiffies))
        
        # --- seq chunk (optional) ---
        seq_chunk = make_chunk(b'seq ', struct.pack("<{}I".format(num_frames), *range(num_frames)))

        # --- LIST 'fram' chunk, with all frames ---
        frames_blob = b''.join(chunked_cur_data_list)
        fram_list_data = b'fram' + frames_blob
        fram_list_chunk = b'LIST' + struct.pack('<I', len(fram_list_data)) + fram_list_data

        # --- Build the main RIFF 'ACON' chunk ---
        acon_content = anih_chunk + rate_chunk + seq_chunk + fram_list_chunk
        
        riff_payload_size = len(b'ACON') + len(acon_content)
        riff_header = b'RIFF' + struct.pack('<I', riff_payload_size) + b'ACON'
        
        return riff_header + acon_content

class staticPNG:
    def __init__(self):
        pass

class animatedPNG:
    def __init__(self):
        pass

class Converter:
    def __init__(self, master):
        self.master = master
        master.title("PNG to CUR Converter")

        self.input_label = Label(master, text="Select PNG File(s):")
        self.input_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.file_path = tk.StringVar()
        self.file_entry = Entry(master, textvariable=self.file_path, width=40)
        self.file_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.browse_button = Button(master, text="Browse", command=self.browse_file)
        self.browse_button.grid(row=0, column=2, padx=5, pady=5)

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

        self.hotspot_label = Label(master, text="Hotspot (X, Y):")
        self.hotspot_label.grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.hotspot_x_label = Label(master, text="X:")
        self.hotspot_x_label.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.hotspot_x_entry = Entry(master, width=5)
        self.hotspot_x_entry.grid(row=3, column=1, padx=(25, 45), pady=5)

        self.hotspot_y_label = Label(master, text="Y:")
        self.hotspot_y_label.grid(row=3, column=2, sticky="w", padx=5, pady=5)
        self.hotspot_y_entry = Entry(master, width=5)
        self.hotspot_y_entry.grid(row=3, column=2, padx=(20, 5), pady=5)

        self.hotspot_x_entry.insert(0, "0")
        self.hotspot_y_entry.insert(0, "0")

        self.transparency_label = Label(master, text="Transparency:")
        self.transparency_label.grid(row=4, column=0, sticky="w", padx=5, pady=5)

        self.binary_transparency_var = IntVar()
        self.binary_transparency_check = Checkbutton(master, text="Binary Transparency (via mask)", variable=self.binary_transparency_var)
        self.binary_transparency_check.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        self.binary_transparency_check.config(state=tk.DISABLED)

        self.variable_transparency_var = IntVar()
        self.variable_transparency_check = Checkbutton(master, text="Variable Transparency (32-bit RGBA)", variable=self.variable_transparency_var)
        self.variable_transparency_check.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        self.variable_transparency_check.select()
        self.variable_transparency_check.config(state=tk.DISABLED)

        self.color_label = Label(master, text="Color Format:")
        self.color_label.grid(row=6, column=0, sticky="w", padx=5, pady=5)

        self.color_format_label_display = Label(master, text="32-bit RGBA")
        self.color_format_label_display.grid(row=6, column=1, sticky="w", padx=5, pady=5)

        self.convert_button = Button(master, text="Convert to CUR/ANI", command=self.convert_png_to_cur)
        self.convert_button.grid(row=7, column=1, pady=10)
        self.frames_data = []

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

            if getattr(img, "is_animated", False):
                print("Animated PNG detected.")
                for i, frame in enumerate(ImageSequence.Iterator(img)):
                    f_rgba = frame.convert("RGBA")
                    delay = frame.info.get("duration", 100)
                    self.frames_data.append({
                        "image_data": f_rgba,
                        "delay": delay,
                        "width": f_rgba.width,
                        "height": f_rgba.height
                    })
                    self.frames_listbox.insert(
                        tk.END,
                        f"Frame {i+1} (Delay: {delay} ms, Size: {f_rgba.width}x{f_rgba.height})"
                    )
            else:
                print("Static PNG detected.")
                f_rgba = img.convert("RGBA")
                self.frames_data.append({
                    "image_data": f_rgba,
                    "delay": 0,
                    "width": f_rgba.width,
                    "height": f_rgba.height
                })
                self.frames_listbox.insert(tk.END, f"Single Frame (Size: {f_rgba.width}x{f_rgba.height})")
            
            if self.frames_data:
                first_frame_width = self.frames_data[0]['width']
                first_frame_height = self.frames_data[0]['height']
                default_hotspot_x = first_frame_width // 2
                default_hotspot_y = first_frame_height // 2
                self.hotspot_x_entry.delete(0, tk.END)
                self.hotspot_x_entry.insert(0, str(default_hotspot_x))
                self.hotspot_y_entry.delete(0, tk.END)
                self.hotspot_y_entry.insert(0, str(default_hotspot_y))

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
                        self.frames_listbox.delete(index)
                        self.frames_listbox.insert(index, f"Frame {index+1} (Delay: {delay:.2f} ms, Size: {self.frames_data[index].get('width', '?')}x{self.frames_data[index].get('height', '?')})")
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

        default_ext = ".ani" if len(self.frames_data) > 1 else ".cur"
        file_types = (("Animated Cursor files", "*.ani"), ("Cursor files", "*.cur"), ("All files", "*.*"))
        dialog_title = "Save as Animated Cursor file" if len(self.frames_data) > 1 else "Save as Cursor file"

        output_filepath = filedialog.asksaveasfilename(
            defaultextension=default_ext,
            filetypes=file_types,
            title=dialog_title
        )
        if not output_filepath:
            return

        if len(self.frames_data) == 1:
            try:
                cur_obj = staticCUR(self.frames_data[0], hotspot_x, hotspot_y)
                cur_data = cur_obj.get_cur_data()
                with open(output_filepath, 'wb') as f:
                    f.write(cur_data)
                messagebox.showinfo("Info", f"Static cursor saved to {output_filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Error creating static CUR file: {e}")
        else:
            try:
                ani_obj = animatedANI(self.frames_data, hotspot_x, hotspot_y)
                ani_data = ani_obj.get_ani_data()
                with open(output_filepath, 'wb') as f:
                    f.write(ani_data)
                messagebox.showinfo("Info", f"Animated cursor saved to {output_filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Error creating animated ANI file: {e}")

# Launch Area

root = tk.Tk()
converter = Converter(root)
root.mainloop()
