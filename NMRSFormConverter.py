import tkinter as tk
from tkinter import ttk, Listbox, Text, END, VERTICAL, messagebox
import mysql.connector
from bs4 import BeautifulSoup
from openpyxl import Workbook
import json
import os
import re
import uuid

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
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        # DB Connection Frame
        self.db_frame = ttk.LabelFrame(root, text="Database Connection")
        self.db_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self._add_db_widgets()

        # Concept Search Frame
        self.concept_frame = ttk.LabelFrame(root, text="Concept Search/Info")
        self.concept_frame.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self._add_concept_widgets()

        # Forms List Frame (left)
        self.forms_frame = ttk.LabelFrame(root, text="Available Forms")
        self.forms_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.forms_frame.columnconfigure(0, weight=1)
        self.forms_frame.rowconfigure(1, weight=1)

        self.convert_btn = ttk.Button(self.forms_frame, text="Convert Selected Form", command=self.convert_selected_form)
        self.convert_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.forms_listbox = Listbox(self.forms_frame, width=60)
        self.forms_listbox.grid(row=1, column=0, sticky="nsew")
        self.forms_scrollbar = ttk.Scrollbar(self.forms_frame, orient=VERTICAL, command=self.forms_listbox.yview)
        self.forms_scrollbar.grid(row=1, column=1, sticky="ns")
        self.forms_listbox.config(yscrollcommand=self.forms_scrollbar.set)
        self.forms_listbox.bind('<<ListboxSelect>>', self.on_form_select)

        # XML Data Display Frame (right)
        self.xml_frame = ttk.LabelFrame(root, text="Form XML (xml_data)")
        self.xml_frame.grid(row=1, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        self.xml_frame.rowconfigure(0, weight=1)
        self.xml_frame.columnconfigure(0, weight=1)

        # Add Download HTML button above the HTML form display box
        self.download_html_btn = ttk.Button(self.xml_frame, text="Download HTML", command=self.download_html)
        self.download_html_btn.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 2))
        # Move the text widget and scrollbar down by one row
        self.xml_text = Text(self.xml_frame, wrap="none")
        self.xml_text.grid(row=1, column=0, sticky="nsew")
        self.xml_scrollbar = ttk.Scrollbar(self.xml_frame, orient=VERTICAL, command=self.xml_text.yview)
        self.xml_scrollbar.grid(row=1, column=1, sticky="ns")
        self.xml_text.config(yscrollcommand=self.xml_scrollbar.set)

        # Optional: Add right-click context menu for copy/paste
        def show_context_menu(event):
            context_menu.tk_popup(event.x_root, event.y_root)

        context_menu = tk.Menu(self.xml_text, tearoff=0)
        context_menu.add_command(label="Copy", command=lambda: self.xml_text.event_generate("<<Copy>>"))
        context_menu.add_command(label="Paste", command=lambda: self.xml_text.event_generate("<<Paste>>"))
        context_menu.add_command(label="Cut", command=lambda: self.xml_text.event_generate("<<Cut>>"))

        self.xml_text.bind("<Button-3>", show_context_menu)  # Right-click menu

        # --- FIX: Always allow editing and copying ---
        # Make sure the Text widget is always in normal state for selection/copy
        self.xml_text.config(state="normal")

        # Add Ctrl+A support for select all
        def select_all(event):
            self.xml_text.tag_add("sel", "1.0", "end-1c")
            return "break"
        self.xml_text.bind("<Control-a>", select_all)
        self.xml_text.bind("<Control-A>", select_all)

        # Add single left click to focus the widget (so Ctrl+A works after click)
        self.xml_text.bind("<Button-1>", lambda e: self.xml_text.focus_set())

        self.connection = None
        self.concept_map = {}      # {concept_id: {"uuid": ..., "name": ...}}
        self.concept_datatypes = {}  # {concept_id: datatype}
        self.concept_numeric = {}   # {concept_id: {"hi_absolute": ..., "low_absolute": ...}}
        self.forms = []
        self.selected_form_index = None
        self.option_sets = {}
        self.concept_answers = {}  # {concept_id: [{"label": ..., "uuid": ...}, ...]}

        self.connect_to_db(auto=True)

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
        self.concept_search_entry.bind("<Return>", self.on_concept_search)
        self.concept_search_btn = ttk.Button(self.concept_frame, text="Search", command=self.on_concept_search)
        self.concept_search_btn.grid(row=0, column=1, padx=5, pady=5)
        self.concept_info_text = Text(self.concept_frame, height=10, width=70, wrap="word")
        self.concept_info_text.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        self.concept_info_text.config(state="disabled")

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
        cursor = self.connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT h.form_id, f.name 
            FROM htmlformentry_html_form h
            JOIN form f ON h.form_id = f.form_id
        """)
        self.forms = cursor.fetchall()
        self.forms_listbox.delete(0, END)
        for form in self.forms:
            self.forms_listbox.insert(END, f"{form['form_id']}: {form['name']}")
        cursor.close()

    def on_form_select(self, event):
        selection = event.widget.curselection()
        if not selection:
            self.selected_form_index = None
            self.xml_text.config(state="normal")
            self.xml_text.delete(1.0, END)
            return
        self.selected_form_index = selection[0]
        form = self.forms[self.selected_form_index]
        xml_data = self.fetch_form_html(form['form_id'])
        self.xml_text.config(state="normal")      # Enable editing/selecting
        self.xml_text.delete(1.0, END)
        self.xml_text.insert(END, xml_data if xml_data else "(No xml_data found)")
        # Do NOT set state="disabled" here!

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
        self.generate_outputs(soup, form['name'])

    def fetch_form_html(self, form_id):
        cursor = self.connection.cursor(dictionary=True)
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
        cursor = self.connection.cursor(dictionary=True)
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
        cursor.close()

    def on_concept_search(self, event=None):
        search = self.concept_search_var.get().strip()
        self.concept_info_text.config(state="normal")
        self.concept_info_text.delete(1.0, END)
        if not search:
            self.concept_info_text.config(state="disabled")
            return
        cursor = self.connection.cursor(dictionary=True)
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
        self.concept_info_text.config(state="disabled")

    def generate_outputs(self, soup, form_name):
        form_uuid = str(uuid.uuid4())
        json_form = {
            "name": form_name,
            "uuid": form_uuid,
            "processor": "EncounterFormProcessor",
            "version": "1.0",
            "description": "",
            "pages": []
        }
        wb = Workbook()
        ws = wb.active
        ws.title = "Form"
        ws.append([
            "Page", "Section", "Question", "Datatype", "Mandatory", "Question ID",
            "External ID", "Rendering", "OptionSet name", "Upper limit", "Lower limit"
        ])
        option_sets = {}

        fieldsets = soup.find_all("fieldset")
        if not fieldsets:
            fieldsets = [soup]

        id_counter = 1  # <-- Use this for incremental numbering

        htmlid_to_qid = {}     # Maps HTML ids to generated question ids
        cid_to_qid = {}        # Maps concept IDs to generated question ids
        qid_to_question = {}   # Maps generated question ids to question objects

        for fieldset in fieldsets:
            legend = fieldset.find("legend")
            section_label = legend.text.strip() if legend else None

            obs_tags = fieldset.find_all("obs")
            if not obs_tags:
                continue

            page_label = section_label or self.concept_map.get(
                int(obs_tags[0].get("conceptid", "0")), {}).get("name", "Page")

            first_obs_cid = obs_tags[0].get("conceptid")
            section_label_final = section_label or (
                self.concept_map.get(int(first_obs_cid), {}).get("name", "Section")
                if first_obs_cid and first_obs_cid.isdigit() else "Section"
            )

            section = {
                "label": section_label_final,
                "questions": []
            }

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
                qid = f"{base_id}_{id_counter}"

                # --- DO NOT REPEAT ANY QUESTION ---
                if qid in seen_questions:
                    continue
                seen_questions.add(qid)
                id_counter += 1

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
                    section["questions"].append(question)
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
                    section["questions"].append(question)
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
                    section["questions"].append(question)
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
                    section["questions"].append(question)
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
                            section["questions"].append(question)
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
                            section["questions"].append(question)
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
                            section["questions"].append(question)
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

                if datatype == "date":
                    rendering = "date"
                    question_options["allowFutureDates"] = False
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
                    section["questions"].append(question)
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

                section["questions"].append(question)
                ws.append([
                    page_label, section_label_final, label, datatype.capitalize() if datatype else "Text", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                    "", rendering, "", question_options.get("max", ""), question_options.get("min", "")
                ])

            if section["questions"]:
                json_form["pages"].append({
                    "label": page_label,
                    "sections": [section]
                })

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
                        
                        # Get UUID for trigger value
                        if trigger_value.isdigit():
                            trigger_uuid = f"{trigger_value}AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
                        
                        target_id = when.get("thendisplay").lstrip("#")
                        target_elem = soup.find(id=target_id)
                        
                        print(f"Processing control: {controlling_id} -> {target_id}")
                        
                        if controlling_qid and target_elem:
                            # Find all obs inside target container
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
                
                toggle_target = obs.get("toggle")  # e.g., "CD4LFA"
                print(f"Processing toggle: checkbox concept {controlling_cid} -> {toggle_target}")
                
                # Find the target container by ID
                target_elem = soup.find(id=toggle_target)
                if controlling_qid and target_elem:
                    # Find all obs inside the target container
                    for child_obs in target_elem.find_all("obs"):
                        child_cid = child_obs.get("conceptid")
                        if child_cid:
                            # Find corresponding question in the JSON and add hide expression
                            if child_cid in cid_to_qid:
                                child_qid = cid_to_qid[child_cid]
                                for page in json_form["pages"]:
                                    for section in page["sections"]:
                                        for question in section["questions"]:
                                            if question["id"] == child_qid:
                                                print(f"Adding hide to question {child_qid} controlled by {controlling_qid}")
                                                question["hide"] = {
                                                    "hideWhenExpression": f"!{controlling_qid}"
                                                }

        # --- OptionSets Sheet ---
        ws2 = wb.create_sheet("OptionSets")
        ws2.append(["OptionSet name", "Answers", "External ID"])
        for opt_name, values in option_sets.items():
            for ans, extid in values:
                ws2.append([opt_name, ans, extid])

        # --- Save ---
        output_dir = os.path.join(os.getcwd(), "converted")
        os.makedirs(output_dir, exist_ok=True)
        excel_path = os.path.join(output_dir, f"{form_name}_converted.xlsx")
        json_path = os.path.join(output_dir, f"{form_name}_converted.json")
        wb.save(excel_path)
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(json_form, jf, indent=2)
        messagebox.showinfo("Done", f"Files generated in {output_dir}")

    def download_html(self):
        # Save the current HTML/XML in the display box to a file
        html_content = self.xml_text.get("1.0", END).strip()
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

if __name__ == "__main__":
    root = tk.Tk()
    app = NMRSFormConverter(root)
    root.mainloop()