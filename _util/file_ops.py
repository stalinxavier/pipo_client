import os
import json
import tempfile
from typing import Tuple
from datetime import datetime
from fpdf import FPDF

def prepare_output_dir(cf_repo_prefix : str) -> str:
    try:
        cf_repo = tempfile.mkdtemp(prefix = cf_repo_prefix)
    
    except Exception as e:
        print(f"Exception in prepare_output_dir function: {e}")
        cf_repo = ""
    
    finally:
        return cf_repo

def write_json(json_value, json_file_name):
    try:
        base_dir = os.getcwd()
        temp_dir = os.path.join(base_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        json_path = os.path.join(temp_dir, json_file_name)
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_value, f, indent=4, ensure_ascii=False)

    except Exception as e:
        print(f"Exception in write_json function: {e}")

    finally:
        pass

def gather_repo_files(neo_repo: str, max_chars: bool = True) -> Tuple[list, dict]:
    try:
        filenames = []
        snippets = {}
        exclude_dirs = [".git", "node_modules", "__pycache__", ".venv", ".idea"]
        exclude_files = [".jar"]

        for root, dirs, files in os.walk(neo_repo):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if any(f.endswith(ext) for ext in exclude_files):
                    continue

                rel_path = os.path.relpath(os.path.join(root, f), neo_repo)
                filenames.append(rel_path)
                try:
                    if max_chars == True:
                        snippets[rel_path] = read_text_file(rel_path = os.path.join(root, f))[:2000]
                    
                    else:    
                        snippets[rel_path] = read_text_file(rel_path = os.path.join(root, f))
                    
                except Exception as e:
                    print(f"Exception reading file {rel_path}: {e}")
                    snippets[rel_path] = "<unreadable>"
                    
        json_value = {"filenames": filenames, "snippets": snippets}
        write_json(json_value = json_value, json_file_name = "gather_repo_files.json")
        
    except Exception as e:
        print(f"Exception in gather_repo_files function: {e}")
        filenames = []
        snippets = {}    
    
    finally:
        print(f"filenames count: {len(filenames)}, snippets count: {len(snippets)}")
        return filenames, snippets

def read_text_file(rel_path: str) -> str:
    try:
        with open(rel_path, "r", encoding="utf-8", errors="ignore") as f:
            read_file = f.read()
        
    except Exception as e:
        print(f"Exception in read_text_file function: {e}")
        read_file = ""
    
    finally:
        return read_file

def write_text_file(dest_path: str, content: str) -> None:
    try:
        with open(dest_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(content)
            
    except Exception as e:
        print(f"Exception in write_text_file function: {e}")
        
    finally:
        pass

def write_txt(txt_value, txt_file_name):
    try:
        base_dir = os.getcwd()
        temp_dir = os.path.join(base_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        txt_path = os.path.join(temp_dir, txt_file_name)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_value)

    except Exception as e:
        print(f"Exception in write_txt function: {e}")

    finally:
        pass

def save_to_pdf(text: str, filename: str):
    pdf = FPDF()
    pdf.add_page()
    
    # Use a monospaced font → better for code / structured output
    pdf.set_font("Courier", size=11)
    
    # Optional: smaller margin, better line spacing
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Split text into lines and add them
    for line in text.splitlines():
        # FPDF's cell() doesn't wrap automatically → we use multi_cell
        pdf.multi_cell(0, 6, line.encode('latin-1', 'replace').decode('latin-1'))
        # or just: pdf.multi_cell(0, 6, line)  # but sometimes encoding issues
    
    pdf.output(filename)
    print(f"Saved PDF: {filename}")            

def pdf_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_dir = os.path.join(project_root, "_downloads")
    os.makedirs(base_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    print(f"🐞 ts: {ts}")

    dest_path = os.path.join(base_dir, f"agent_result_{ts}.pdf")
    return os.path.normpath(dest_path)