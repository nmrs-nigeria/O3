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
        self.xml_text = Text(self.xml_frame, wrap="none")
        self.xml_text.grid(row=0, column=0, sticky="nsew")
        self.xml_scrollbar = ttk.Scrollbar(self.xml_frame, orient=VERTICAL, command=self.xml_text.yview)
        self.xml_scrollbar.grid(row=0, column=1, sticky="ns")
        self.xml_text.config(yscrollcommand=self.xml_scrollbar.set)
        self.xml_text.config(state="disabled")

        self.connection = None
        self.concept_map = {}      # {concept_id: {"uuid": ..., "name": ...}}
        self.concept_datatypes = {}  # {concept_id: datatype}
        self.concept_numeric = {}   # {concept_id: {"hi_absolute": ..., "low_absolute": ...}}
        self.forms = []
        self.selected_form_index = None
        self.option_sets = {}

        self.connect_to_db(auto=True)

    def _add_db_widgets(self):
        labels = ["Host", "User", "Password", "Database"]
        self.db_entries = {}
        defaults = {"host": "localhost", "user": "root", "password": "root", "database": "openmrs"}
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
            self.xml_text.config(state="disabled")
            return
        self.selected_form_index = selection[0]
        form = self.forms[self.selected_form_index]
        xml_data = self.fetch_form_html(form['form_id'])
        self.xml_text.config(state="normal")
        self.xml_text.delete(1.0, END)
        self.xml_text.insert(END, xml_data if xml_data else "(No xml_data found)")
        self.xml_text.config(state="disabled")

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

                # --- PRIORITY: Handle answerConceptIds as select ---
                answer_concept_ids = obs.get("answerconceptids")
                answer_labels = obs.get("answerlabels")
                if answer_concept_ids:
                    # Split ids and labels, strip whitespace
                    ids = [x.strip() for x in answer_concept_ids.split(",")]
                    labels = [x.strip() for x in answer_labels.split(",")] if answer_labels else ids
                    answers = []
                    for i, cid_val in enumerate(ids):
                        # Use the uuid for each answer concept if available, else fallback to the id itself
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

        # --- Handle components not within any fieldset ---
        # Find all obs, encounterProvider, encounterLocation, encounterDate not inside a fieldset
        all_tags = soup.find_all(["obs", "encounterprovider", "encounterlocation", "encounterdate"])
        fieldset_obs = set()
        for fs in fieldsets:
            for tag in fs.find_all(["obs", "encounterprovider", "encounterlocation", "encounterdate"]):
                fieldset_obs.add(tag)

        # Only process tags not already handled in fieldsets
        outside_tags = [tag for tag in all_tags if tag not in fieldset_obs]
        if outside_tags:
            section = {
                "label": "General",
                "questions": []
            }
            page_label = "General"
            section_label_final = "General"
            seen_questions = set()
            used_labels = {}

            for obs in outside_tags:
                # --- Handle encounterProvider/person and encounterLocation ---
                is_person = obs.get("style", "").lower() == "person" or obs.name.lower() == "encounterprovider"
                is_location = obs.name.lower() == "encounterlocation"
                is_date = obs.name.lower() == "encounterdate"

                # Generate a label and id
                if is_date:
                    label = "Visit Date"
                    base_id = "encounterDate"
                else:
                    cid = obs.get("conceptid")
                    if cid and cid.isdigit():
                        cid = int(cid)
                        label = obs.get("label", "") or self.concept_map.get(cid, {"name": f"Concept {cid}"})["name"]
                        base_id = to_camel_case_id(label)
                    else:
                        label = obs.get("label", "") or obs.name
                        base_id = to_camel_case_id(label)
                qid = f"{base_id}_{id_counter}"

                if qid in seen_questions:
                    continue
                seen_questions.add(qid)
                id_counter += 1

                if is_person:
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

                if is_location:
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

                if is_date:
                    question = {
                        "id": qid,
                        "label": label,
                        "type": "encounterDate",
                        "required": obs.get("required", "false").lower() == "true",
                        "questionOptions": {
                            "rendering": "date",
                            "allowFutureDates": obs.get("allowfuturedates", "false").lower() == "true",
                            "showTime": obs.get("showtime", "false").lower() == "true"
                        }
                    }
                    section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Date", "Yes" if obs.get("required", "false").lower() == "true" else "No", qid,
                        "", "date", "", "", ""
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
                            "concept": self.concept_map.get(cid, {}).get("uuid", ""),
                            "rendering": "radio",
                            "answers": [
                                {
                                    "label": label,
                                    "concept": self.concept_map.get(cid, {}).get("uuid", "")
                                }
                            ]
                        }
                    }
                    if default_val:
                        question["default"] = self.concept_map.get(cid, {}).get("uuid", "")  # Set default to the single answer option's uuid
                    section["questions"].append(question)
                    ws.append([
                        page_label, section_label_final, label, "Radio", "No", qid,
                        "", "radio", "", "", ""
                    ])
                    continue

                # --- PRIORITY: Handle answerConceptIds as select ---
                answer_concept_ids = obs.get("answerconceptids")
                answer_labels = obs.get("answerlabels")
                if answer_concept_ids:
                    # Split ids and labels, strip whitespace
                    ids = [x.strip() for x in answer_concept_ids.split(",")]
                    labels = [x.strip() for x in answer_labels.split(",")] if answer_labels else ids
                    answers = []
                    for i, cid_val in enumerate(ids):
                        # Use the uuid for each answer concept if available, else fallback to the id itself
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
                            "concept": self.concept_map.get(cid, {}).get("uuid", ""),
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

                # --- Datatype-based rendering for obs ---
                cid = obs.get("conceptid")
                if not cid or not cid.isdigit():
                    continue
                cid = int(cid)
                datatype = self.concept_datatypes.get(cid, "").lower()
                rendering = "text"
                question_options = {
                    "concept": self.concept_map.get(cid, {}).get("uuid", "")
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
                elif obs.get("answerlabel"):
                    answer_label = obs.get("answerlabel")
                    answer_concept_id = obs.get("answerconceptid")
                    question = {
                        "id": qid,
                        "label": answer_label,
                        "type": "radio",
                        "questionOptions": {
                            "concept": self.concept_map.get(cid, {}).get("uuid", ""),
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

if __name__ == "__main__":
    root = tk.Tk()
    app = NMRSFormConverter(root)
    root.mainloop()