# NMRS Form Converter

A desktop application for converting OpenMRS HTML forms to JSON and Excel formats, with support for editing, uploading, and downloading forms. Designed for use with the Nigeria Medical Records System (NMRS).

---

## Features

- **Connects to OpenMRS database** to fetch available forms.
- **Displays and edits HTML forms** in a user-friendly interface.
- **Converts HTML forms to JSON** (for OpenMRS 3.x style forms) and Excel.
- **Editable JSON output** with download option.
- **Upload and download HTML forms** for easy modification.
- **Search OpenMRS concepts** and view details.
- **Supports conditional rendering and advanced form logic.**

---

## Requirements

- Python 3.7+
- MySQL database with OpenMRS schema
- The following Python packages:
  - `tkinter` (usually included with Python)
  - `mysql-connector-python`
  - `beautifulsoup4`
  - `openpyxl`

Install dependencies with:

```bash
pip install mysql-connector-python beautifulsoup4 openpyxl
```

---

## Usage

1. **Clone or download this repository.**
2. **Run the application:**

   ```bash
   python NMRSFormConverter.py
   ```

3. **Connect to your OpenMRS database** using the credentials at the top left.
4. **Select a form** from the list to view and edit its HTML.
5. **Edit the HTML** as needed in the center panel.
6. **Convert the displayed HTML** to JSON using the "Convert Displayed HTML to JSON" button.
7. **View and edit the generated JSON** in the right panel.
8. **Download the JSON or HTML** using the provided buttons.
9. **Upload an HTML file** to edit and convert forms not in the database.

---

## Screenshots

*(Add screenshots here if desired)*

---

## File Structure

- NMRSFormConverter.py — Main application code.
- requirements.txt — Python dependencies.
- converted — Output directory for generated JSON and Excel files.

---

## License

MIT License. See LICENSE for details.

---

## Support

For issues or feature requests, please open an issue on the repository or contact the maintainer.

---

**Enjoy using NMRS Form Converter!**
