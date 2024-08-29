import tkinter as tk
import ttkbootstrap as ttk
from tkinter import filedialog
import os
import yt_dlp
import threading
import glob
from pathlib import Path
import tkinter.font as tkfont
import cProfile
import ctypes


def extract_links(partial_info):
    return [entry.get('webpage_url', None) for entry in partial_info.get('entries', [])]


extraction_event = threading.Event()
downloads = []  # List to store download information
extraction_cancelled = False
global partial_info
partial_info = None
global ydl_opts
ydl_opts = None
processed_videos = 0
total_videos = 0

result = {}


def show_loading_window():
    loading_window = tk.Toplevel()
    loading_window.title("Loading")
    loading_window.geometry("200x150")
    loading_window.resizable(False, False)

    label = ttk.Label(loading_window, text="Extracting video information...")
    label.pack(pady=20)

    progress_bar = ttk.Progressbar(loading_window, mode='indeterminate')
    progress_bar.pack(pady=10)
    progress_bar.start()

    cancel_button = ttk.Button(loading_window, text="Cancel", command=loading_window.destroy)
    cancel_button.pack(pady=10)

    return loading_window


def chooseDirectory():
    file_path = filedialog.askdirectory()
    directory.set(file_path)


def progress_hook(d):

    if extraction_event.is_set():
        raise Exception("Extraction cancelled")

    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0.0%')
        download_id = d['info_dict']['webpage_url']
        p = p.strip(' %.')
        try:
            number_int = int(float(p))
        except ValueError:
            number_int = 0

        for download in downloads:
            if download['id'] == download_id:
                if download['cancelled']:
                    raise Exception("Download cancelled")
                download['progress'].set(number_int)
                # download['label'].config(text=f"{download['title']} - {number_int}%")
                download['labelProgress'].config(text=f"{number_int}")
                window.update_idletasks()

    elif d['status'] == 'finished':
        download_id = d['info_dict']['webpage_url']
        for download in downloads:
            if download['id'] == download_id:
                if not download['cancelled']:
                    # download['label'].config(text=f"{download['title']} - Complete")
                    download['labelProgress'].config(text=f"Complete")
                    download['completed'] = True


def update_progress(download_info, ydl):
    download_info['progressbar'].update()
    ydl.download([pasted_url.get()])
    if not download_info['completed']:
        window.after(100, lambda: update_progress(download_info, ydl))


def progress_process_download(d):
    global processed_videos, total_videos
    if d['status'] == 'finished':
        processed_videos += 1
        if 'total_videos' in d:
            total_videos = d['total_videos']
        print(f"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXProcessed {processed_videos} out of {total_videos} videos")

def download():
    global result
    try:
        pasted_url.set(window.clipboard_get())
        url = pasted_url.get()
        if not url.startswith("https://www.youtube.com"):
            raise Exception("The link is not a youtube link")

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(directory.get(), '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
        }

        def download_thread(url):
            global result, extraction_cancelled, partial_info

            extraction_cancelled = False
            extraction_event.clear()

            loading_window = show_loading_window()

            def extract_info():
                global partial_info
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.add_progress_hook(progress_process_download)
                        partial_info = ydl.extract_info(url, download=False, process=True)

                        if 'entries' in partial_info:
                            global total_videos
                            total_videos = len(partial_info['entries'])

                except Exception as e:
                    partial_info = None
                    print(f"Extraction error: {e}")
                finally:
                    if not extraction_cancelled:
                        loading_window.destroy()

            extract_thread = threading.Thread(target=extract_info)
            extract_thread.start()

            def check_extract_thread():
                nonlocal extract_thread, loading_window
                if extract_thread.is_alive() and not extraction_cancelled:
                    window.after(100, check_extract_thread)
                else:
                    if not extraction_cancelled:
                        process_extracted_info(url)
                    loading_window.destroy()

            def on_cancel():
                nonlocal loading_window
                global extraction_cancelled
                extraction_cancelled = True
                loading_window.destroy()
                extraction_event.set()

                # Give the thread a chance to exit gracefully
                extract_thread.join(timeout=1.0)

                # If the thread is still alive after the timeout, we can try to raise an exception in it
                if extract_thread.is_alive():
                    raise_exception_in_thread(extract_thread)

            loading_window.protocol("WM_DELETE_WINDOW", on_cancel)
            loading_window.children['!button']['command'] = on_cancel

            window.after(100, check_extract_thread)

        threading.Thread(target=download_thread, args=(url,)).start()
    except Exception as error:
        create_popup(error)


def raise_exception_in_thread(thread):
    thread_id = thread.ident
    print("THREAD HAS BEEN STOPPED")
    if thread_id is not None:
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id),
                                                         ctypes.py_object(SystemExit))
        if res > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), None)
            print("Exception raise failed")

def process_extracted_info(url):
    global result, extraction_cancelled, ydl_opts, partial_info
    if extraction_cancelled:
        print("Extraction was cancelled.")
        return

    if partial_info is None:
        print("Error occurred during extraction.")
        return

    if 'entries' in partial_info:  # It's a playlist
        create_popup_selection(partial_info)  # Check for selection
        if result.get('approved', False):
            for entry in result['links']:
                video_url = entry['webpage_url']
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    create_download_item(video_url, entry['name'], ydl)
        result = {}
    else:  # It's a single video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            create_download_item(url, partial_info['title'], ydl)

def create_popup_selection(info = {}):
    popup = tk.Toplevel(window)
    popup.title("Select Songs")
    popup.geometry("600x400")
    # popup.attributes('-topmost', True)
    linksList = []
    global result

    popup.columnconfigure(0, weight=9)
    popup.columnconfigure(1, weight=9)
    popup.columnconfigure(2, weight=1)
    popup.rowconfigure(0, weight=9)
    popup.rowconfigure(1, weight=9)

    CheckButtonState = tk.IntVar(value=0)

    custom_font = tkfont.Font(family="Helvetica", size=13, weight="bold")

    canvas2 = tk.Canvas(popup)
    canvas2.grid(row=0, column=0, columnspan=2, sticky='nswe', pady=10)

    # Add a scrollbar to the canvas
    scrollbar = ttk.Scrollbar(popup, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=2, sticky='nse')

    # Configure the canvas to use the scrollbar
    canvas2.configure(yscrollcommand=scrollbar.set)

    # Create a frame inside the canvas
    scrollable_frame = ttk.Frame(canvas2, relief=tk.RIDGE, borderwidth=1)
    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    # Create a window inside the canvas that will contain the scrollable frame
    canvas_window2 = canvas2.create_window((10, 0), window=scrollable_frame, anchor="nw")

    # Function to add a new row to the scrollable frame

    popup.checked_img = tk.PhotoImage(file="checked.png")
    popup.unchecked_img = tk.PhotoImage(file="unchecked.png")
    unchecked = popup.unchecked_img.subsample(1, 1)

    def on_mouse_wheel(event):
        canvas2.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_frame_configure(event):
        canvas2.configure(scrollregion=canvas.bbox("all"))

    def configure_canvas(event):
        canvas2.configure(scrollregion=canvas.bbox("all"))
        if scrollable_frame.winfo_height() <= canvas.winfo_height():
            scrollbarElements.grid_remove()
        else:
            scrollbarElements.grid()

    def resize_canvas(event):
        canvas2.itemconfig(canvas_window2, width=event.width - 10)
        print(str(event.width) + "   " + str(canvas2.winfo_width()) + "  " + str(window.winfo_width()))


    canvas2.bind_all("<MouseWheel>", on_mouse_wheel)
    canvas2.bind("<Configure>", resize_canvas)
    scrollable_frame.bind("<Configure>", on_frame_configure)
    link_states = dict()


    for i, entry in enumerate(info['entries']):  # Add multiple check buttons for demonstration

        checkButtonState = tk.IntVar()
        checkButtonState.set(1)
        link_states[entry['title']] = checkButtonState

        def update_link_state(state, name=entry['title']):
            link_states[name].set(state)

        row = len(scrollable_frame.winfo_children())
        checkButton = tk.Checkbutton(scrollable_frame,
                          image=popup.unchecked_img,
                          selectimage=popup.checked_img,
                          indicatoron=False,
                          compound="top",
                          onvalue=1,
                          offvalue=0,
                          variable=checkButtonState,
                          command= lambda : update_link_state(checkButtonState.get()))

        label = tk.Label(scrollable_frame, text=entry['title'], font=custom_font)

        checkButton.grid(row=row, column=0, sticky="nwe", padx=10, pady=10)

        label.grid(row=row, column=1, sticky="nwe", padx=10, pady=10)

        linkInfo = \
                    {
                    'label':label,
                    'button':checkButton,
                    'name': entry['title'],
                    'webpage_url': entry['webpage_url'],
                    'buttonState': False,
                }
        linksList.append(linkInfo)

    # Add initial rows to the scrollable frame
    # Configure the columns to expand
    scrollable_frame.grid_columnconfigure(0, weight=1)
    scrollable_frame.grid_columnconfigure(1, weight=10)


    # Bind the resize event to the canvas
    canvas2.bind("<Configure>", resize_canvas)
    canvas2.bind_all("<MouseWheel>", on_mouse_wheel)
    scrollable_frame.bind("<Configure>", on_frame_configure)

    # Add OK and Cancel buttons
    button_frame = ttk.Frame(popup)
    button_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=10)

    ok_button = tk.Button(button_frame, text="OK", command=lambda : approved_selection(), width=20, height=2, background='blue')
    ok_button.pack(side="left", expand=True)
    ok_button.config()

    cancel_button = tk.Button(button_frame, text="Cancel", command=lambda :not_approved_selection(), width=20, height=2, background='blue')
    cancel_button.pack(side="right", expand=True)
    cancel_button.config()

    result = {'approved' : False, 'links': []}

    def approved_selection():
        result['approved'] = True
        to_remove = []
        for i, entry in enumerate(linksList):
            if link_states[entry['name']].get() == 0:
                to_remove.append(entry)
        for entry in to_remove:
            linksList.remove(entry)
        result['links'] = linksList
        popup.destroy()

    def not_approved_selection():
        result['approved'] = False
        popup.destroy()

    popup.wait_window()


def is_checked(button):
    # Simulate the button press to get the current state
    button.invoke()
    state = button.select()
    button.deselect()  # Ensure it returns to its original state
    return state


def create_popup(error):
    # Create a new top-level window
    popup = tk.Toplevel(window)
    popup.title("Popup Window")
    popup.geometry("200x100")
    popup.attributes('-topmost', True)

    # Add a label to the popup window
    label = ttk.Label(popup, text=error.args)
    label.pack(pady=10)

    # Add a button to close the popup window
    close_button = ttk.Button(popup, text="Close", command=popup.destroy)
    close_button.pack(pady=5)



def cancel_button(download_info):
    download_info['cancelled'] = True
    download_info['label'].config(text=f"{download_info['title']} - Cancelled")
    cleanup_unfinished(download_info)


def cleanup_unfinished(download_info):
    partial_path = directory.get()
    print(partial_path)

    file_name_without_extension = download_info['title']


    for file2 in os.listdir(partial_path):
        if file2.startswith(file_name_without_extension):
            # Construct the full file path
            file_path = partial_path + '/' + file2
            # Delete the file
            os.remove(file_path)
            print(f"File '{file_path}' has been deleted.")
            break
        #     else:
        #         print(f"No file starting with '{file_name_without_extension}' found.")
        #     os.remove(file + '/' + download_info['title'])
        #     print(f"Removed partial file: {file}")
        # except Exception as e:
        #     print(f"Error removing file {file}: {str(e)}")
        # print("FISIERE:" + file)

def on_mouse_wheel(event):
    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

def on_frame_configure(event):
    canvas.configure(scrollregion=canvas.bbox("all"))

def configure_canvas(event):
    canvas.configure(scrollregion=canvas.bbox("all"))
    if frameElements.winfo_height() <= canvas.winfo_height():
        scrollbarElements.grid_remove()
    else:
        scrollbarElements.grid()

def resize_canvas(event):
    canvas.itemconfig(canvas_window, width=event.width - 5)
    print(str(event.width) + "   " + str(canvas.winfo_width()) + "  " + str(window.winfo_width()) + " " + str(frameElements.winfo_width()))


def create_download_item(url,title, ydl):
    labelExperiment = ttk.Label(frameElements, text=title)
    progressBar = ttk.Progressbar(frameElements, orient='horizontal', length=90, mode='determinate', maximum=100)
    progressLabel = ttk.Label(frameElements)
    cancelButton = ttk.Button(frameElements, text='Cancel', command= lambda : cancel_button(download_info))

    row = len(downloads) + 1
    labelExperiment.grid(row=row, column=0, sticky='nwe', padx=3, pady=7)
    progressBar.grid(row=row, column=1, sticky='nwe', padx=3, pady=7)
    progressLabel.grid(row=row, column=2, sticky='nwe', padx=3, pady=7)
    cancelButton.grid(row=row, column=3, sticky='nwe', padx=7, pady=7)

    progress_var = tk.IntVar()
    download_info = {
        'id': url,
        'title': title,
        'label': labelExperiment,
        'progress': progress_var,
        'progressbar': progressBar,
        'cancel_button': cancelButton,
        'labelProgress' : progressLabel,
        'completed': False,
        'cancelled': False
    }
    downloads.append(download_info)
    progressBar.config(variable=progress_var)

    def download_single():
        try:
            ydl.download([url])
            print("CEVA")
            if download_info['completed'] == True:
                download_info['cancel_button'].config(text='Delete')
                download_info['cancel_button'].config(command=lambda : eliminate_row(download_info))
        except Exception as e:
            if not download_info['cancelled']:
                download_info['label'].config(text=f"{download_info['title']} - Error: {str(e)}")
                cleanup_unfinished(download_info)
        if not download_info['cancelled']:
            download_info['completed'] = True
        else:
            cleanup_unfinished(download_info)

    threading.Thread(target=download_single).start()


    def eliminate_row(download_info):
        download_info['label'].grid_remove()
        download_info['label'].destroy()
        download_info['progressbar'].grid_remove()
        download_info['progressbar'].destroy()
        download_info['cancel_button'].grid_remove()
        download_info['cancel_button'].destroy()
        download_info['labelProgress'].grid_remove()
        download_info['labelProgress'].destroy()
        position = downloads.index(download_info)
        downloads.pop(position)

        if not downloads:
            global frameElements, canvas  # Assuming frameElements is a global variable

            frameElements.destroy()  # Destroy the current frame
            canvas.destroy()
            canvas = ttk.Canvas(window)
            canvas.grid(row=2, column=0, columnspan=2, sticky='nswe')
            frameElements = ttk.Frame(canvas, relief=tk.RIDGE)
            frameElements.bind("<Configure>", on_frame_configure)
            canvas.bind_all("<MouseWheel>", on_mouse_wheel)
            canvas.bind("<Configure>", resize_canvas)
            canvas.create_window((0, 0), window=frameElements, anchor="nw")
            canvas_window = canvas.create_window((2, 0), window=frameElements, anchor="nw")
            frameElements.columnconfigure(0, weight=8)

            window.update_idletasks()  # Force the window to update
        else:
            # Re-grid the remaining widgets
            for i, entry in enumerate(downloads):
                entry['label'].grid(row=i, column=0, sticky='nwe', padx=3, pady=7)
                entry['progressbar'].grid(row=i, column=1, sticky='nwe', padx=3, pady=7)
                entry['cancel_button'].grid(row=i, column=3, sticky='nwe', padx=7, pady=7)
                entry['labelProgress'].grid(row=i, column=2, sticky='nwe', padx=3, pady=7)

def on_closing():
    for download in downloads:
        if not download['completed']:
            cleanup_unfinished(download)
    window.destroy()


def get_default_downloads_folder():
    if os.name == 'nt':  # For Windows
        downloads_folder = Path(os.getenv('USERPROFILE')) / 'Downloads'
    else:  # For MacOS and Linux
        downloads_folder = Path.home() / 'Downloads'

    return str(downloads_folder)


# Usage
downloads_path = get_default_downloads_folder()
downloads_path = downloads_path.replace("\\\\", "\\")


# GUI setup
window = tk.Tk()
window.geometry("500x400")
# window.minsize(500, 400)
window.title("Youtube Downloader")

window.columnconfigure(0, weight=8)
window.columnconfigure(1, weight=8)
window.columnconfigure(2, weight=1)
window.rowconfigure(0, weight=1)
window.rowconfigure(1, weight=1)
window.rowconfigure(2, weight=20)


###################### CANVAS ###########################
canvas = tk.Canvas(window)
canvas.grid(row=2, column=0, columnspan=2, sticky='nswe')

scrollbarElements = ttk.Scrollbar(window, orient = 'vertical', command=canvas.yview)
scrollbarElements.grid(row=2, column=2, sticky='ns')
canvas.configure(yscrollcommand=scrollbarElements.set)

frameElements = ttk.Frame(canvas, relief=tk.RIDGE)
frameElements.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))


# frameElements.grid_propagate(False)

canvas.create_window((0,0), window=frameElements, anchor='nw')


canvas.bind_all("<MouseWheel>", on_mouse_wheel)
canvas.bind("<Configure>", resize_canvas)
frameElements.bind("<Configure>", on_frame_configure)

canvas_window = canvas.create_window((2, 0), window=frameElements, anchor="nw")

################## /CANVAS #########################

frameElements.columnconfigure(0, weight=8)
# frameElements.columnconfigure(1, weight=5)
# frameElements.columnconfigure(2, weight=3)
# frameElements.columnconfigure(3, weight=3)

# frameElements.rowconfigure(0, weight=1)
# frameElements.rowconfigure(1, weight=1)

directory = tk.StringVar()
directory.set(downloads_path)
print(directory.get())
buttonInput = ttk.Button(window, text="Input", command=chooseDirectory)
inputField = ttk.Entry(window, textvariable=directory)

buttonInput.grid(row=0, column=0, padx=10, sticky='nswe', pady=10)
inputField.grid(row=1, column=0, sticky='nwe', padx=4, pady=5)

pasted_url = tk.StringVar()
pasteButton = ttk.Button(window, text="Paste", command=download)
pasteEntry = ttk.Entry(window, textvariable=pasted_url)

pasteButton.grid(row=0, column=1, sticky='nswe', padx=10, pady=10, columnspan=2)
pasteEntry.grid(row=1, column=1, sticky='nwe', padx=4, pady=5, columnspan=2)

# row = len(frameElements.winfo_children())
# label = ttk.Label(frameElements, text=f"Label {row + 1}", background='green')
# label.grid(row=row, column=0, sticky="ew", pady=5)

window.protocol("WM_DELETE_WINDOW", on_closing)

window.mainloop()
