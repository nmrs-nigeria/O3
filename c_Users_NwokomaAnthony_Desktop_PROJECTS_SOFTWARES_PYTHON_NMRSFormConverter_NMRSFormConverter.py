import tkinter as tk
from tkinter import ttk, Text, END, VERTICAL, messagebox, filedialog
import webbrowser
import requests
from openpyxl.styles import Font, Alignment
import mysql.connector
from bs4 import BeautifulSoup
from openpyxl import Workbook
import json
import os
import re
import uuid
import time

def to_camel_case_id(label):
    # Remove non-alphanumeric, split by space, lowercase first, capitalize rest, join with _
    words = re.sub(r'[^a-zA-Z0-9 ]', '', label).strip().split()
    if not words:
        return "q"
    camel = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
    return camel

class NMRSFormConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("NMRS HTML Form Converter")
        self.root.geometry("1400x800")

        # --- Initialize instance variables ---
        self.connection = None
        self.json1_data = None
        self.json2_data = None
        self.json1_path = tk.StringVar(value="No file loaded")
        self.json2_path = tk.StringVar(value="No file loaded")
        self.concept_map = {}      # {concept_id: {"uuid": ..., "name": ...}}
        self.concept_datatypes = {}  # {concept_id: datatype}
        self.concept_numeric = {}   # {concept_id: {"hi_absolute": ..., "low_absolute": ...}}
        self.forms = []
        self.form_checkboxes = [] # To store IntVars for checkboxes
        self.selected_form_index = None
        self.option_sets = {}
        self.concept_answers = {}  # {concept_id: [{"label": ..., "uuid": ...}, ...]}

        # --- Main Tabbed Interface ---
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Form Converter Tab ---
        form_converter_tab = ttk.Frame(self.notebook)
        self.notebook.add(form_converter_tab, text="Form Converter")
        self._setup_form_converter_ui(form_converter_tab)

        # --- JSON Tools Tab ---
        json_tools_tab = JSONToolsTab(self.notebook, self)
        self.notebook.add(json_tools_tab, text="JSON Form Tools")

        # --- OCL Management Tab ---
        self.ocl_management_tab = OCLManagementTab(self.notebook, self)
        self.notebook.add(self.ocl_management_tab, text="OCL Management")

        self.connect_to_db(auto=True)

    def _setup_form_converter_ui(self, parent_frame):
        # --- Main Layout with PanedWindows for resizability ---
        main_paned_window = ttk.PanedWindow(parent_frame, orient=tk.VERTICAL)
        main_paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Top Row Frame (DB, Forms, Concept Search) ---
        top_row_frame = ttk.Frame(main_paned_window)
        top_row_frame.columnconfigure(0, weight=1)
        top_row_frame.columnconfigure(1, weight=1)
        top_row_frame.columnconfigure(2, weight=1)
        main_paned_window.add(top_row_frame, weight=1)

        # DB Connection Frame
        self.db_frame = ttk.LabelFrame(top_row_frame, text="Database Connection")
        self.db_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        self._add_db_widgets()

        # Forms List Frame (middle)
        self.forms_frame = ttk.LabelFrame(top_row_frame, text="Available Forms")
        self.forms_frame.grid(row=0, column=1, padx=5, pady=10, sticky="nsew")
        self.forms_frame.columnconfigure(0, weight=1)
        self.forms_frame.rowconfigure(1, weight=1) # Make listbox expand

        # Concept Search Frame (right)
        self.concept_frame = ttk.LabelFrame(top_row_frame, text="Concept Search/Info")
        self.concept_frame.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="nsew")
        self.concept_frame.columnconfigure(0, weight=1) # type: ignore
        self._add_concept_widgets()

        # --- Bottom Row PanedWindow (HTML Editor and JSON Output) ---
        bottom_paned_window = ttk.PanedWindow(main_paned_window, orient=tk.HORIZONTAL)
        main_paned_window.add(bottom_paned_window, weight=4) # Give more initial space

        # XML Data Display Frame (left pane of bottom)
        self.xml_frame = ttk.LabelFrame(bottom_paned_window, text="Form HTML Editor")
        bottom_paned_window.add(self.xml_frame, weight=2)
        self.xml_frame.rowconfigure(1, weight=1)
        self.xml_frame.columnconfigure(0, weight=1)
        self.xml_frame.columnconfigure(1, weight=1)
        self.xml_frame.columnconfigure(2, weight=1)

        # JSON display section (right pane of bottom)
        self.json_frame = ttk.LabelFrame(bottom_paned_window, text="Generated JSON (editable)")
        bottom_paned_window.add(self.json_frame, weight=1)
        self.json_frame.rowconfigure(1, weight=1)
        self.json_frame.columnconfigure(0, weight=1)
        self.json_frame.columnconfigure(1, weight=1)
        self.json_frame.columnconfigure(2, weight=1)

        # --- Widgets inside the frames ---

        self.convert_btn = ttk.Button(self.forms_frame, text="Convert Selected Form", command=self.convert_selected_form)
        self.convert_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        # --- Checkbox list for forms ---
        self.forms_canvas = tk.Canvas(self.forms_frame)
        self.forms_scrollbar = ttk.Scrollbar(self.forms_frame, orient="vertical", command=self.forms_canvas.yview)
        self.scrollable_forms_frame = ttk.Frame(self.forms_canvas)
        self.scrollable_forms_frame.bind("<Configure>", lambda e: self.forms_canvas.configure(scrollregion=self.forms_canvas.bbox("all")))
        self.forms_canvas.create_window((0, 0), window=self.scrollable_forms_frame, anchor="nw")
        self.forms_canvas.configure(yscrollcommand=self.forms_scrollbar.set)
        self.forms_canvas.grid(row=1, column=0, sticky="nsew")
        self.forms_scrollbar.grid(row=1, column=1, sticky="ns")

        # Add Download HTML button above the HTML form display box
        self.download_html_btn = ttk.Button(self.xml_frame, text="Download HTML", command=self.download_html)
        self.download_html_btn.grid(row=0, column=0, sticky="ew", padx=(5,2), pady=(5, 2))

        # Add Upload HTML and Convert Displayed HTML buttons above the HTML form display
        self.upload_html_btn = ttk.Button(self.xml_frame, text="Upload HTML", command=self.upload_html)
        self.upload_html_btn.grid(row=0, column=1, sticky="ew", padx=(2,2), pady=(5, 2))

        self.convert_displayed_btn = ttk.Button(self.xml_frame, text="Convert Displayed HTML to JSON", command=self.convert_displayed_html)
        self.convert_displayed_btn.grid(row=0, column=2, sticky="ew", padx=(2,5), pady=(5, 2))

        # Move the text widget and scrollbar down by one row
        self.xml_text = Text(self.xml_frame, wrap="none", undo=True, bg="#2b2b2b", fg="#a9b7c6", insertbackground="white")
        self.xml_text.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        self.xml_scrollbar = ttk.Scrollbar(self.xml_frame, orient=VERTICAL, command=self.xml_text.yview)
        self.xml_scrollbar.grid(row=1, column=3, sticky="ns")
        self.xml_text.config(yscrollcommand=self.xml_scrollbar.set)

        # --- Add Syntax Highlighting ---
        # Dark mode syntax highlighting (inspired by IDE themes)
        self.xml_text.tag_configure("tag", foreground="#e8bf6a")       # Yellow for tags
        self.xml_text.tag_configure("attribute", foreground="#9876aa") # Purple for attributes
        self.xml_text.tag_configure("string", foreground="#6a8759")     # Green for strings
        self.xml_text.tag_configure("comment", foreground="#808080")    # Grey for comments
        self.xml_text.tag_configure("keyword", foreground="#cc7832")    # Orange for JSON keywords (true, false, null)
        self.xml_text.tag_configure("number", foreground="#6897bb")     # Blue for numbers

        self.xml_text.tag_raise("sel")

        self.xml_text.bind("<KeyRelease>", self._on_key_release)

        # Button sub-frame for better organization
        button_sub_frame = ttk.Frame(self.json_frame)
        button_sub_frame.grid(row=0, column=0, columnspan=3, sticky="ew")

        self.generate_concepts_btn = ttk.Button(button_sub_frame, text="Generate Concepts Excel", command=self.generate_concepts_excel)
        self.generate_concepts_btn.grid(row=0, column=0, sticky="ew", padx=(5,2), pady=(5, 2))

        self.generate_selected_concepts_btn = ttk.Button(button_sub_frame, text="Generate Excel for Selected", command=self.generate_selected_concepts_excel)
        self.generate_selected_concepts_btn.grid(row=0, column=1, sticky="ew", padx=(2,2), pady=(5, 2))

        self.download_json_btn = ttk.Button(self.json_frame, text="Download JSON", command=self.download_json)
        self.download_json_btn.grid(row=0, column=2, sticky="ew", padx=(2,5), pady=(5, 2)) # This was in json_frame, now in button_sub_frame
        
        self.json_text = Text(self.json_frame, wrap="none", bg="#2b2b2b", fg="#a9b7c6", insertbackground="white")
        self.json_text.grid(row=1, column=0, columnspan=3, sticky="nsew")
        self.json_scrollbar = ttk.Scrollbar(self.json_frame, orient=VERTICAL, command=self.json_text.yview)
        self.json_scrollbar.grid(row=1, column=3, sticky="ns")
        self.json_text.config(yscrollcommand=self.json_scrollbar.set, undo=True)

    def _on_key_release(self, event=None):
        """Callback for syntax highlighting on key release."""
        # Determine which widget triggered the event
        widget = event.widget
        if widget == self.xml_text:
            self.highlight_syntax(widget, 'html')
        elif widget == self.json_text:
            self.highlight_syntax(widget, 'json')

    def highlight_syntax(self, widget, language):
        """Applies syntax highlighting to a text widget."""
        content = widget.get("1.0", "end-1c")
        
        # Remove all tags first
        for tag in ["tag", "attribute", "string", "comment", "keyword", "number"]:
            widget.tag_remove(tag, "1.0", END)

        if language == 'html':
            # Regex for HTML parts
            tag_regex = r"<\/?\w+\b"
            attr_regex = r"\b\w+(?=\s*=)"
            string_regex = r"\".*?\""
            comment_regex = r"<!--.*?-->"

            self._apply_tag_to_regex(widget, content, tag_regex, "tag")
            self._apply_tag_to_regex(widget, content, attr_regex, "attribute")
            self._apply_tag_to_regex(widget, content, string_regex, "string")
            self._apply_tag_to_regex(widget, content, comment_regex, "comment", re.DOTALL)

        elif language == 'json':
            # Regex for JSON parts
            string_regex = r"\".*?\""
            number_regex = r"\b-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?\b"
            keyword_regex = r"\b(true|false|null)\b"

            self._apply_tag_to_regex(widget, content, string_regex, "string")
            self._apply_tag_to_regex(widget, content, number_regex, "number")
            self._apply_tag_to_regex(widget, content, keyword_regex, "keyword")


    def _add_db_widgets(self):
        labels = ["Host", "Port", "User", "Password", "Database"]
        self.db_entries = {}
        defaults = {"host": "localhost", "port": "3306", "user": "root", "password": "root", "database": "openmrs"}
        for i, label in enumerate(labels):
            ttk.Label(self.db_frame, text=label).grid(row=i, column=0, sticky="w")
            entry = ttk.Entry(self.db_frame, show="*" if label == "Password" else "")
            entry.insert(0, defaults[label.lower()])
            entry.grid(row=i, column=1, padx=5, pady=2)
            self.db_entries[label.lower()] = entry
        self.connect_btn = ttk.Button(self.db_frame, text="Connect", command=self.connect_to_db)
        self.connect_btn.grid(row=len(labels), column=0, columnspan=2, pady=5)

    def _add_concept_widgets(self):
        self.concept_search_var = tk.StringVar()
        self.concept_search_entry = ttk.Entry(self.concept_frame, textvariable=self.concept_search_var, width=40)
        self.concept_search_entry.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.concept_search_btn = ttk.Button(self.concept_frame, text="Search", command=self.on_concept_search)
        self.concept_search_btn.grid(row=0, column=1, padx=5, pady=5)
        self.concept_frame.rowconfigure(1, weight=1)
        self.concept_info_text = Text(self.concept_frame, width=70, wrap="word")
        self.concept_info_text.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        self.concept_info_text.config(state="disabled")
        self.concept_info_text.tag_configure("ocl_link", foreground="blue", underline=True)

    def upload_comparison_json(self, json_num):
        """Handles uploading JSON files for comparison."""
        file_path = filedialog.askopenfilename(
            title=f"Select JSON File {json_num}",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if json_num == 1:
                self.json1_data = data
                self.json1_path.set(os.path.basename(file_path))
            else:
                self.json2_data = data
                self.json2_path.set(os.path.basename(file_path))
            messagebox.showinfo("Success", f"JSON {json_num} loaded successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load or parse JSON {json_num}:\n{e}")

    def _get_questions_map(self, json_data):
        """Helper to create a map of id -> question object from a form JSON."""
        q_map = {}
        if not json_data or "pages" not in json_data:
            return q_map
        for page in json_data.get("pages", []):
            for section in page.get("sections", []):
                for question in section.get("questions", []):
                    if "id" in question:
                        q_map[question["id"]] = question
        return q_map

    def _get_questions_map_by_label(self, json_data):
        """Helper to create a map of label -> question object from a form JSON."""
        q_map = {}
        if not json_data or "pages" not in json_data:
            return q_map
        for page in json_data.get("pages", []):
            for section in page.get("sections", []):
                for question in section.get("questions", []):
                    if "label" in question:
                        q_map[question["label"]] = question
        return q_map

    def compare_jsons(self):
        """Compares two loaded JSON files and generates an Excel report of differences."""
        if not self.json1_data or not self.json2_data:
            messagebox.showwarning("Missing Files", "Please upload both JSON 1 and JSON 2 before comparing.")
            return

        map1 = self._get_questions_map_by_label(self.json1_data)
        map2 = self._get_questions_map_by_label(self.json2_data)

        wb = Workbook()
        wb.remove(wb.active) # Remove default sheet

        # Sheet 1: Comparison
        ws_compare = wb.create_sheet("Comparison")
        compare_headers = ["Question1", "Question2", "json1concept", "json2concept", "Status"]
        ws_compare.append(compare_headers)
        for header_cell in ws_compare[1]:
            header_cell.font = Font(bold=True)

        # Sheet 2: Only in JSON1
        ws_json1_only = wb.create_sheet("Only in JSON1")
        unique_headers = ["Question", "Concept"]
        ws_json1_only.append(unique_headers)
        for header_cell in ws_json1_only[1]:
            header_cell.font = Font(bold=True)

        # Sheet 3: Only in JSON2
        ws_json2_only = wb.create_sheet("Only in JSON2")
        ws_json2_only.append(unique_headers)
        for header_cell in ws_json2_only[1]:
            header_cell.font = Font(bold=True)

        all_labels = sorted(list(set(map1.keys()) | set(map2.keys())))

        for label in all_labels:
            q1 = map1.get(label)
            q2 = map2.get(label)
            
            if q1 and q2: # Exists in both
                concept1 = q1.get("questionOptions", {}).get("concept")
                concept2 = q2.get("questionOptions", {}).get("concept")
                if concept1 != concept2:
                    ws_compare.append([label, label, concept1, concept2, "Concept Mismatch"])
                else:
                    ws_compare.append([label, label, concept1, concept2, "Same"])
            elif q1 and not q2: # Only in JSON 1
                ws_json1_only.append([label, q1.get("questionOptions", {}).get("concept")])
            elif not q1 and q2: # Only in JSON 2
                ws_json2_only.append([label, q2.get("questionOptions", {}).get("concept")])

        # Auto-size columns
        for ws in wb.worksheets:
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = (max_length + 2)
                ws.column_dimensions[column].width = adjusted_width

        try:
            output_dir = os.path.join(os.getcwd(), "converted")
            os.makedirs(output_dir, exist_ok=True)
            
            base_filename = os.path.splitext(self.json1_path.get())[0]
            excel_filename = f"{base_filename}-Compared.xlsx"
            file_path = os.path.join(output_dir, excel_filename)
            
            wb.save(file_path)
            messagebox.showinfo("Success", f"Comparison report saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save Excel file:\n{e}")

    def merge_and_download_json(self):
        """Updates JSON1 with concepts from JSON2 and prompts for download."""
        if not self.json1_data or not self.json2_data:
            messagebox.showwarning("Missing Files", "Please upload both JSON 1 and JSON 2 before merging.")
            return

        map2 = self._get_questions_map_by_label(self.json2_data)
        json1_updated = json.loads(json.dumps(self.json1_data)) # Deep copy

        for page in json1_updated.get("pages", []):
            for section in page.get("sections", []):
                for question in section.get("questions", []):
                    q_label = question.get("label")
                    # Check if the same question label exists in JSON2 and has a concept
                    if q_label in map2 and "concept" in map2[q_label].get("questionOptions", {}):
                        # Update the concept in our copy of JSON1
                        question["questionOptions"]["concept"] = map2[q_label]["questionOptions"]["concept"]
        
        try:
            original_name = self.json1_path.get().replace('.json', '')
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json", 
                filetypes=[("JSON Files", "*.json")], 
                title="Save Merged JSON File",
                initialfile=f"{original_name}_Updated.json"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(json1_updated, f, indent=2)
                messagebox.showinfo("Success", f"Merged JSON file saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save merged JSON file:\n{e}")

    def connect_to_db(self, auto=False):
        try:
            self.connection = mysql.connector.connect(
                host=self.db_entries["host"].get(),
                port=int(self.db_entries["port"].get()),
                user=self.db_entries["user"].get(),
                password=self.db_entries["password"].get(),
                database=self.db_entries["database"].get()
            )
            if not auto:
                messagebox.showinfo("Success", "Connected to database.")
            self.fetch_forms()
        except mysql.connector.Error as err:
            if not auto:
                messagebox.showerror("Error", f"Database connection failed:\n{err}")

    def fetch_forms(self):
        cursor = self.connection.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT 
                h.form_id, 
                f.name,
                et.uuid as encounter_type_uuid
            FROM htmlformentry_html_form h
            JOIN form f ON h.form_id = f.form_id
            LEFT JOIN encounter_type et ON f.encounter_type = et.encounter_type_id
        """)
        self.forms = cursor.fetchall()
        
        # Clear previous widgets
        for widget in self.scrollable_forms_frame.winfo_children():
            widget.destroy()
        self.form_checkboxes.clear()

        for i, form in enumerate(self.forms):
            var = tk.IntVar()
            cb = ttk.Checkbutton(self.scrollable_forms_frame, text=f"{form['form_id']}: {form['name']}", variable=var)
            cb.grid(row=i, column=0, sticky='w', padx=5)
            cb.bind("<Button-1>", lambda e, index=i: self.on_form_select(index))
            self.form_checkboxes.append({'var': var, 'form': form})

        cursor.close()

    def on_form_select(self, index):
        """Loads the HTML for a form when its checkbox label is clicked."""
        self.selected_form_index = index
        form = self.forms[self.selected_form_index]
        xml_data = self.fetch_form_html(form['form_id'])
        self.xml_text.delete(1.0, END)
        self.xml_text.insert(END, xml_data if xml_data else "(No xml_data found)")
        self.highlight_syntax(self.xml_text, 'html') # Highlight after loading


    def convert_selected_form(self):
        if self.selected_form_index is None:
            messagebox.showwarning("No Selection", "Please select a form to convert.")
            return
        form = self.forms[self.selected_form_index]
        html = self.fetch_form_html(form['form_id'])
        if not html:
            messagebox.showerror("Error", "No HTML found for this form.")
            return
        soup = BeautifulSoup(html, 'html.parser')
        concept_ids = set()
        for obs in soup.find_all("obs"):
            cid = obs.get("conceptid")
            if cid and cid.isdigit():
                concept_ids.add(int(cid))
            # Also collect answerConceptIds
            answer_ids = []
            if obs.get("answers"):
                answer_ids = [a.strip() for a in obs.get("answers").split(",")]
            elif obs.get("answerconceptids"):
                answer_ids = [a.strip() for a in obs.get("answerconceptids").split(",")]
            elif obs.get("answerconceptid"):
                answer_ids = [obs.get("answerconceptid").strip()]
            for aid in answer_ids:
                if aid.isdigit():
                    concept_ids.add(int(aid))
        # Now fetch all concepts at once
        self.fetch_concepts_from_db(concept_ids)
        self.generate_outputs(soup, form['name'], form.get('encounter_type_uuid'))

    def generate_selected_concepts_excel(self):
        selected_forms = [cb['form'] for cb in self.form_checkboxes if cb['var'].get() == 1]

        if not selected_forms:
            messagebox.showwarning("No Forms Selected", "Please check the boxes for the forms you want to process.")
            return

        # --- Progress Bar Setup ---
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Generating...")
        progress_win.geometry("400x120")
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        status_var = tk.StringVar()
        status_var.set("Initializing...")
        
        ttk.Label(progress_win, textvariable=status_var, wraplength=380).pack(pady=5)
        progress_bar = ttk.Progressbar(progress_win, orient="horizontal", length=350, mode="determinate")
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(selected_forms)

        # 1. Pre-scan all forms to find all concept IDs and map concepts to forms
        all_concept_ids = set()
        concept_to_forms = {}  # {concept_id: {form_name1, form_name2}}
        form_data = [] # Store (form_name, soup) tuples

        for i, form_info in enumerate(selected_forms):
            try:
                form_name = form_info['name']
                status_var.set(f"Processing ({i+1}/{len(selected_forms)}): {form_name}")
                progress_bar["value"] = i + 1
                progress_win.update_idletasks()
                form_id = form_info['form_id']
                html = self.fetch_form_html(form_id)
                if not html:
                    print(f"Skipping form '{form_name}' (ID: {form_id}) as it has no HTML content.")
                    continue
            except Exception as e:
                print(f"An error occurred while fetching form '{form_name}' (ID: {form_id}): {e}")
                messagebox.showwarning("Form Fetch Error", f"Could not fetch HTML for form: {form_name}.\n\nError: {e}\n\nSkipping to the next form.")
                continue

            soup = BeautifulSoup(html, 'html.parser')
            form_data.append((form_name, soup))
            obs_tags = soup.find_all("obs")

            for obs in obs_tags:
                # Question concept
                q_cid_str = obs.get("conceptid")
                if q_cid_str and q_cid_str.isdigit():
                    q_cid = int(q_cid_str)
                    all_concept_ids.add(q_cid)
                    if q_cid not in concept_to_forms:
                        concept_to_forms[q_cid] = set()
                    concept_to_forms[q_cid].add(form_name)

                # Answer concepts
                answer_sources = ["answerconceptids", "answerconceptid", "answers"]
                for source in answer_sources:
                    answer_ids_str = obs.get(source)
                    if answer_ids_str:
                        for aid in answer_ids_str.split(','):
                            if aid.strip().isdigit():
                                all_concept_ids.add(int(aid.strip()))

        # 2. Fetch all concept details in one go
        self.fetch_concepts_from_db(all_concept_ids)

        # 3. Create and populate the Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "All Concepts"
        headers = [
            "Form Name", "Concept", "2.x Question with Concepts", "2.x Question text", "HTML Question Text",
            "3.x Question (Concept) UUID", "Answer", "2.x Answers with their Concepts", "2.x Answer text",
            "2.x Answer Type", "Answer UUID", "Found in Other Forms"
        ]
        ws.append(headers)

        # 4. Iterate through each form's stored soup and populate rows
        for form_name, soup in form_data:
            self._populate_concepts_sheet(ws, soup, form_name, concept_to_forms)

        # 5. Save the file
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, "All_Forms_Concepts.xlsx")

        try:
            wb.save(excel_path)
            progress_win.destroy()
            messagebox.showinfo("Success", f"Consolidated concepts Excel file generated at:\n{excel_path}")
        except Exception as e:
            progress_win.destroy()
            messagebox.showerror("Error", f"Failed to save Excel file:\n{e}")



    def generate_concepts_excel(self):
        if self.selected_form_index is None:
            messagebox.showwarning("No Selection", "Please select a form to generate concepts from.")
            return

        form = self.forms[self.selected_form_index]
        form_name = form['name']
        html = self.fetch_form_html(form['form_id'])
        if not html:
            messagebox.showerror("Error", f"No HTML found for form: {form_name}")
            return

        soup = BeautifulSoup(html, 'html.parser')

        # 1. Collect all concept IDs from the form
        all_concept_ids = set()
        obs_tags = soup.find_all("obs")
        for obs in obs_tags:
            # Question concept
            q_cid = obs.get("conceptid")
            if q_cid and q_cid.isdigit():
                all_concept_ids.add(int(q_cid))

            # Answer concepts
            answer_sources = ["answerconceptids", "answerconceptid", "answers"]
            for source in answer_sources:
                answer_ids_str = obs.get(source)
                if answer_ids_str:
                    for aid in answer_ids_str.split(','):
                        if aid.strip().isdigit():
                            all_concept_ids.add(int(aid.strip()))

        # 2. Fetch all concept details in one go
        self.fetch_concepts_from_db(all_concept_ids)

        # 3. Create and populate the Excel workbook and headers
        wb = Workbook()
        ws = wb.active
        ws.title = "Concepts"
        headers = [ # Added Form Name and Duplicate columns
            "Form Name", "Concept", "2.x Question with Concepts", "2.x Question text", 
            "HTML Question Text", "3.x Question (Concept) UUID", "Answer", 
            "2.x Answers with their Concepts", "2.x Answer text", "2.x Answer Type", 
            "Answer UUID", "Found in Other Forms"
        ]
        ws.append(headers)

        # Pre-scan to find where concepts are used for the "Found in Other Forms" column
        concept_to_forms = {}
        for obs in obs_tags:
            q_cid_str = obs.get("conceptid")
            if q_cid_str and q_cid_str.isdigit():
                q_cid = int(q_cid_str)
                if q_cid not in concept_to_forms:
                    concept_to_forms[q_cid] = {form_name} # Use a set for uniqueness
                else:
                    concept_to_forms[q_cid].add(form_name)

        # 4. Populate the sheet using the helper method
        self._populate_concepts_sheet(ws, soup, form_name, concept_to_forms)

        # 5. Save the file
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        safe_form_name = "".join(c for c in form_name if c.isalnum() or c in " ._-").rstrip()
        excel_path = os.path.join(output_dir, f"{safe_form_name}_Concepts.xlsx")
        
        try:
            wb.save(excel_path)
            messagebox.showinfo("Success", f"Concepts Excel file generated at:\n{excel_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save Excel file:\n{e}")

    def _populate_concepts_sheet(self, ws, soup, form_name, concept_to_forms):
        """Helper method to populate a worksheet with concepts from a given soup."""
        obs_tags = soup.find_all("obs")
        is_first_answer = True

        for obs in obs_tags:
            q_cid_str = obs.get("conceptid")
            if not (q_cid_str and q_cid_str.isdigit()):
                continue

            if int(q_cid_str) not in self.concept_map:
                print(f"Warning: Question concept ID '{q_cid_str}' from form '{form_name}' not seen in dictionary. Ignoring this <obs> tag.")
                continue

            q_cid = int(q_cid_str)
            q_info = self.concept_map.get(q_cid, {})
            q_name = q_info.get("name", f"Unknown Concept {q_cid}")
            q_uuid = q_info.get("uuid", "N/A")

            # --- Extract HTML Question Text ---
            html_question_text = ""
            parent_td = obs.find_parent('td')
            if parent_td:
                # Check for label in the preceding sibling td
                prev_td = parent_td.find_previous_sibling('td')
                if prev_td and prev_td.text.strip():
                    html_question_text = prev_td.text.strip().rstrip(':')
                else:
                    # If not in prev_td, get text from the current td, excluding obs children
                    text_nodes = parent_td.find_all(string=True, recursive=False)
                    html_question_text = ' '.join(node.strip() for node in text_nodes).strip()
            html_question_text = html_question_text or obs.get('labelText', '') or q_name

            # --- Identify other forms using this concept ---
            other_forms = concept_to_forms.get(q_cid, set()) - {form_name}
            found_in_others_text = ", ".join(sorted(list(other_forms))) if other_forms else "No"

            # Reset for each new question
            is_first_answer = True

            # Collect all unique answer concept IDs for this question
            answer_concept_ids = set()
            answer_sources = ["answerconceptids", "answerconceptid", "answers"]
            for source in answer_sources:
                answer_ids_str = obs.get(source)
                if answer_ids_str:
                    for aid in answer_ids_str.split(','):
                        if aid.strip().isdigit():
                            answer_concept_ids.add(int(aid.strip()))

            # If the question's datatype is 'Coded', also get its answers from the database
            if self.concept_datatypes.get(q_cid) == 'coded' and not answer_concept_ids:
                db_answers = self.concept_answers.get(q_cid, [])
                for ans in db_answers:
                    ans_cid = "N/A" # Cannot easily reverse-lookup UUID to concept_id here
                    q_data = [form_name, "Concept", q_cid, q_name, html_question_text, q_uuid] if is_first_answer else ["", "", "", "", "", ""]
                    ans_data = ["Answer", ans_cid, ans.get("label"), "Coded", ans.get("uuid"), found_in_others_text if is_first_answer else ""]
                    ws.append(q_data + ans_data)
                    is_first_answer = False

            # If there were no answers, add a single row for the question itself
            if not answer_concept_ids and self.concept_datatypes.get(q_cid) != 'coded':
                q_datatype = self.concept_datatypes.get(q_cid, "N/A")
                if is_first_answer:
                    ws.append([form_name, "Concept", q_cid, q_name, html_question_text, q_uuid, "", "", "", q_datatype.capitalize(), "", found_in_others_text])
                    is_first_answer = False

            # Process the collected answer IDs
            else:
                # Validate answer concepts before processing
                valid_answer_ids = {aid for aid in answer_concept_ids if aid in self.concept_map}
                invalid_answer_ids = answer_concept_ids - valid_answer_ids
                if invalid_answer_ids:
                    print(f"Warning: Answer concept IDs {invalid_answer_ids} for question '{q_name}' not seen in dictionary. They will be skipped.")

                for a_cid in sorted(list(answer_concept_ids)): # Sort for consistent order
                    a_info = self.concept_map.get(a_cid, {})
                    a_name = a_info.get("name", f"Unknown Concept {a_cid}")
                    a_uuid = a_info.get("uuid", "N/A")
                    a_datatype = self.concept_datatypes.get(a_cid, "N/A")

                    q_data = [form_name, "Concept", q_cid, q_name, html_question_text, q_uuid] if is_first_answer else ["", "", "", "", "", ""]
                    ws.append(q_data + ["Answer", a_cid, a_name, a_datatype.capitalize(), a_uuid, found_in_others_text if is_first_answer else ""])
                    is_first_answer = False

    def fetch_form_html(self, form_id):
        cursor = self.connection.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT xml_data FROM htmlformentry_html_form WHERE form_id = %s", (form_id,))
        row = cursor.fetchone()
        cursor.close()
        return row['xml_data'] if row else ""

    def fetch_concepts_from_db(self, concept_ids):
        if not concept_ids:
            self.concept_map = {}
            self.concept_datatypes = {}
            self.concept_numeric = {}
            self.concept_answers = {}
            return
        cursor = self.connection.cursor(dictionary=True, buffered=True)
        placeholders = ",".join(["%s"] * len(concept_ids))
        # Fetch concept uuid and name
        cursor.execute(
            f"SELECT c.concept_id, c.uuid, n.name FROM concept c JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale = 'en' WHERE c.concept_id IN ({placeholders})",
            list(concept_ids)
        )
        self.concept_map = {row["concept_id"]: {"uuid": row["uuid"], "name": row["name"]} for row in cursor.fetchall()}
        # Fetch concept datatype
        cursor.execute(
            f"SELECT c.concept_id, dt.name as datatype FROM concept c JOIN concept_datatype dt ON c.datatype_id = dt.concept_datatype_id WHERE c.concept_id IN ({placeholders})",
            list(concept_ids)
        )
        self.concept_datatypes = {row["concept_id"]: row["datatype"].lower() for row in cursor.fetchall()}
        # Fetch concept numeric
        cursor.execute(
            f"SELECT concept_id, hi_absolute, low_absolute FROM concept_numeric WHERE concept_id IN ({placeholders})",
            list(concept_ids)
        )
        self.concept_numeric = {row["concept_id"]: {"hi_absolute": row["hi_absolute"], "low_absolute": row["low_absolute"]} for row in cursor.fetchall()}
        # Fetch concept answers
        cursor.execute(
            f"SELECT ca.concept_id, ca.answer_concept, n.name as answer_label, c.uuid as answer_uuid FROM concept_answer ca JOIN concept c ON ca.answer_concept = c.concept_id JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale = 'en' WHERE ca.concept_id IN ({placeholders})",
            list(concept_ids)
        )
        self.concept_answers = {}
        for row in cursor.fetchall():
            if row["concept_id"] not in self.concept_answers:
                self.concept_answers[row["concept_id"]] = []
            self.concept_answers[row["concept_id"]].append({"label": row["answer_label"], "uuid": row["answer_uuid"]})

        # Fetch concept class and description for OCL export
        cursor.execute(
            f"""SELECT c.concept_id, cc.name as concept_class, cd.description
                FROM concept c
                LEFT JOIN concept_class cc ON c.class_id = cc.concept_class_id
                LEFT JOIN concept_description cd ON c.concept_id = cd.concept_id AND cd.locale = 'en'
                WHERE c.concept_id IN ({placeholders})
            """,
            list(concept_ids)
        )
        for row in cursor.fetchall():
            if row['concept_id'] in self.concept_map:
                self.concept_map[row['concept_id']]['concept_class'] = row.get('concept_class')
                self.concept_map[row['concept_id']]['description'] = row.get('description')
        cursor.close()

    def on_concept_search(self, event=None):
        search = self.concept_search_var.get().strip()
        self.concept_info_text.config(state="normal")
        self.concept_info_text.delete(1.0, END)
        if not search:
            self.concept_info_text.config(state="disabled")
            return
        cursor = self.connection.cursor(dictionary=True, buffered=True)
        results = []
        # Numeric or UUID search
        if re.fullmatch(r'\d+', search):
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE c.concept_id = %s
                LIMIT 1
            """, (int(search),))
            results = cursor.fetchall()
        elif re.fullmatch(r'[0-9a-fA-F-]{36}', search):
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE c.uuid = %s
                LIMIT 1
            """, (search,))
            results = cursor.fetchall()
        else:
            # Text search in name and description
            cursor.execute("""
                SELECT c.concept_id, c.uuid, n.name, d.description
                FROM concept c
                LEFT JOIN concept_name n ON c.concept_id = n.concept_id AND n.locale='en'
                LEFT JOIN concept_description d ON c.concept_id = d.concept_id AND d.locale='en'
                WHERE n.name LIKE %s OR d.description LIKE %s
                LIMIT 20
            """, (f"%{search}%", f"%{search}%"))
            results = cursor.fetchall()
        if results:
            for row in results:
                self.concept_info_text.insert(END, f"Concept ID: {row['concept_id']}\nUUID: {row['uuid']}\nName: {row.get('name','')}\nDescription: {row.get('description','')}\n{'-'*40}\n")
        else:
            self.concept_info_text.insert(END, "No concept found.")
        cursor.close()
        self.fetch_ocl_concepts(search)
        self.concept_info_text.config(state="disabled")

    def fetch_ocl_concepts(self, search_term):
        """Fetches concepts from Open Concept Lab (OCL) and displays them."""
        ocl_url = f"https://api.openconceptlab.org/orgs/NMRS/sources/NMRS/concepts/?q={search_term}&limit=10"
        try:
            response = requests.get(ocl_url)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            data = response.json()

            self.concept_info_text.config(state="normal")
            self.concept_info_text.insert(END, "\n\n--- OCL Results ---\n")

            if data:
                for result in data:
                    name = result.get("display_name", "N/A")
                    concept_url = result.get("url")
                    tag_name = f"ocl_link_{concept_url}"
                    self.concept_info_text.insert(END, f"{name}\n", (tag_name, "ocl_link"))
                    self.concept_info_text.tag_bind(tag_name, "<Button-1>", lambda e, url=concept_url: self.open_ocl_concept_details(url))
            else:
                self.concept_info_text.insert(END, "No concepts found on OCL.\n")
        except requests.exceptions.RequestException as e:
            self.concept_info_text.insert(END, f"\nError fetching from OCL: {e}\n")
        finally:
            self.concept_info_text.config(state="disabled")

    def _apply_tag_to_regex(self, widget, content, regex, tag_name, flags=0):
        """Helper to find all matches of a regex and apply a tag."""
        for match in re.finditer(regex, content, flags):
            start = match.start()
            end = match.end()
            widget.tag_add(tag_name, f"1.0+{start}c", f"1.0+{end}c")

    def open_ocl_concept_details(self, concept_url):
        """Opens a new window to display detailed information about an OCL concept."""
        if not concept_url:
            return
        # The API URL is like /orgs/NMRS/sources/NMRS/concepts/NMRS_2195/
        # The UI URL is https://app.openconceptlab.org/#/orgs/NMRS/sources/NMRS/concepts/NMRS_2195/
        full_ui_url = f"https://app.openconceptlab.org/#{concept_url}"
        webbrowser.open_new_tab(full_ui_url)


    def deduplicate_answers(self, answers):
        """Remove duplicate answers with same concept, keeping the first occurrence."""
        seen_concepts = {}
        unique_answers = []
        
        for answer in answers:
            concept = answer["concept"]
            if concept not in seen_concepts:
                seen_concepts[concept] = True
                unique_answers.append(answer)
        
        return unique_answers

    def process_encounter_elements(self, container, section):
        """Process encounter elements in any container"""
        for element in container.find_all(['encounterDate', 'encounterProvider', 'encounterLocation'], recursive=True):
            qid = f"{element.name.lower()}_{self.id_counter}"
            self.id_counter += 1
            
            # Get label from previous td
            label = None
            prev_td = element.find_parent('td')
            if prev_td:
                label_td = prev_td.find_previous_sibling('td')
                if label_td:
                    label = label_td.text.strip().rstrip(':')

            if element.name == 'encounterDate':
                question = {
                    "id": qid,
                    "label": label or "Visit Date",
                    "type": "encounterDate",
                    "questionOptions": {
                        "rendering": "date",
                        "showTime": element.get("showTime", "false"),
                        "allowFutureDates": element.get("allowFutureDates", "false")
                    }
                }
                section["questions"].append(question)
                
            elif element.name == 'encounterProvider':
                question = {
                    "id": qid,
                    "label": label or "Provider",
                    "type": "encounterProvider",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "currentUser":
                    question["default"] = "currentUser"
                section["questions"].append(question)
                
            elif element.name == 'encounterLocation':
                question = {
                    "id": qid,
                    "label": label or "Facility",
                    "type": "encounterLocation",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "SessionAttribute:emrContext.sessionLocationId":
                    question["default"] = "SessionAttribute:emrContext.sessionLocationId"
                section["questions"].append(question)

    def process_fieldset_elements(self, fieldset, current_section):
        """Process both obs and encounter elements in a fieldset"""
        
        # First process encounter elements
        for element in fieldset.find_all(['encounterDate', 'encounterProvider', 'encounterLocation']):
            qid = f"{element.name.lower()}_{self.id_counter}"
            self.id_counter += 1
            
            # Get label from previous td
            label = None
            prev_td = element.find_parent('td')
            if prev_td:
                label_td = prev_td.find_previous_sibling('td')
                if label_td:
                    label = label_td.text.strip().rstrip(':')
            
            if element.name == 'encounterDate':
                question = {
                    "id": qid,
                    "label": label or "Visit Date",
                    "type": "encounterDate",
                    "questionOptions": {
                        "rendering": "date",
                        "showTime": element.get("showTime", "false"),
                        "allowFutureDates": element.get("allowFutureDates", "false")
                    }
                }
                current_section["questions"].append(question)
                
            elif element.name == 'encounterProvider':
                question = {
                    "id": qid,
                    "label": label or "Provider",
                    "type": "encounterProvider",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "currentUser":
                    question["default"] = "currentUser"
                current_section["questions"].append(question)
                
            elif element.name == 'encounterLocation':
                question = {
                    "id": qid,
                    "label": label or "Facility",
                    "type": "encounterLocation",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "SessionAttribute:emrContext.sessionLocationId":
                    question["default"] = "SessionAttribute:emrContext.sessionLocationId"
                current_section["questions"].append(question)

    def process_root_encounters(self, soup, json_form):
        """Process encounter elements at the root level"""
        # Look for table with encounter elements at root level
        root_encounters = soup.find_all(['encounterDate', 'encounterProvider', 'encounterLocation'], recursive=False)
        root_tables = soup.find_all('table', recursive=False)
        
        for table in root_tables:
            root_encounters.extend(table.find_all(['encounterDate', 'encounterProvider', 'encounterLocation']))
        
        if root_encounters:
            general_section = {
                "label": "General Information",
                "questions": []
            }
            
            for element in root_encounters:
                qid = f"{element.name.lower()}_{self.id_counter}"
                self.id_counter += 1
                
                # Get label from previous td
                label = None
                prev_td = element.find_parent('td')
                if prev_td and prev_td.find_previous_sibling('td'):
                    label = prev_td.find_previous_sibling('td').text.strip()
                
                if element.name == 'encounterDate':
                    question = {
                        "id": qid,
                        "label": label or "Visit Date",
                        "type": "encounterDate",
                        "questionOptions": {
                            "rendering": "date",
                            "showTime": element.get("showTime", "false"),
                            "allowFutureDates": element.get("allowFutureDates", "false")
                        }
                    }
                    general_section["questions"].append(question)
                
                elif element.name == 'encounterProvider':
                    question = {
                        "id": qid,
                        "label": label or "Provider",
                        "type": "encounterProvider",
                        "questionOptions": {
                            "rendering": "ui-select-extended"
                        }
                    }
                    if element.get("default") == "currentUser":
                        question["default"] = "currentUser"
                    general_section["questions"].append(question)
                
                elif element.name == 'encounterLocation':
                    question = {
                        "id": qid,
                        "label": label or "Facility",
                        "type": "encounterLocation",
                        "questionOptions": {
                            "rendering": "ui-select-extended"
                        }
                    }
                    if element.get("default") == "SessionAttribute:emrContext.sessionLocationId":
                        question["default"] = "SessionAttribute:emrContext.sessionLocationId"
                    general_section["questions"].append(question)
            
            # Add section to form if it has questions
            if general_section["questions"]:
                if not json_form["pages"]:
                    json_form["pages"].append({
                        "label": "General Information",
                        "sections": []
                    })
                json_form["pages"][0]["sections"].append(general_section)

    def process_all_encounter_elements(self, soup, json_form):
        """Find all encounter* elements anywhere in the form and add them as questions if not already present."""
        encounter_tags = [
            tag for tag in soup.find_all(True)
            if tag.name.lower().startswith("encounter")
        ]
        if not encounter_tags:
            return

        # Put all in a "General Information" section if not already present
        general_section = None
        for page in json_form["pages"]:
            for section in page["sections"]:
                if section["label"] == "General Information":
                    general_section = section
                    break
        if not general_section:
            general_section = {"label": "General Information", "questions": []}
            if not json_form["pages"]:
                json_form["pages"].append({"label": "General Information", "sections": [general_section]})
            else:
                json_form["pages"][0]["sections"].insert(0, general_section)

        for element in encounter_tags:
            qid = f"{element.name.lower()}_{self.id_counter}"
            self.id_counter += 1

            # Try to get label from previous sibling td
            label = None
            prev_td = element.find_parent('td')
            if prev_td:
                label_td = prev_td.find_previous_sibling('td')
                if label_td:
                    label = label_td.text.strip().rstrip(':')

            # Build the question according to type
            if element.name.lower() == 'encounterdate':
                question = {
                    "id": qid,
                    "label": label or "Visit Date",
                    "type": "encounterDate",
                    "questionOptions": {
                        "rendering": "date",
                        "showTime": element.get("showTime", "false"),
                        "allowFutureDates": element.get("allowFutureDates", "false")
                    }
                }
            elif element.name.lower() == 'encounterprovider':
                question = {
                    "id": qid,
                    "label": label or "Provider",
                    "type": "encounterProvider",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "currentUser":
                    question["default"] = "currentUser"
            elif element.name.lower() == 'encounterlocation':
                question = {
                    "id": qid,
                    "label": label or "Facility",
                    "type": "encounterLocation",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
                if element.get("default") == "SessionAttribute:emrContext.sessionLocationId":
                    question["default"] = "SessionAttribute:emrContext.sessionLocationId"
            elif element.name.lower() == 'encounterfacility':
                question = {
                    "id": qid,
                    "label": label or "Facility",
                    "type": "encounterFacility",
                    "questionOptions": {
                        "rendering": "ui-select-extended"
                    }
                }
            else:
                # Generic fallback for any other encounter* tag
                question = {
                    "id": qid,
                    "label": label or element.name,
                    "type": element.name,
                    "questionOptions": {
                        "rendering": "text"
                    }
                }

            # Avoid duplicates (by id)
            if not any(q["id"] == qid for q in general_section["questions"]):
                general_section["questions"].append(question)

    def generate_outputs(self, soup, form_name, encounter_type_uuid=None):
        form_uuid = str(uuid.uuid4())
        json_form = {
            "name": form_name,
            "uuid": form_uuid,
            "processor": "EncounterFormProcessor" if encounter_type_uuid else "",
            "version": "1.0",
            "description": "",
            "pages": []
        }
        if encounter_type_uuid:
            json_form["encounterType"] = encounter_type_uuid

        wb = Workbook()
        ws = wb.active
        ws.title = "Form"
        ws.append([
            "Page", "Section", "Question", "Datatype", "Mandatory", "Question ID",
            "External ID", "Rendering", "OptionSet name", "Upper limit", "Lower limit"
        ])
        option_sets = {}

        self.id_counter = 1  # <-- Use this for incremental numbering

        htmlid_to_qid = {}     # Maps HTML ids to generated question ids
        cid_to_qid = {}        # Maps concept IDs to generated question ids
        qid_to_question = {}   # Maps generated question ids to question objects

        # Constants for Boolean concepts
        YES_CONCEPT = "1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # UUID for concept_id 1
        NO_CONCEPT = "2AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"   # UUID for concept_id 2

        # Process root level encounter elements
        self.process_root_encounters(soup, json_form)

        # Process all encounter elements
        self.process_all_encounter_elements(soup, json_form)

        # --- Then process fieldsets ---
        fieldsets = soup.find_all("fieldset")
        if not fieldsets:
            fieldsets = [soup]  # Use whole document if no fieldsets

        pages_to_add = []

        for fieldset in fieldsets:
            legend = fieldset.find("legend")
            section_label = legend.text.strip() if legend else None

            current_section = {
                "label": section_label or "Unlabeled Section",
                "questions": []
            }

            # Process both encounter and obs elements
            self.process_fieldset_elements(fieldset, current_section)
            
            # Then process obs elements
            obs_tags = fieldset.find_all("obs", recursive=True)
            
            # Set page_label without depending on obs_tags[0]
            page_label = section_label or "Page"
            section_label_final = section_label or "Section"

            # Process encounter elements first
            self.process_encounter_elements(fieldset, current_section)

            # Then process obs elements if any exist
            if obs_tags:
                # Get first obs concept info if available
                first_obs = obs_tags[0]
                first_obs_cid = first_obs.get("conceptid")
                if first_obs_cid and first_obs_cid.isdigit():
                    section_label_final = section_label or self.concept_map.get(int(first_obs_cid), {}).get("name", "Section")

            # Continue with existing obs processing
            seen_questions = set()  # To avoid repeating any question
            used_labels = {}        # To ensure label uniqueness within the section

            for obs in obs_tags:
                cid = obs.get("conceptid")
                if not cid or not cid.isdigit():
                    continue
                cid = int(cid)

                # --- Use label as it appears on the HTML form ---
                label_td = obs.find_parent("td")
                if label_td:
                    prev_td = label_td.find_previous_sibling("td")
                    if prev_td and prev_td.text.strip():
                        label = prev_td.text.strip()
                    else:
                        label = obs.get("label", "") or self.concept_map.get(cid, {"name": f"Concept {cid}"})["name"]
                else:
                    label = obs.get("label", "") or self.concept_map.get(cid, {"name": f"Concept {cid}"})["name"]

                # --- Ensure label uniqueness ---
                original_label = label
                label_count = used_labels.get(original_label, 0)
                if label_count > 0:
                    label = f"{original_label} ({label_count+1})"
                used_labels[original_label] = label_count + 1

                concept_info = self.concept_map.get(cid, {"uuid": "", "name": label})
                uuid_val = concept_info["uuid"]
                base_id = to_camel_case_id(label)
                qid = f"{base_id}_{self.id_counter}"

                # --- DO NOT REPEAT ANY QUESTION ---
                if qid in seen_questions:
                    continue
                seen_questions.add(qid)
                self.id_counter += 1

                html_id = obs.get("id")
                if html_id:
                    htmlid_to_qid[html_id] = qid
                concept_id = obs.get("conceptid")
                if concept_id:
                    cid_to_qid[concept_id] = qid
                question = {
                    "id": qid,
                    "label": label,
                    "type": "obs",
                    "questionOptions": {
                        "concept": uuid_val
                    }
                }
                qid_to_question[qid] = question  # After you build the question dict

                # --- Handle encounterProvider/person and encounterLocation ---
                # If obs has style="person" or is <encounterProvider>
                is_person = obs.get("style", "").lower() == "person" or obs.name.lower() == "encounterprovider"
                is_location = obs.name.lower() == "encounterlocation"

                if is_person:
                    # Render as encounterProvider select
                    question = {
                        "label": label,
                        "type": "encounterProvider",
                        "required": obs.get("required", "false").lower() == "true",
                        "id": qid,
                        "questionOptions": {
                            "rendering": "ui-select-extended"
                        },
                        "validators": []
                    }
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Provider", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                        "", "ui-select-extended", "", "", ""
                    ])
                    continue

                if is_location or obs.name.lower() == "encounterlocation":
                    question = {
                        "label": label,
                        "type": "encounterLocation",
                        "required": obs.get("required", "false").lower() == "true",
                        "id": qid,
                        "questionOptions": {
                            "rendering": "ui-select-extended"
                        },
                        "validators": []
                    }
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Location", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                        "", "ui-select-extended", "", "", ""
                    ])
                    continue

                # --- PRIORITY: Handle style="checkbox" as radio with default ---
                if obs.get("style", "").lower() == "checkbox":
                    checked_val = obs.get("value", "").lower()
                    default_val = True if checked_val in ["true", "1", "yes", "checked"] else False
                    question = {
                        "id": qid,
                        "label": label,
                        "type": "radio",
                        "questionOptions": {
                            "concept": uuid_val,
                            "rendering": "radio",
                            "answers": [
                                {
                                    "label": label,
                                    "concept": uuid_val
                                }
                            ]
                        }
                    }
                    if default_val:
                        question["default"] = uuid_val  # Set default to the single answer option's uuid
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Radio", "No", qid,
                        "", "radio", "", "", ""
                    ])
                    continue

                # --- PRIORITY: Handle answerConceptIds as select, even if answerLabel(s) is present ---
                answer_concept_ids = obs.get("answerconceptids")
                answer_labels = obs.get("answerlabels") or obs.get("answerlabel")
                if answer_concept_ids:
                    ids = [x.strip() for x in answer_concept_ids.split(",")]
                    # If only one concept id and no answerLabel(s), use concept_name for label
                    if len(ids) == 1 and not answer_labels:
                        cid_val = ids[0]
                        # Use the uuid and name for the answer option
                        uuid_val_ans = self.concept_map.get(int(cid_val), {}).get("uuid", cid_val) if cid_val.isdigit() else cid_val
                        label_val_ans = self.concept_map.get(int(cid_val), {}).get("name", cid_val) if cid_val.isdigit() else cid_val
                        answers = [{
                            "label": label_val_ans,
                            "concept": uuid_val_ans
                        }]
                    else:
                        labels = [x.strip() for x in answer_labels.split(",")] if answer_labels else ids
                        answers = []
                        for i, cid_val in enumerate(ids):
                            uuid_val_ans = self.concept_map.get(int(cid_val), {}).get("uuid", cid_val) if cid_val.isdigit() else cid_val
                            answers.append({
                                "label": labels[i] if i < len(labels) else cid_val,
                                "concept": uuid_val_ans
                            })
                    question = {
                        "id": qid,
                        "label": label,
                        "type": "obs",
                        "questionOptions": {
                            "concept": uuid_val,
                            "rendering": "select",
                            "answers": answers
                        }
                    }
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Coded", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                        "", "select", "", "", ""
                    ])
                    continue

                # --- Handle style="no_yes_dropdown" ---
                elif obs.get("style", "").lower() in ["no_yes_dropdown", "yes_no", "no_yes"]:
                    question = {
                        "id": qid,
                        "label": label,
                        "type": "obs",
                        "questionOptions": {
                            "concept": uuid_val,
                            "rendering": "select",
                            "answers": [
                                {
                                    "label": "Yes",
                                    "concept": YES_CONCEPT
                                },
                                {
                                    "label": "No", 
                                    "concept": NO_CONCEPT
                                }
                            ]
                        }
                    }
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Coded", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                        "", "select", "", "", ""
                    ])
                    continue

                # --- Handle <obs conceptId="..."/> with no answerConceptIds/answerLabels: prioritize date, then numeric/coded ---
                if (
                    obs.name.lower() == "obs"
                    and obs.get("conceptid")
                    and not obs.get("answerconceptids")
                    and not obs.get("answerlabels")
                    and not obs.get("answerlabel")
                ):
                    cid = obs.get("conceptid")
                    if cid and cid.isdigit():
                        cid = int(cid)
                        uuid_val = self.concept_map.get(cid, {}).get("uuid", "")
                        datatype = self.concept_datatypes.get(cid, "").lower()
                        # 1. Prioritize rendering as date if label contains 'date'
                        if "date" in label.lower():
                            question = {
                                "id": qid,
                                "label": label,
                                "type": "obs",
                                "questionOptions": {
                                    "concept": uuid_val,
                                    "rendering": "date"
                                },
                                "validators": [{
                                    "type": "date",
                                    "message": "Please enter a valid date"
                                }]
                            }
                            current_section["questions"].append(question)
                            ws.append([
                                page_label, section_label_final, label, "Date", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                                "", "date", "", "", ""
                            ])
                            continue
                        # 2. If numeric, render as number
                        elif datatype == "numeric":
                            numeric_info = self.concept_numeric.get(cid, {})
                            question_options = {
                                "concept": uuid_val,
                                "rendering": "number"
                            }
                            validators = []
                            if numeric_info.get("hi_absolute") is not None:
                                question_options["max"] = str(numeric_info["hi_absolute"])
                                validators.append({
                                    "type": "max",
                                    "value": str(numeric_info["hi_absolute"]),
                                    "message": f"Value must be <= {numeric_info['hi_absolute']}"
                                })
                            if numeric_info.get("low_absolute") is not None:
                                question_options["min"] = str(numeric_info["low_absolute"])
                                validators.append({
                                    "type": "min",
                                    "value": str(numeric_info["low_absolute"]),
                                    "message": f"Value must be >= {numeric_info['low_absolute']}"
                                })
                            question = {
                                "id": qid,
                                "label": label,
                                "type": "obs",
                                "questionOptions": question_options
                            }
                            if validators:
                                question["validators"] = validators
                            current_section["questions"].append(question)
                            ws.append([
                                page_label, section_label_final, label, "Numeric", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                                "", "number", "", question_options.get("max", ""), question_options.get("min", "")
                            ])
                            continue
                        # 3. If coded, render as select using concept answers
                        elif datatype == "coded":
                            answers = []
                            for ans in self.concept_answers.get(cid, []):
                                answers.append({
                                    "label": ans["label"],
                                    "concept": ans["uuid"]
                                })
                            
                            # Deduplicate answers before adding to question
                            answers = self.deduplicate_answers(answers)
                            
                            question = {
                                "id": qid,
                                "label": label,
                                "type": "obs",
                                "questionOptions": {
                                    "concept": uuid_val,
                                    "rendering": "select",
                                    "answers": answers
                                }
                            }
                            current_section["questions"].append(question)
                            ws.append([
                                page_label, section_label_final, label, "Coded", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                                "", "select", "", "", ""
                            ])
                            continue

                # --- Datatype-based rendering ---
                datatype = self.concept_datatypes.get(cid, "").lower()
                rendering = "text"  # default
                question_options = {
                    "concept": uuid_val
                }
                validators = []

                # Add time handling before date check
                if datatype == "time" or ("time" in label.lower() and not datatype == "coded"):
                    rendering = "datetime"
                    question_options.update({
                        "showDate": "false",  # Quote boolean values
                        "showTime": "true",   # Quote boolean values
                        "allowFutureDates": "true"  # Quote boolean values
                    })
                    validators.append({
                        "type": "datetime",
                        "message": "Please enter a valid time"
                    })
                elif datatype == "date":
                    rendering = "date"
                    question_options["allowFutureDates"] = "false"  # Quote boolean value
                    validators.append({
                        "type": "date",
                        "message": "Please enter a valid date"
                    })
                elif datatype == "numeric":
                    rendering = "number"
                    numeric_info = self.concept_numeric.get(cid, {})
                    if numeric_info.get("hi_absolute") is not None:
                        # Ensure max is a string
                        question_options["max"] = str(numeric_info["hi_absolute"])
                        validators.append({
                            "type": "max",
                            "value": str(numeric_info["hi_absolute"]),
                            "message": f"Value must be <= {numeric_info['hi_absolute']}"
                        })
                    if numeric_info.get("low_absolute") is not None:
                        # Ensure min is a string
                        question_options["min"] = str(numeric_info["low_absolute"])
                        validators.append({
                            "type": "min",
                            "value": str(numeric_info["low_absolute"]),
                            "message": f"Value must be >= {numeric_info['low_absolute']}"
                        })
                # --- Handle answerLabel for radio buttons ---
                elif obs.get("answerlabel"):
                    # Use answerLabel as the label, type radio, one option, no default
                    answer_label = obs.get("answerlabel")
                    answer_concept_id = obs.get("answerconceptid")
                    # Use the answerConceptId directly as the answer's concept (string, not uuid)
                    question = {
                        "id": qid,
                        "label": answer_label,
                        "type": "radio",
                        "questionOptions": {
                            "concept": uuid_val,
                            "rendering": "radio",
                            "answers": [
                                {
                                    "label": answer_label,
                                    "concept": answer_concept_id or ""
                                }
                            ]
                        }
                    }
                    current_section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, answer_label, "Radio", "No", qid,
                        "", "radio", "", "", ""
                    ])
                    continue
                else:
                    # --- Existing logic for radios, selects, etc. ---
                    # (You may want to keep your radio/select logic here as before)
                    # For brevity, only the datatype logic is shown here.
                    pass

                question_options["rendering"] = rendering

                question = {
                    "id": qid,
                    "label": label,
                    "type": "obs",
                    "questionOptions": question_options
                }
                if validators:
                    question["validators"] = validators

                current_section["questions"].append(question)
                ws.append([
                    page_label, section_label_final, label, datatype.capitalize() if datatype else "Text", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                    "", rendering, "", question_options.get("max", ""), question_options.get("min", "")
                ])

            if current_section["questions"]:
                if not pages_to_add or pages_to_add[-1]["label"] != section_label:
                    pages_to_add.append({
                        "label": section_label or "Page",
                        "sections": []
                    })
                pages_to_add[-1]["sections"].append(current_section)

        # After collecting all sections for a page, before appending to json_form["pages"]:
        for page in pages_to_add:  # however you collect your pages
            # If page label is missing or generic, use first section label or first question label
            if not page.get("label") or page["label"] in ["Page", "Unlabeled Section", "General Information"]:
                if page["sections"]:
                    first_section = page["sections"][0]
                    if first_section.get("label") and first_section["label"] not in ["Unlabeled Section", "Section"]:
                        page["label"] = first_section["label"]
                    elif first_section.get("questions"):
                        page["label"] = first_section["questions"][0].get("label", "Page")
            # For each section, do the same for section label
            for section in page["sections"]:
                if not section.get("label") or section["label"] in ["Unlabeled Section", "Section"]:
                    if section.get("questions"):
                        section["label"] = section["questions"][0].get("label", "Section")
            json_form["pages"].append(page)

        # --- After all questions are generated: ---
        # Build a mapping from concept uuid to all qids for fallback (handles duplicates)
        conceptuuid_to_qids = {}
        for qid, q in qid_to_question.items():
            concept_uuid = q["questionOptions"]["concept"]
            if concept_uuid not in conceptuuid_to_qids:
                conceptuuid_to_qids[concept_uuid] = []
            conceptuuid_to_qids[concept_uuid].append(qid)

        # Add this debug print to verify mappings
        print("HTML ID to QID mapping:", htmlid_to_qid)
        print("Concept ID to QID mapping:", cid_to_qid)

        # --- Process conditional rendering ---
        for obs in soup.find_all("obs"):
            # 1. Handle controls/when
            controls = obs.find("controls")
            if controls:
                print(f"Found controls in obs with id: {obs.get('id')}")
                for when in controls.find_all("when"):
                    if when.get("value") and when.get("thendisplay"):
                        controlling_id = obs.get("id")
                        controlling_qid = htmlid_to_qid.get(controlling_id)
                        trigger_value = when.get("value")
                        
                        # Fix: Get UUID for trigger value
                        if trigger_value.isdigit():
                            # Get the proper UUID from concept_map
                            trigger_uuid = self.concept_map.get(int(trigger_value), {}).get("uuid")
                            if not trigger_uuid:
                                # If not in concept_map, append standard suffix
                                trigger_uuid = f"{trigger_value}AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                        else:
                            trigger_uuid = trigger_value
                        
                        target_id = when.get("thendisplay").lstrip("#")
                        target_elem = soup.find(id=target_id)
                        
                        if controlling_qid and target_elem:
                            for child_obs in target_elem.find_all("obs"):
                                child_cid = child_obs.get("conceptid")
                                if child_cid in cid_to_qid:
                                    child_qid = cid_to_qid[child_cid]
                                    for page in json_form["pages"]:
                                        for section in page["sections"]:
                                            for question in section["questions"]:
                                                if question["id"] == child_qid:
                                                    question["hide"] = {
                                                        "hideWhenExpression": f"isEmpty({controlling_qid}) || {controlling_qid} !== '{trigger_uuid}'"
                                                    }

            # 2. Handle toggle
            if obs.get("style", "").lower() == "checkbox" and obs.get("toggle"):
                controlling_id = obs.get("id")
                controlling_qid = htmlid_to_qid.get(controlling_id)
                toggle_target = obs.get("toggle")
                
                print(f"Processing toggle: {controlling_id} -> {toggle_target}")
                
                target_elem = soup.find(id=toggle_target)
                if controlling_qid and target_elem:
                    for child_obs in target_elem.find_all("obs"):
                        child_cid = child_obs.get("conceptid")
                        if child_cid in cid_to_qid:
                            child_qid = cid_to_qid[child_cid]
                            print(f"Adding hide to {child_qid}")
                            
                            # Add hide expression to the question
                            for page in json_form["pages"]:
                                for section in page["sections"]:
                                    for question in section["questions"]:
                                        if question["id"] == child_qid:
                                            question["hide"] = {
                                                "hideWhenExpression": f"!{controlling_qid}"
                                            }

        # --- Handle toggle attributes ---
        for obs in soup.find_all("obs"):
            if obs.get("style", "").lower() == "checkbox" and obs.get("toggle"):
                # Get the controlling question's id (the checkbox)
                controlling_id = obs.get("id")
                controlling_qid = None
                
                # Get the generated question id for this checkbox
                controlling_cid = obs.get("conceptid")
                if controlling_cid in cid_to_qid:
                    controlling_qid = cid_to_qid[controlling_cid]
                    # Get the UUID for the controlling concept
                    controlling_uuid = self.concept_map.get(int(controlling_cid), {}).get("uuid")
                
                toggle_target = obs.get("toggle")  
                print(f"Processing toggle: checkbox concept {controlling_cid} -> {toggle_target}")
                
                # Find the target container by ID
                target_elem = soup.find(id=toggle_target)
                if controlling_qid and controlling_uuid and target_elem:
                    # Find all obs inside the target container
                    for child_obs in target_elem.find_all("obs"):
                        child_cid = child_obs.get("conceptid")
                        if child_cid and child_cid in cid_to_qid:
                            child_qid = cid_to_qid[child_cid]
                            for page in json_form["pages"]:
                                for section in page["sections"]:
                                    for question in section["questions"]:
                                        if question["id"] == child_qid:
                                            print(f"Adding hide to question {child_qid}")
                                            question["hide"] = {
                                                "hideWhenExpression": f"isEmpty({controlling_qid}) || {controlling_qid} !== '{controlling_uuid}'"
                                            }

        # --- OptionSets Sheet ---
        ws2 = wb.create_sheet("OptionSets")
        ws2.append(["OptionSet name", "Answers", "External ID"])
        for opt_name, values in option_sets.items():
            for ans, extid in values:
                ws2 .append([opt_name, ans, extid])

        # Move "General Information" page to the end if it exists
        general_info_index = None
        for idx, page in enumerate(json_form["pages"]):
            if page.get("label", "").strip().lower() == "general information":
                general_info_index = idx
                break

        if general_info_index is not None:
            general_info_page = json_form["pages"].pop(general_info_index)
            json_form["pages"].append(general_info_page)

        # --- Save ---
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, f"{form_name}_converted.xlsx")
        json_path = os.path.join(output_dir, f"{form_name}_converted.json")
        wb.save(excel_path)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(json_form, jf, indent=2, ensure_ascii=False) # type: ignore
        messagebox.showinfo("Done", f"Files generated in {output_dir}")

        # After initializing json_form and id_counter

        # Find all obs and encounter elements in DOM order, anywhere in the document
        question_tags = soup.find_all(
            ["obs", "encounterDate", "encounterProvider", "encounterLocation", "encounterFacility"],
            recursive=True
        )

        # Group by fieldset if present, otherwise group by "orphan" (not in fieldset)
        fieldset_to_questions = {}
        orphans = []

        for elem in question_tags:
            parent_fieldset = elem.find_parent("fieldset")
            if parent_fieldset:
                if parent_fieldset not in fieldset_to_questions:
                    fieldset_to_questions[fieldset] = []
                fieldset_to_questions[fieldset].append(elem)
            else:
                orphans.append(elem)

        # --- Process fieldsets first ---
        for fieldset, elems in fieldset_to_questions.items():
            legend = fieldset.find("legend")
            section_label = legend.text.strip() if legend else None
            section = {
                "label": section_label or "Section",
                "questions": []
            }
            for elem in elems:
                # --- Encounter elements ---
                if elem.name.lower().startswith("encounter"):
                    # (use your encounter question logic here, as in your process_encounter_elements)
                    # ... build question dict as before ...
                    pass
                # --- Obs elements ---
                elif elem.name == "obs":
                    # (use your obs question logic here)
                    # ... build question dict as before ...
                    pass
            if section["questions"]:
                json_form["pages"].append({
                    "label": section_label or "Page",
                    "sections": [section]
                })

        # --- Now process orphan questions (not in any fieldset) ---
        if orphans:
            # Use the first question's label as section/page label
            first_label = None
            orphan_questions = []
            for elem in orphans:
                label = None
                prev_td = elem.find_parent('td')
                if prev_td:
                    label_td = prev_td.find_previous_sibling('td')
                    if label_td:
                        label = label_td.text.strip().rstrip(':')
                if not label:
                    label = elem.get("label") or "Question"
                if not first_label:
                    first_label = label
                # --- Encounter elements ---
                if elem.name.lower().startswith("encounter"):
                    # ... build encounter question dict as before ...
                    pass
                elif elem.name == "obs":
                    # ... build obs question dict as before ...
                    pass
                # orphan_questions.append(question)
            if orphan_questions:
                json_form["pages"].append({
                    "label": first_label or "Page",
                    "sections": [{
                        "label": first_label or "Section",
                        "questions": orphan_questions
                    }]
                })

    def download_html(self):
        # Save the current HTML/XML in the display box to a file
        html_content = self.xml_text.get("1.0", END)
        if not html_content:
            messagebox.showwarning("No Content", "There is no HTML to download.")
            return

        # Get the selected form name for the filename
        if self.selected_form_index is not None:
            form = self.forms[self.selected_form_index]
            form_name = form['name']
        else:
            form_name = "form"

        # Clean filename (remove invalid characters)
        safe_form_name = "".join(c if c.isalnum() or c in " ._-" else "_" for c in form_name)
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{safe_form_name}.html")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        messagebox.showinfo("Saved", f"HTML saved to {file_path}")

    def upload_html(self):
        import tkinter.filedialog as filedialog
        file_path = filedialog.askopenfilename(filetypes=[("HTML Files", "*.html;*.htm"), ("All Files", "*.*")])
        if file_path:
            with open(file_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            self.xml_text.delete(1.0, END)
            self.xml_text.insert(END, html_content)
            self.highlight_syntax(self.xml_text, 'html') # Highlight after loading

    def convert_displayed_html(self):
        html = self.xml_text.get("1.0", END)
        if not html:
            messagebox.showerror("Error", "No HTML to convert.")
            return
        soup = BeautifulSoup(html, 'html.parser')
        concept_ids = set()
        for obs in soup.find_all("obs"):
            cid = obs.get("conceptid")
            if cid and cid.isdigit():
                concept_ids.add(int(cid))
            # Also collect answerConceptIds
            answer_ids = []
            if obs.get("answers"):
                answer_ids = [a.strip() for a in obs.get("answers").split(",")]
            elif obs.get("answerconceptids"):
                answer_ids = [a.strip() for a in obs.get("answerconceptids").split(",")]
            elif obs.get("answerconceptid"):
                answer_ids = [obs.get("answerconceptid").strip()]
            for aid in answer_ids:
                if aid.isdigit():
                    concept_ids.add(int(aid))
        self.fetch_concepts_from_db(concept_ids)
        # Generate JSON and display in json_text
        # Use a temp name for the form
        if self.selected_form_index is not None:
            form = self.forms[self.selected_form_index]
            form_name = form['name']
            encounter_type_uuid = form.get('encounter_type_uuid')
        else:
            form_name = "Edited HTML Form"
            encounter_type_uuid = None
        self.generate_outputs(soup, form_name, encounter_type_uuid)
        temp_name = form_name # Use the determined name for file lookup
        # After generate_outputs, load the generated JSON file and display it
        output_dir = os.path.join(os.getcwd(), "converted")
        json_path = os.path.join(output_dir, f"{temp_name}_converted.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as jf:
                json_content = jf.read()
            self.json_text.config(state="normal")
            self.json_text.delete(1.0, END)
            self.json_text.insert(END, json_content)
            self.highlight_syntax(self.json_text, 'json') # Highlight after loading

    def download_json(self):
        import tkinter.filedialog as filedialog
        json_content = self.json_text.get("1.0", END).strip()
        if not json_content:
            messagebox.showwarning("No Content", "There is no JSON to download.")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json_content)
            messagebox.showinfo("Saved", f"JSON saved to {file_path}")

class JSONToolsTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app

        # --- Main Layout ---
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- JSON Tools Frame ---
        json_compare_frame = ttk.LabelFrame(main_frame, text="JSON Form Tools")
        json_compare_frame.pack(fill="x", pady=10)
        json_compare_frame.columnconfigure(0, weight=1)
        json_compare_frame.columnconfigure(1, weight=1)
        json_compare_frame.columnconfigure(2, weight=1)
        json_compare_frame.columnconfigure(3, weight=1)

        # Row 0: Buttons
        ttk.Button(json_compare_frame, text="Upload Main JSON 1", command=lambda: self.main_app.upload_comparison_json(1)).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(json_compare_frame, text="Upload JSON 2", command=lambda: self.main_app.upload_comparison_json(2)).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(json_compare_frame, text="Compare JSON 1 and JSON 2", command=self.main_app.compare_jsons).grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        ttk.Button(json_compare_frame, text="Download Merged JSON File", command=self.main_app.merge_and_download_json).grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        # Row 1: Labels for file paths
        json1_label_frame = ttk.Frame(json_compare_frame)
        json1_label_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=2, sticky="ew")
        ttk.Label(json1_label_frame, text="JSON 1:").pack(side="left")
        ttk.Label(json1_label_frame, textvariable=self.main_app.json1_path, anchor="w").pack(side="left", fill="x", expand=True)

        json2_label_frame = ttk.Frame(json_compare_frame)
        json2_label_frame.grid(row=1, column=2, columnspan=2, padx=5, pady=2, sticky="ew")
        ttk.Label(json2_label_frame, text="JSON 2:").pack(side="left")
        ttk.Label(json2_label_frame, textvariable=self.main_app.json2_path, anchor="w").pack(side="left", fill="x", expand=True)

        # --- Comparison Result Display ---
        result_frame = ttk.LabelFrame(main_frame, text="Comparison Results")
        result_frame.pack(fill="both", expand=True, pady=10)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        self.result_text = Text(result_frame, wrap="word", state="disabled", bg="#f0f0f0")
        self.result_text.grid(row=0, column=0, sticky="nsew")
        
        result_scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_text.yview)
        result_scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_text.config(yscrollcommand=result_scrollbar.set)

    def display_comparison_results(self, comparison_data):
        """Displays the results of the JSON comparison in the text widget."""
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", END)

        if not any(comparison_data.values()):
            self.result_text.insert(END, "No differences found. All questions are identical.")
            self.result_text.config(state="disabled")
            return

        # --- Mismatched Concepts ---
        if comparison_data["mismatched"]:
            self.result_text.insert(END, "--- Concept Mismatches ---\n\n")
            for item in comparison_data["mismatched"]:
                self.result_text.insert(END, f"Question: {item['label']}\n")
                self.result_text.insert(END, f"  - JSON 1 Concept: {item['concept1']}\n")
                self.result_text.insert(END, f"  - JSON 2 Concept: {item['concept2']}\n\n")
            self.result_text.insert(END, "="*40 + "\n\n")

        # --- Only in JSON 1 ---
        if comparison_data["json1_only"]:
            self.result_text.insert(END, "--- Questions Only in JSON 1 ---\n\n")
            for item in comparison_data["json1_only"]:
                self.result_text.insert(END, f"Question: {item['label']}\n")
                self.result_text.insert(END, f"  - Concept: {item['concept']}\n\n")
            self.result_text.insert(END, "="*40 + "\n\n")

        # --- Only in JSON 2 ---
        if comparison_data["json2_only"]:
            self.result_text.insert(END, "--- Questions Only in JSON 2 ---\n\n")
            for item in comparison_data["json2_only"]:
                self.result_text.insert(END, f"Question: {item['label']}\n")
                self.result_text.insert(END, f"  - Concept: {item['concept']}\n\n")

        self.result_text.config(state="disabled")

    def clear_results(self):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", END)
        self.result_text.config(state="disabled")

    def get_main_app(self):
        """Provides access to the main application instance."""
        return self.main_app



class OCLManagementTab(ttk.Frame):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.all_ocl_concepts = []  # To store the full list for local search
        self.current_page = 1

        # --- OCL Configuration ---
        config_frame = ttk.LabelFrame(self, text="OCL Configuration")
        config_frame.pack(fill="x", padx=10, pady=10)
        config_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(3, weight=1)

        self.api_token = tk.StringVar()
        self.owner_type = tk.StringVar(value="Organization")
        self.ocl_org = tk.StringVar(value="NMRS")
        self.ocl_source = tk.StringVar(value="NMRS")

        # Row 0: API Token
        ttk.Label(config_frame, text="API Token:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(config_frame, textvariable=self.api_token, show="*", width=50).grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        # Row 1: Owner Type and ID
        ttk.Label(config_frame, text="Owner Type:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        owner_type_dropdown = ttk.Combobox(config_frame, textvariable=self.owner_type, values=["Organization", "User"], state="readonly")
        owner_type_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(config_frame, text="Owner ID:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        ttk.Entry(config_frame, textvariable=self.ocl_org).grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        # Row 2: Source and Load Button
        ttk.Label(config_frame, text="OCL Source:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(config_frame, textvariable=self.ocl_source).grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(config_frame, text="Load Concepts from OCL", command=self.load_ocl_concepts).grid(row=2, column=2, columnspan=2, padx=5, pady=5, sticky="ew")

        # --- Actions Frame ---
        actions_frame = ttk.LabelFrame(self, text="Actions")
        actions_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(actions_frame, text="Create Single Concept from OpenMRS", command=self.create_single_concept_window).pack(side="left", padx=5, pady=5)
        ttk.Button(actions_frame, text="Generate OCL Excel from All Forms", command=self.generate_all_concepts_for_ocl).pack(side="left", padx=5, pady=5) # type: ignore
        self.upload_button = ttk.Button(actions_frame, text="Upload OCL Excel", command=self.upload_bulk_from_excel)
        self.upload_button.pack(side="left", padx=5, pady=5)
        ttk.Button(actions_frame, text="Edit Selected Concept", command=self.edit_selected_concept).pack(side="left", padx=5, pady=5)
        ttk.Button(actions_frame, text="Delete Selected Concept", command=self.delete_selected_concept).pack(side="left", padx=5, pady=5)

        # --- Concept List ---
        list_frame = ttk.LabelFrame(self, text="OCL Concepts in Source")
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- Local Search Bar ---
        search_frame = ttk.Frame(list_frame)
        search_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Label(search_frame, text="Search Loaded Concepts:").pack(side="left")
        self.local_search_var = tk.StringVar()
        local_search_entry = ttk.Entry(search_frame, textvariable=self.local_search_var)
        local_search_entry.pack(side="left", fill="x", expand=True, padx=5)
        local_search_entry.bind("<KeyRelease>", self.filter_ocl_concepts)

        self.tree = ttk.Treeview(list_frame, columns=("ID", "Name", "UUID", "Datatype", "Class"), show="headings")
        self.tree.heading("ID", text="OCL ID")
        self.tree.heading("Name", text="Display Name")
        self.tree.heading("UUID", text="External ID (UUID)")
        self.tree.heading("Datatype", text="Datatype")
        self.tree.heading("Class", text="Concept Class")

        self.tree.column("ID", width=100)
        self.tree.column("Name", width=300)
        self.tree.column("UUID", width=300)
        self.tree.column("Datatype", width=100)
        self.tree.column("Class", width=100)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew")

        list_frame.rowconfigure(1, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # --- Pagination Controls ---
        pagination_frame = ttk.Frame(list_frame)
        pagination_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=5)
        pagination_frame.columnconfigure(1, weight=1)

        self.prev_button = ttk.Button(pagination_frame, text="<< Previous", command=self.prev_page, state="disabled")
        self.prev_button.grid(row=0, column=0, padx=5)
        self.page_label = ttk.Label(pagination_frame, text="Page 1 / 1")
        self.page_label.grid(row=0, column=1, padx=5)
        self.next_button = ttk.Button(pagination_frame, text="Next >>", command=self.next_page, state="disabled")
        self.next_button.grid(row=0, column=2, padx=5)
    def get_headers(self, write_access=False):
        token = self.api_token.get()
        if not token and write_access:
            messagebox.showerror("Error", "An OCL API Token is required for this write operation.")
            return None
        return {
            "Authorization": f"Token {token}" if token else "",
            "Content-Type": "application/json",
        }

    def load_ocl_concepts(self):
        self.all_ocl_concepts = []  # Clear previous results
        for i in self.tree.get_children():
            self.tree.delete(i)

        self.current_page = 1
        headers = self.get_headers()
        if not headers: return

        # Show a progress/loading indicator
        progress_win = tk.Toplevel(self)
        progress_win.title("Loading...")
        progress_win.geometry("300x80")
        progress_win.transient(self.main_app.root)
        progress_win.grab_set()
        ttk.Label(progress_win, text="Fetching all concepts from OCL...").pack(pady=10)
        progress_bar = ttk.Progressbar(progress_win, mode='indeterminate')
        progress_bar.pack(pady=5, padx=20, fill='x')
        progress_bar.start()
        self.update_idletasks()

        owner_id = self.ocl_org.get()
        source = self.ocl_source.get()
        path_segment = "orgs" if self.owner_type.get() == "Organization" else "users"
        base_url = f"https://api.openconceptlab.org/{path_segment}/{owner_id}/sources/{source}/concepts/"
        
        # Fetch all concepts with pagination
        all_concepts = []
        url = base_url
        while url:
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                all_concepts.extend(data)
                # Check for next page link in headers
                if 'next' in response.links:
                    url = response.links['next']['url']
                else:
                    url = None
            except requests.exceptions.RequestException as e:
                progress_win.destroy()
                messagebox.showerror("Error", f"Failed to load concepts from OCL:\n{e}")
                return
            except json.JSONDecodeError:
                progress_win.destroy()
                messagebox.showerror("Error", "Failed to parse response from OCL. The source might be empty or invalid.")
                return

        progress_win.destroy() # type: ignore
        self.all_ocl_concepts = all_concepts
        self.total_pages = (len(self.all_ocl_concepts) + 24) // 25
        self.filter_ocl_concepts() # This will populate the first page
        messagebox.showinfo("Success", f"Loaded {len(self.all_ocl_concepts)} concepts from OCL.")

    def populate_treeview(self, concepts_to_display):
        """Clears and populates the treeview with a list of concepts."""
        for i in self.tree.get_children():
            self.tree.delete(i)
        for concept in concepts_to_display:
            self.tree.insert("", "end", values=(
                concept.get('id', ''),
                concept.get('display_name', ''),
                concept.get('external_id', ''),
                concept.get('datatype', ''),
                concept.get('concept_class', '')
            ))
        self.update_pagination_controls()

    def filter_ocl_concepts(self, event=None):
        """Filters the displayed concepts based on the local search bar."""
        search_term = self.local_search_var.get().lower()
        if search_term:
            self.filtered_list = [c for c in self.all_ocl_concepts if search_term in str(c.get('id','')).lower() or search_term in str(c.get('display_name','')).lower() or search_term in str(c.get('external_id','')).lower()]
        else:
            self.filtered_list = self.all_ocl_concepts

        self.total_pages = (len(self.filtered_list) + 24) // 25
        self.current_page = 1
        self.show_current_page()

    def show_current_page(self):
        start_index = (self.current_page - 1) * 25
        end_index = start_index + 25
        page_concepts = self.filtered_list[start_index:end_index]
        self.populate_treeview(page_concepts)

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.show_current_page()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.show_current_page()

    def update_pagination_controls(self):
        self.page_label.config(text=f"Page {self.current_page} / {self.total_pages}")
        self.prev_button.config(state="normal" if self.current_page > 1 else "disabled")
        self.next_button.config(state="normal" if self.current_page < self.total_pages else "disabled")

    def create_single_concept_window(self): # No change here, just for context
        # Simple dialog to get a concept ID from OpenMRS
        dialog = tk.Toplevel(self)
        dialog.title("Upload Single Concept")
        dialog.geometry("400x150")
        dialog.transient(self.main_app.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Enter OpenMRS Concept ID to upload:").pack(pady=10)
        concept_id_entry = ttk.Entry(dialog, width=40)
        concept_id_entry.pack(pady=5)

        def do_upload():
            concept_id = concept_id_entry.get()
            if not concept_id.isdigit():
                messagebox.showerror("Invalid ID", "Please enter a numeric Concept ID.", parent=dialog)
                return
            self.upload_single_concept(int(concept_id))
            dialog.destroy()

        ttk.Button(dialog, text="Upload to OCL", command=do_upload).pack(pady=10)

    def upload_single_concept(self, concept_id): # No change here, just for context
        headers = self.get_headers(write_access=True)
        if not headers: return

        # 1. Fetch concept details from OpenMRS DB
        cursor = self.main_app.connection.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT 
                c.uuid, c.retired,
                cn.name as display_name,
                cd.name as datatype,
                cc.name as concept_class,
                cds.description
            FROM concept c
            LEFT JOIN concept_name cn ON c.concept_id = cn.concept_id AND cn.locale_preferred = 1 AND cn.locale = 'en'
            LEFT JOIN concept_datatype cd ON c.datatype_id = cd.concept_datatype_id
            LEFT JOIN concept_class cc ON c.class_id = cc.concept_class_id
            LEFT JOIN concept_description cds ON c.concept_id = cds.concept_id AND cds.locale = 'en'
            WHERE c.concept_id = %s
        """, (concept_id,))
        concept_details = cursor.fetchone()
        cursor.close()

        if not concept_details:
            messagebox.showerror("Error", f"Concept ID {concept_id} not found in OpenMRS database.")
            return

        # 2. Construct OCL payload
        ocl_id = f"{self.ocl_source.get()}_{concept_id}"
        payload = {
            "id": ocl_id,
            "external_id": concept_details['uuid'],
            "concept_class": concept_details['concept_class'],
            "datatype": concept_details['datatype'],
            "names": [{
                "name": concept_details['display_name'],
                "locale": "en",
                "locale_preferred": True,
                "name_type": "Fully Specified"
            }],
            "retired": concept_details['retired']
        }
        if concept_details.get('description'):
            payload['descriptions'] = [{"description": concept_details['description'], "locale": "en"}]

        # 3. Show dialog for review and final upload
        self.show_review_and_upload_dialog(payload)

    def show_review_and_upload_dialog(self, payload):
        dialog = tk.Toplevel(self)
        dialog.title("Review and Upload Concept")
        dialog.geometry("600x500")
        dialog.transient(self.main_app.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Review the JSON payload before uploading to OCL. You can make edits below.").pack(pady=5, padx=10)

        text_frame = ttk.Frame(dialog)
        text_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        json_text = Text(text_frame, wrap="word", undo=True, bg="#2b2b2b", fg="#a9b7c6", insertbackground="white")
        json_text.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=json_text.yview)
        scrollbar.pack(side="right", fill="y")
        json_text.config(yscrollcommand=scrollbar.set)

        json_text.insert("1.0", json.dumps(payload, indent=2))

        def do_final_upload():
            headers = self.get_headers(write_access=True)
            if not headers: return

            try:
                final_payload_str = json_text.get("1.0", END)
                final_payload = json.loads(final_payload_str)
            except json.JSONDecodeError as e:
                messagebox.showerror("JSON Error", f"The content is not valid JSON:\n{e}", parent=dialog)
                return

            owner_id = self.ocl_org.get()
            source = self.ocl_source.get()
            path_segment = "orgs" if self.owner_type.get() == "Organization" else "users"
            url = f"https://api.openconceptlab.org/{path_segment}/{owner_id}/sources/{source}/concepts/"
            
            try:
                response = requests.post(url, headers=headers, data=json.dumps(final_payload))
                response.raise_for_status()
                messagebox.showinfo("Success", f"Concept '{final_payload.get('id')}' uploaded successfully to OCL.", parent=dialog)
                dialog.destroy()
                self.load_ocl_concepts() # Refresh list
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Upload Failed", f"Failed to upload concept:\n{e}\nResponse: {e.response.text if e.response else 'N/A'}", parent=dialog)

        ttk.Button(dialog, text="Save to OCL", command=do_final_upload).pack(pady=10)
    def generate_all_concepts_for_ocl(self):
        """Generates a single Excel file with all concepts from all forms, ready for OCL bulk upload."""
        if not self.main_app.connection:
            messagebox.showerror("Database Error", "Please connect to the database first.")
            return

        # 1. Fetch all forms
        cursor = self.main_app.connection.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT form_id, name FROM form WHERE retired = 0")
        all_forms = cursor.fetchall()
        cursor.close()

        if not all_forms:
            messagebox.showinfo("No Forms", "No active forms found in the database.")
            return

        # 2. Scan all forms to get all unique concept IDs
        all_concept_ids = set()
        for form in all_forms:
            form_name = form['name']
            html = self.main_app.fetch_form_html(form['form_id'])
            if not html: continue
            soup = BeautifulSoup(html, 'html.parser')
            for obs in soup.find_all("obs"):
                # Question concept
                q_cid = obs.get("conceptid")
                if q_cid and q_cid.isdigit():
                    cid = int(q_cid)
                    all_concept_ids.add(cid)
                # Answer concepts
                answer_sources = ["answerconceptids", "answerconceptid", "answers"]
                for source in answer_sources:
                    answer_ids_str = obs.get(source)
                    if answer_ids_str:
                        for aid in answer_ids_str.split(','):
                            if aid.strip().isdigit():
                                all_concept_ids.add(int(aid.strip()))
        
        # 3. Fetch details for all concepts
        self.main_app.fetch_concepts_from_db(all_concept_ids)

        # 4. Create Excel file
        wb = Workbook()
        ws = wb.active
        ws.title = "OCL_Bulk_Upload"
        headers = ["form_name", "html_question_text", "id", "external_id", "concept_class", "datatype", "name", "description"]
        ws.append(headers)

        source_prefix = self.ocl_source.get()
        
        # Re-iterate through forms to associate concepts with forms and questions
        for form in all_forms:
            form_name = form['name']
            html = self.main_app.fetch_form_html(form['form_id'])
            if not html: continue
            soup = BeautifulSoup(html, 'html.parser')
            
            for obs in soup.find_all("obs"):
                q_cid = obs.get("conceptid")
                if q_cid and q_cid.isdigit():
                    cid = int(q_cid)
                    concept_info = self.main_app.concept_map.get(cid)
                    if not concept_info: continue

                    # Extract HTML question text again
                    html_question_text = ""
                    parent_td = obs.find_parent('td')
                    if parent_td:
                        prev_td = parent_td.find_previous_sibling('td')
                        if prev_td and prev_td.text.strip():
                            html_question_text = prev_td.text.strip().rstrip(':')
                        else:
                            text_nodes = parent_td.find_all(string=True, recursive=False)
                            html_question_text = ' '.join(node.strip() for node in text_nodes).strip()
                    html_question_text = html_question_text or obs.get('labelText', '') or concept_info.get("name", "")

                    ocl_id = f"{source_prefix}_{cid}"
                    external_id = concept_info.get("uuid", "")
                    name = concept_info.get("name", "")
                    datatype = self.main_app.concept_datatypes.get(cid, "")
                    concept_class = concept_info.get("concept_class", "")
                    description = concept_info.get("description", "")

                    ws.append([form_name, html_question_text, ocl_id, external_id, concept_class, datatype, name, description])

        # 5. Save the file
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, "OCL_All_Concepts_Bulk_Upload.xlsx")
        
        try:
            wb.save(excel_path)
            messagebox.showinfo("Success", f"OCL bulk upload Excel file generated at:\n{excel_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save Excel file:\n{e}")

    def edit_selected_concept(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a concept from the list to edit.")
            return

        item_values = self.tree.item(selected_item[0], 'values')
        concept_id = item_values[0]

        # Find the full concept data from our stored list
        concept_data = next((c for c in self.all_ocl_concepts if c.get('id') == concept_id), None)
        if not concept_data:
            messagebox.showerror("Error", "Could not find the full data for the selected concept.")
            return

        # Create a dialog for editing
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Concept: {concept_id}")
        dialog.geometry("500x300")
        dialog.transient(self.main_app.root)
        dialog.grab_set() # type: ignore

        fields = ["display_name", "concept_class", "datatype"]
        entries = {}

        for i, field in enumerate(fields):
            ttk.Label(dialog, text=f"{field.replace('_', ' ').title()}:").grid(row=i, column=0, padx=10, pady=5, sticky="w")
            var = tk.StringVar(value=concept_data.get(field, ''))
            entry = ttk.Entry(dialog, textvariable=var, width=50)
            entry.grid(row=i, column=1, padx=10, pady=5, sticky="ew")
            entries[field] = var
        
        # Add description field
        ttk.Label(dialog, text="Description:").grid(row=len(fields), column=0, padx=10, pady=5, sticky="w")
        desc_var = tk.StringVar(value=concept_data.get('descriptions', [{}])[0].get('description', ''))
        desc_entry = ttk.Entry(dialog, textvariable=desc_var, width=50)
        desc_entry.grid(row=len(fields), column=1, padx=10, pady=5, sticky="ew")
        entries['description'] = desc_var

        def save_changes():
            headers = self.get_headers(write_access=True)
            if not headers: return

            # Construct the full payload as required by the OCL PUT endpoint
            payload = {
                "id": concept_data.get('id'),
                "external_id": concept_data.get('external_id'),
                "concept_class": entries["concept_class"].get(),
                "datatype": entries["datatype"].get(),
                "names": [{
                    "name": entries["display_name"].get(),
                    "locale": "en",
                    "locale_preferred": True,
                    "name_type": "Fully Specified"
                }]
            }
            
            # Add description if it's not empty
            description = entries["description"].get()
            if description:
                payload["descriptions"] = [{"description": description, "locale": "en"}]

            owner_id = self.ocl_org.get()
            source = self.ocl_source.get()
            path_segment = "orgs" if self.owner_type.get() == "Organization" else "users"
            url = f"https://api.openconceptlab.org/{path_segment}/{owner_id}/sources/{source}/concepts/{concept_id}/"

            try:
                response = requests.put(url, headers=headers, data=json.dumps(payload))
                response.raise_for_status()
                messagebox.showinfo("Success", f"Concept '{concept_id}' updated successfully.", parent=dialog)
                dialog.destroy()
                self.load_ocl_concepts() # Refresh the list
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Update Failed", f"Failed to update concept:\n{e}\nResponse: {e.response.text if e.response else 'N/A'}", parent=dialog)

        ttk.Button(dialog, text="Save Changes", command=save_changes).grid(row=len(fields) + 1, column=0, columnspan=2, pady=20)
        dialog.columnconfigure(1, weight=1)

    def delete_selected_concept(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a concept from the list to delete.")
            return

        item_values = self.tree.item(selected_item[0], 'values')
        concept_id = item_values[0]
        concept_name = item_values[1]

        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to permanently delete the concept:\n\nID: {concept_id}\nName: {concept_name}\n\nThis action cannot be undone."):
            return

        headers = self.get_headers(write_access=True)
        if not headers: return

        owner_id = self.ocl_org.get()
        source = self.ocl_source.get()
        path_segment = "orgs" if self.owner_type.get() == "Organization" else "users"
        url = f"https://api.openconceptlab.org/{path_segment}/{owner_id}/sources/{source}/concepts/{concept_id}/"

        try:
            # In OCL, deletion is done by retiring the concept
            payload = {"retired": True}
            response = requests.put(url, headers=headers, data=json.dumps(payload))
            # A 204 No Content is also a success for DELETE-like actions
            if response.status_code not in [200, 201, 204]:
                 response.raise_for_status()
            messagebox.showinfo("Success", f"Concept '{concept_id}' has been retired (deleted).")
            self.load_ocl_concepts() # Refresh the list
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Deletion Failed", f"Failed to delete concept:\n{e}\nResponse: {e.response.text if e.response else 'N/A'}")

    def upload_bulk_from_excel(self):
        """Reads an Excel file and performs a bulk upload to OCL."""
        # Disable button to prevent multiple submissions
        self.upload_button.config(state="disabled")

        # Get only the auth header, requests will set the multipart content type
        auth_header = self.get_headers(write_access=True)
        if not auth_header:
            self.upload_button.config(state="normal")
            return
        headers = {"Authorization": auth_header.get("Authorization", "")}

        file_path = filedialog.askopenfilename(
            title="Select Excel file for OCL Bulk Upload",
            filetypes=[("Excel Files", "*.xlsx")]
        )
        if not file_path:
            self.upload_button.config(state="normal") # Re-enable if cancelled
            return

        try:
            from openpyxl import load_workbook
            wb = load_workbook(filename=file_path)
            ws = wb.active

            header_row = [cell.value for cell in ws[1]]
            required_headers = ["id", "external_id", "concept_class", "datatype", "name"]
            if not all(h in header_row for h in required_headers):
                messagebox.showerror("Invalid Excel", f"Excel file must contain the headers: {', '.join(required_headers)}")
                self.upload_button.config(state="normal")
                return

            concepts_list = []
            owner_id = self.ocl_org.get()
            owner_type = self.owner_type.get()
            source = self.ocl_source.get()

            for row in ws.iter_rows(min_row=2, values_only=True):
                row_data = dict(zip(header_row, row))

                concept_definition = {
                    "type": "Concept",
                    "owner": owner_id,
                    "owner_type": owner_type,
                    "source": source,
                    "id": row_data.get("id"),
                    "external_id": row_data.get("external_id"),
                    "concept_class": row_data.get("concept_class", "Misc"), # Default if blank
                    "datatype": row_data.get("datatype", "N/A"),
                    "retired": False,
                    "names": [{
                        "name": row_data.get("name"),
                        "locale": "en",
                        "locale_preferred": True,
                        "name_type": "Fully Specified"
                    }]
                }
                if row_data.get("description"):
                    concept_definition["descriptions"] = [{"description": row_data.get("description"), "locale": "en"}]

                concepts_list.append(concept_definition)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read or process Excel file:\n{e}")
            self.upload_button.config(state="normal")
            return

        url = "https://api.openconceptlab.org/importers/bulk-import/"
        form_data = {
            "data": "\n".join(json.dumps(obj) for obj in concepts_list),
            "update_if_exists": "true"
        }

        try:
            response = requests.post(url, headers=headers, files=form_data)
            response.raise_for_status()
            result = response.json()
            messagebox.showinfo("Success", f"Bulk import submitted successfully.\nTask ID: {result.get('task')}\nIt may take a few moments to process.")
            self.load_ocl_concepts() # Refresh list after a short delay
        except requests.exceptions.RequestException as e:
            error_message = f"Failed to submit bulk import:\n{e}\nResponse: {e.response.text if e.response else 'N/A'}"
            if e.response and e.response.status_code == 409:
                error_message += "\n\nThis '409 Conflict' error often means a previous import task is still running. Please wait a minute and try again."
            messagebox.showerror("Bulk Upload Failed", error_message)
        finally:
            # Always re-enable the button
            self.upload_button.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = NMRSFormConverter(root)
    root.mainloop()