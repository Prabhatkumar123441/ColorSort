import os
import wx
import time
import wx.adv
import threading
import subprocess
import wx.grid as gridlib



st = None
et = None
FO_DELETE = 3
FOF_ALLOWUNDO = 0x00000040
FOF_NOCONFIRMATION = 0x00000010



def get_file_paths_with_os_walk(directory):
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths

def get_file_paths_with_os_scan(directory, required_file_size_start, required_file_size_end=None):
    file_paths = []
    try:
        for entry in os.scandir(directory):
            try:
                # if "Desktop" in entry.path:
                #     print("entry.path--->", entry.path)
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    file_size = os.path.getsize(entry.path)
                    if required_file_size_end:
                        if required_file_size_start <= file_size <= required_file_size_end:
                            file_paths.append((entry.path, file_size))
                    else:
                        if file_size >= required_file_size_start:
                            file_paths.append((entry.path, file_size))
                elif entry.is_dir():
                    file_paths.extend(get_file_paths_with_os_scan(entry.path, required_file_size_start, required_file_size_end))
            except PermissionError as e:
                print(f"Permission denied: {entry.path}")
                print(f"Permission denied: {str(e)}")
            except FileNotFoundError as e:
                print(f"File not found: {entry.path}")
                print(f"File not found: {str(e)}")
            except OSError as e:
                print(f"OS error: {entry.path}")
                print(f"OS error: {str(e)}")
    except PermissionError as e:
        print(f"Permission denied: {str(e)}")
    except FileNotFoundError as e:
        print(f"File not found: {directory}")
        print(f"File not found: {str(e)}")
    except OSError as e:
        print(f"OS error: {directory}")
        print(f"OS error: {str(e)}")
    return file_paths





class SophisticatedProgressBar(wx.Panel):
    def __init__(self, parent, range=100, size=(300, 50), color=wx.Colour(30, 144, 255)):
        super().__init__(parent, size=size)
        self.range = range
        self.value = 0
        self.color = color
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def on_paint(self, event):
        dc = wx.BufferedPaintDC(self)
        rect = self.GetClientRect()
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()

        width = rect.width * self.value // self.range
        gauge_rect = wx.Rect(0, 0, width, rect.height)

        dc.SetBrush(wx.Brush(self.color))
        dc.SetPen(wx.Pen(self.color))
        dc.DrawRectangle(gauge_rect)

        percentage = f"{(self.value / self.range) * 100:.2f}%"
        dc.SetTextForeground(wx.BLACK)
        dc.DrawText(percentage, rect.width // 2 - dc.GetTextExtent(percentage)[0] // 2, rect.height // 2 - dc.GetTextExtent(percentage)[1] // 2)

    def SetValue(self, value):
        if 0 <= value <= self.range:
            self.value = value
            self.Refresh()

    def getvalue(self):
        return self.value



class PanelForGrid(wx.Panel):
    def __init__(self, parent, directory_path, progress_gauge, anim_ctrl, required_file_size_start,required_file_size_end):
        super(PanelForGrid, self).__init__(parent)
        try:
            self.anim_ctrl = anim_ctrl
            self.required_file_size_start = required_file_size_start
            self.required_file_size_end = required_file_size_end

            self.directory_path = directory_path

            self.progress_gauge = progress_gauge

            self.initial_batch_size = 100
            self.batch_size = 500
            self.fully_parsed = None
            self.initial_batch_loaded = False

            self.os_description = wx.GetOsDescription()
            self.SetDoubleBuffered(True)

            self.sleep_obj = threading.Event()

            # self.colors = [
            #     wx.Colour(*wx.ColourDatabase().Find('LIGHT BLUE')),
            #     wx.Colour(*wx.ColourDatabase().Find('GREEN')),
            #     wx.Colour(*wx.ColourDatabase().Find('YELLOW')),
            #     wx.Colour(*wx.ColourDatabase().Find('PINK')),
            #     wx.Colour(*wx.ColourDatabase().Find('CYAN')),
            #     wx.Colour(*wx.ColourDatabase().Find('ORANGE')),
            #     wx.Colour(*wx.ColourDatabase().Find('GREY'))
            # ]

            def hex_to_wx_colour(hex_color):
                """Convert hex color to wx.Colour."""
                return wx.Colour(int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16))

            # Hex color codes 
            hex_colors = [
                '#ffe119', '#42d4f4', '#fabed4', 
                '#469990', '#dcbeff', '#fffac8', '#aaffc3', '#a9a9a9'
            ]

            # Convert hex colors to wx.Colour
            self.colors = [hex_to_wx_colour(color) for color in hex_colors]

            self.current_color_index = 0
            self.file_grid = gridlib.Grid(self)
            self.file_grid.CreateGrid(0, 4)  # Increased the number of columns to 4
            self.file_grid.SetColLabelValue(0, "File Path")
            self.file_grid.SetColLabelValue(1, "File Size (MB)")
            self.file_grid.SetColLabelValue(2, "Explore")
            self.file_grid.SetColLabelValue(3, "Delete")
            # self.file_grid.AutoSizeColumns()
            # self.file_grid.EnableEditing(False)
            self.file_grid.Bind(gridlib.EVT_GRID_CELL_LEFT_CLICK, self.on_grid_cell_click)
            self.file_grid.Bind(wx.EVT_MOUSEWHEEL, self.on_scroll)
            self.file_grid.Bind(wx.EVT_SCROLLWIN, self.on_scroll)
            # self.file_grid.Bind(wx.EVT_SCROLLWIN, self.on_scroll)
            
            self.scroll_timeout = None

            self.Bind(wx.EVT_SIZE, self.on_resize)
            self.set_column_widths()
            self.file_info = None

            self.sleep_obj = threading.Event()
            self.batch = 0


            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(self.file_grid, 1, wx.EXPAND | wx.ALL, 5)
            self.SetSizer(sizer)
            self.directory = None
        except Exception as e:
            print("Error in init of PanelForGrid",str(e))

    def set_column_widths(self):
        try:
            # total_width = self.file_grid.GetSize().GetWidth()
            parent_size = self.GetParent().GetSize()
            total_width = (parent_size.GetWidth()*8.5)//10
            
            col0_width = int(total_width * 0.7)
            col1_width = int(total_width * 0.1)
            col2_width = int(total_width * 0.1)
            col3_width = int(total_width * 0.1)

            self.file_grid.SetColSize(0, col0_width)
            self.file_grid.SetColSize(1, col1_width)
            self.file_grid.SetColSize(2, col2_width)
            self.file_grid.SetColSize(3, col3_width)
        except Exception as e:
            print("Error in set_column_widths",str(e))

    def on_resize(self, event):
        try:
            self.set_column_widths()
            event.Skip()
        except Exception as e:
            print("Error in on_resize",str(e))
    
    def on_scroll(self, event):
        try:
            if FileSizeSorter.stop_flag:
                scrollbar = self.file_grid.GetScrollThumb(wx.VERTICAL)
                scroll_position = self.file_grid.GetScrollPos(wx.VERTICAL)
                scroll_range = self.file_grid.GetScrollRange(wx.VERTICAL)
                if self.file_info and self.initial_batch_loaded:
                    if scroll_position + scrollbar >= scroll_range and not self.fully_parsed:
                        self.OnScrollDebounced(event)
                        print("on_scroll ------")
                
            event.Skip()
        except Exception as e:
            print("Error in on_scroll",str(e))
    
    def OnScrollDebounced(self,event):
        try:
            # print("Scrolling debounced.")
            if self.file_info:
                start = self.batch*self.batch_size + self.initial_batch_size
                end = (self.batch+1)*self.batch_size + self.initial_batch_size  
                
                # thread = threading.Thread(target=self.add_rows_into_filegrid,args=(self.file_info[start:end], FileSizeSorter.lock, self.sleep_obj))
                # thread.start()
                # thread.join()
                batch_size  = end - start
                self.add_rows_into_filegrid(self.file_info[start:end], batch_size, self.sleep_obj)
                self.batch+=1
            event.Skip()
        except Exception as e:
            print("Error in OnScrollDebounced",str(e))
    
    def on_mouse_wheel(self, event):
        try:
            # Handle mouse wheel scrolling here
            print("on_mouse_wheel")
            if self.scroll_timeout is not None:
                self.scroll_timeout.Stop()
            
            self.scroll_timeout = wx.CallLater(1000, self.OnScrollDebounced,event)
            event.Skip()  # Continue processing the event
            
        except Exception as e:
            print("Error in on_mouse_wheel",str(e))
    
    def get_directory_from_dialog(self):
        try:
            dlg = wx.DirDialog(self, "Choose a directory", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                directory = dlg.GetPath()
                dlg.Destroy()
                return directory
            dlg.Destroy()
            return None
        except Exception as e:
            print("Error in get_directory_from_dialog",str(e))

    def delete_all_rows(self):
        try:
            with FileSizeSorter.lock:
                num_rows = self.file_grid.GetNumberRows()
                if num_rows > 0:
                    self.file_grid.DeleteRows(0, num_rows)
        except Exception as e:
            print("Error in delete_all_rows",str(e))

    def set_row_background_color(self, row, color):
        # Create a custom attribute for the row
        try:
            attr = gridlib.GridCellAttr()
            attr.SetBackgroundColour(color)

            # Apply the attribute to all cells in the row
            for col in range(0, self.file_grid.GetNumberCols() - 2):
                self.file_grid.SetAttr(row, col, attr)
        except Exception as e:
            print("Error in set_row_background_color",str(e))

    def Filling_row_with_color(self, file_size, row):
        try:
            if file_size in self.color_mapping:
                color = self.color_mapping[file_size]
            else:
                self.current_color_index = (self.current_color_index + 1) % len(self.colors)
                color = self.colors[self.current_color_index]
                self.color_mapping[file_size] = color

            if row != -1:
                attr = self.file_grid.GetOrCreateCellAttr(row, 0)
                attr.SetBackgroundColour(color)
                self.file_grid.SetAttr(row, 0, attr)
        except Exception as e:
            print("Error in Filling_row_with_color",str(e))

    def process_files(self):
        try:
            self.color_mapping = {}
            # Create a separate thread for adding rows
            
            if FileSizeSorter.lock.locked():
                FileSizeSorter.lock.release_lock()

            self.batch = 0
            if self.file_info:
                FileSizeSorter.stop_flag = True
                start = self.batch*self.initial_batch_size
                end = (self.batch+1)*self.initial_batch_size
                batch_size =  end - start

                self.fully_parsed = False
                self.add_rows_into_filegrid(self.file_info[start:end], batch_size, self.sleep_obj)
                self.initial_batch_loaded = True
                

                # thread = threading.Thread(target=self.add_rows_into_filegrid,args=(self.file_info[start:end],FileSizeSorter.lock, self.sleep_obj))
                # thread.start()
                # thread.join()
        except Exception as e:
            print("Error in process_files",str(e))
    
    def add_rows_into_filegrid(self, file_info, batch_size, sleep_obj):
        try:
            count = 0
            total_files = len(self.file_info)
            rows_in_file_grid = self.file_grid.GetNumberRows()
            with FileSizeSorter.lock:
                new_rows_count = total_files - rows_in_file_grid
                if new_rows_count > 0 and FileSizeSorter.stop_flag:
                    if new_rows_count < batch_size:
                        self.file_grid.AppendRows(new_rows_count)
                    else:
                        self.file_grid.AppendRows(batch_size)
                    for row, (file_path, file_size) in enumerate(file_info):
                        try:
                            if FileSizeSorter.stop_flag:
                                self.file_grid.SetCellValue(rows_in_file_grid+row, 0, file_path)
                                self.file_grid.SetCellValue(rows_in_file_grid+row, 1, f"{float(float(file_size) / (1024 * 1024))}")
                                self.file_grid.SetCellValue(rows_in_file_grid+row, 2, "Explore")
                                self.file_grid.SetCellValue(rows_in_file_grid+row, 3, "Delete")
                                self.Filling_row_with_color(file_size, rows_in_file_grid+row)
                            else:
                                wx.CallAfter(self.update_gui)
                                value = 100
                                wx.CallAfter(self.update_progress_bar, value)
                                self.fully_parsed = True
                                break
                            count += 1

                            if count % batch_size == 0 or count == total_files or count % 20 == 0:
                                wx.CallAfter(self.update_gui)
                                sleep_obj.wait(0.001)  # Sleep for 1 second to throttle updates

                                value = int(((rows_in_file_grid + count )/ total_files) * 100)
                                wx.CallAfter(self.update_progress_bar, value)

                        except Exception as e:
                            print("Error while processing file:", str(e))
                else:    
                    value = 100
                    wx.CallAfter(self.update_progress_bar, value)
                    wx.CallAfter(self.update_gui)
                    self.fully_parsed = True
                    # wx.CallAfter(self.show_completion_message)
        except Exception as e:
            print("Error in add_rows_into_filegrid",str(e))

    def update_gui(self):
        try:
            self.file_grid.Refresh()
            self.Refresh()
        except Exception as e:
            print("Error in update_gui",str(e))

    def update_progress_bar(self, value):
        try:
            self.progress_gauge.SetValue(value)
            self.progress_gauge.SetToolTip(f"Progress: {value}%")
        except Exception as e:
            print("Error in update_progress_bar",str(e))

    def show_completion_message(self):
        wx.MessageBox("File scan completed successfully!", "Scan Complete", wx.OK | wx.ICON_INFORMATION)

    def scan_directory(self, directory, checkbox_flag):
        try:
            start_time = time.time()

            self.file_grid.ClearGrid()
            FileSizeSorter.stop_flag = False  # Clear the grid before scanning the directory
            self.delete_all_rows()
            self.file_info = None
            self.initial_batch_loaded = False
            wx.CallAfter(self.anim_ctrl.Play)
            # Add label on progressbar of scanning 

            file_info = self.get_file_info(directory, checkbox_flag)
            
            self.file_info = file_info

            end_time = time.time()

            elapsed_time = end_time - start_time
            print(f"Scanned items in {elapsed_time:.4f} seconds")
            self.fully_parsed = None
            self.sleep_obj.wait(1)
            wx.CallAfter(self.anim_ctrl.Stop)
            # thread = threading.Thread(target=self.process_files)
            # thread.start()
            self.process_files()
        except Exception as e:
            print("Error in scan_directory",str(e))

    def get_file_info(self, directory, checkbox_flag):
        try:
            file_info = []

            required_file_size_start = 0
            required_file_size_end = None
            try:
                if self.required_file_size_start.GetValue().strip():
                    get_float_number = float(self.required_file_size_start.GetValue())
                    # integer_part = int(float_number)                
                    if get_float_number < 0.5 and checkbox_flag:
                        float_number = get_float_number
                    else:
                        if get_float_number < 0.5:
                            float_number = 0.5
                        else:
                            float_number = get_float_number
                else:
                    if checkbox_flag:
                        float_number = 0
                    else:
                        float_number = 0.5
                required_file_size_start = float_number * 1024 * 1024
                    
                if self.required_file_size_end.GetValue().strip():
                    float_number = float(self.required_file_size_end.GetValue())
                    # integer_part = int(float_number)
                    required_file_size_end = float_number * 1024 * 1024

                
            except Exception as e:
                print("Error - ", str(e))
                wx.MessageBox("Please enter INT value of file size", "File's size", wx.OK | wx.ICON_ERROR)
                float_number = 0.5
                required_file_size_start = float_number * 1024 * 1024

            # file_paths = glob.glob(os.path.join(directory, "**"), recursive=True)
            file_paths = get_file_paths_with_os_scan(directory, required_file_size_start, required_file_size_end)
            file_paths.sort(key=lambda x: x[1], reverse=True)

            return file_paths
        except Exception as e:
            print("Error in get_file_info",str(e))

    def on_grid_cell_click(self, event):
        try:
            row = event.GetRow()
            col = event.GetCol()
            if col == 2:
                file_path = self.file_grid.GetCellValue(row, 0)
                self.on_selected_file_dir_browse(file_path)
            elif col == 3:
                file_path = self.file_grid.GetCellValue(row, 0)
                

                dlg = wx.MessageDialog(self, f"Are you sure you want to delete {file_path}?",
                                    "Confirm Deletion",
                                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
                result = dlg.ShowModal()
                dlg.Destroy()

                if result == wx.ID_YES:
                    try:
                        self.delete_file(file_path)
                    except Exception as e:
                        wx.MessageBox(f"Error deleting file: {e}", "Error", wx.OK | wx.ICON_ERROR)
        except Exception as e:
            print("Error in on_grid_cell_click",str(e))

    def on_selected_file_dir_browse(self, file_full_path):
        try:
            dirname = os.path.dirname(file_full_path)
            if os.path.exists(dirname) and os.path.exists(file_full_path):
                if wx.Platform == '__WXMSW__':
                    # Code for Windows
                    subprocess.run(['explorer', '/select,', file_full_path], shell=True)
                elif wx.Platform == '__WXGTK__':
                    # Code for Linux
                    subprocess.run(['nautilus', '--select', file_full_path])
                elif wx.Platform == '__WXMAC__':
                    # Code for macOS
                    subprocess.run(['open', '-R', file_full_path])
                else:
                    # Unsupported platform
                    print("Unsupported operating system.")
            else:
                wx.MessageBox("This path is not valid for browse.", "Warning",
                                    wx.OK | wx.ICON_ERROR)
                self.delete_row_from_filegrid(file_full_path)
        except Exception as e:
            print("Error in on_selected_file_dir_browse",str(e))

    def delete_file(self, file_path):
        try:
            if os.path.isfile(file_path):
                if "Windows" in self.os_description:
                    
                    
                    import ctypes
                    import ctypes.wintypes
                    class SHFILEOPSTRUCT(ctypes.Structure):
                        _fields_ = [
                            ("hwnd", ctypes.wintypes.HWND),
                            ("wFunc", ctypes.c_uint),
                            ("pFrom", ctypes.wintypes.LPCWSTR),
                            ("pTo", ctypes.wintypes.LPCWSTR),
                            ("fFlags", ctypes.c_short),
                            ("fAnyOperationsAborted", ctypes.wintypes.BOOL),
                            ("hNameMappings", ctypes.wintypes.LPVOID),
                            ("lpszProgressTitle", ctypes.wintypes.LPCWSTR)
                        ]

                    def move_to_trash(file_path):
                        file_op = SHFILEOPSTRUCT()
                        file_op.wFunc = FO_DELETE
                        file_op.pFrom = ctypes.c_wchar_p(file_path + '\0')
                        file_op.pTo = None
                        file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION

                        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
                        if result != 0:
                            raise ctypes.WinError(result)
                    
                    move_to_trash(file_path)

                elif  "macOS" in self.os_description:
                    import send2trash  # Required for moving files to trash on macOS and Windows
                    send2trash.send2trash(file_path)

                elif "Linux" in self.os_description:
                    # Move file to trash on Linux (Ubuntu)
                    gio_trash = subprocess.run(["gio", "trash", file_path], capture_output=True)
                    if gio_trash.returncode != 0:
                        wx.MessageBox("Failed to move the file to the trash bin.", "Delete File",
                                    wx.OK | wx.ICON_ERROR)
                        return
                self.delete_row_from_filegrid(file_path)
        except Exception as e:
            print("Error in delete_file",str(e))

    def delete_row_from_filegrid(self, file_path):
        try:
            row = self.find_row_by_file_path(file_path)
            if row >= 0:
                self.file_grid.DeleteRows(row)
        except Exception as e:
            print("Error in delete_row_from_filegrid",str(e))

    def find_row_by_file_path(self, file_path):
        try:
            for row in range(self.file_grid.GetNumberRows()):
                if self.file_grid.GetCellValue(row, 0) == file_path:
                    return row
            return -1
        except Exception as e:
            print("Error in find_row_by_file_path",str(e))



class FileSizeSorter(wx.Frame):
    stop_flag = True
    lock = threading.Lock()
    def __init__(self, parent, title):
        super(FileSizeSorter, self).__init__(parent, title=title, size=(700, 500))
        # self.SetBackgroundColour('#252525')
        # self.SetBackgroundColour("#b2babb") 
        self.SetBackgroundColour('#2c001e') 
        self.os_description = wx.GetOsDescription()
        panel = wx.Panel(self)
        self.panel = panel



        self.thread_m = None

        self.checkbox_flag = False
        self.checkbox = wx.CheckBox(panel, label="")        
        self.checkbox.Bind(wx.EVT_CHECKBOX, self.OnCheckBox)
        self.checkbox.SetToolTip("If you want to include files less 500kb size, then check")

        self.required_file_size_start = wx.TextCtrl(panel, size=((50, 25)))
        self.required_file_size_start.SetToolTip("Set the MB more then want to get files with in starting size")
        
        self.required_file_size_end = wx.TextCtrl(panel, size=((50, 25)))
        self.required_file_size_end.SetToolTip("Set the MB less then want to get files with in ending size")
        
        self.directory_path = wx.TextCtrl(panel, size=((250, 25)))
        self.directory_path.SetToolTip("Directory path which want to scan")

        self.scan_button = wx.Button(panel, label="Scan Directory")
        self.scan_button.Bind(wx.EVT_BUTTON, self.on_scan)

        self.refresh_button = wx.Button(panel, label="Refresh")
        self.refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh)

        self.stop_button = wx.Button(panel, label="Stop")
        self.stop_button.Bind(wx.EVT_BUTTON, self.on_stop)

        self.exit_button = wx.Button(panel, label="Exit")
        self.exit_button.Bind(wx.EVT_BUTTON, self.on_exit)


        self.progress_gauge = SophisticatedProgressBar(panel, range=100, size=(650, 20), color=wx.Colour(34, 139, 34))
        
        self.progress_gauge.SetToolTip(f"Progress : {0}%")


        script_path = os.path.abspath(__file__)

        script_directory = os.path.dirname(script_path)
        loader_path = os.path.join(script_directory, "loader.gif")
        
        gif = wx.adv.Animation(loader_path)
        self.anim_ctrl = wx.adv.AnimationCtrl(panel, -1, gif)

        self.Panel_for_grid = None

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.sizer = sizer

        self.hori_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.hori_sizer.Add(self.anim_ctrl, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.checkbox, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.required_file_size_start, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.required_file_size_end, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.scan_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.stop_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.refresh_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.directory_path, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.hori_sizer.Add(self.exit_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        

        sizer.Add(self.hori_sizer, 0, wx.EXPAND | wx.ALL, 5)
        sizer.Add(self.progress_gauge, 0, wx.EXPAND | wx.ALL, 5)
        # sizer.Add(self.anim_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        panel.SetSizer(sizer)
        self.directory = None
    
    def OnCheckBox(self, event):
        # Check the state of the checkbox
        if self.checkbox.IsChecked():
            self.checkbox_flag = True
        else:
            self.checkbox_flag = False


    def on_scan(self, event):
        try:
            dlg = wx.DirDialog(self, "Choose a directory", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                self.directory = dlg.GetPath()
                dlg.Destroy()

                self.directory_path.SetLabel(self.directory)
                new_width = max(250, len(self.directory) * 8)  
                self.directory_path.SetSize((new_width, 25))

                self.progress_gauge.SetValue(0)
                self.progress_gauge.SetToolTip(f"Progress : {0}%")
                
                if self.Panel_for_grid:

                    FileSizeSorter.stop_flag = False
                    with FileSizeSorter.lock:
                        self.Panel_for_grid.file_grid.Destroy()
                        self.Panel_for_grid.Destroy()
                    self.Panel_for_grid = None
                    FileSizeSorter.stop_flag = True


                self.Panel_for_grid = PanelForGrid(self.panel, self.directory_path, self.progress_gauge, self.anim_ctrl, self.required_file_size_start, self.required_file_size_end)
                self.Panel_for_grid.Show()
                self.sizer.Add(self.Panel_for_grid, 1, wx.EXPAND | wx.ALL, 5)
                self.sizer.Layout()

                self.thread_m = threading.Thread(target=self.Panel_for_grid.scan_directory,args=(self.directory,self.checkbox_flag))
                self.thread_m.daemon = True
                self.thread_m.start()


        except Exception as e:
            print("Error in on_scan",str(e))

    def on_stop(self, event):
        FileSizeSorter.stop_flag = False
    
    def on_exit(self, event):
        # wx.Exit()
        self.Destroy()

        
    def on_refresh(self, event):
        try:
            if self.directory:
                if os.path.exists(self.directory):
                    if self.Panel_for_grid:

                        FileSizeSorter.stop_flag = False
                        with FileSizeSorter.lock:
                            self.Panel_for_grid.file_grid.Destroy()
                            self.Panel_for_grid.Destroy()
                        self.Panel_for_grid = None
                        FileSizeSorter.stop_flag = True
                        
                    self.progress_gauge.SetValue(0)
                    self.progress_gauge.SetToolTip(f"Progress : {0}%")
                    
                    Panel_for_grid = PanelForGrid(self.panel, self.directory_path, self.progress_gauge, self.anim_ctrl, self.required_file_size_start,self.required_file_size_end)
                    self.Panel_for_grid = Panel_for_grid
                    Panel_for_grid.Show()
                    self.sizer.Add(Panel_for_grid, 1, wx.EXPAND | wx.ALL, 5)
                    self.sizer.Layout()

                    self.thread_m = threading.Thread(target=self.Panel_for_grid.scan_directory,args=(self.directory,self.checkbox_flag))
                    self.thread_m.daemon = True
                    self.thread_m.start()


        except Exception as e:
            print("Error in on_refresh",str(e))



if __name__ == '__main__':
    app = wx.App()
    frame = FileSizeSorter(None, "File Size Sorter")
    frame.Show()
    app.MainLoop()
