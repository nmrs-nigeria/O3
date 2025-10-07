# Installation Guide for NMRS Form Converter

Follow these steps to install and run the NMRS Form Converter application.

---

## 1. Prerequisites

- **Python 3.7 or higher**  
  Download from [python.org](https://www.python.org/downloads/).

- **MySQL Server**  
  Required for connecting to your OpenMRS database.

---

## 2. Clone or Download the Repository

```bash
git clone https://github.com/yourusername/NMRSFormConverter.git
cd NMRSFormConverter
```
Or download and extract the ZIP file.

---

## 3. Install Python Dependencies

Install required packages using pip:

```bash
pip install mysql-connector-python beautifulsoup4 openpyxl
```

---

## 4. Configure Database Access

- Ensure you have access to your OpenMRS MySQL database.
- You will enter your database credentials in the app UI when you start the program.

---

## 5. Run the Application

```bash
python NMRSFormConverter.py
```

---

## 6. Usage

- Connect to your database using the credentials panel.
- Select a form from the list to view and edit its HTML.
- Use the buttons to upload, download, or convert forms as needed.
- See the [README.md](README.md) for more details.

---

## Troubleshooting

- **Tkinter not found:**  
  Tkinter is included with most Python installations. If missing, install it via your OS package manager (e.g., `sudo apt-get install python3-tk` on Ubuntu).
- **MySQL connection errors:**  
  Ensure your credentials are correct and the database server is running.
- **Other issues:**  
  Open an issue on the repository or contact the maintainer.

---