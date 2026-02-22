import os
import json
import tempfile
from typing import Tuple
from datetime import datetime

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
            json.dump(json_value, f, indent=4)

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

def i_flow_path(i_flow_name: str) -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_dir = os.path.join(project_root, "_downloads", "i_flow", f"{i_flow_name}")
    os.makedirs(base_dir, exist_ok=True)
    base_path = os.path.join(base_dir, f"{i_flow_name}")
    os.makedirs(base_path, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # print(f"🐞 ts: {ts}")    

def save_clean_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)



import json
from datetime import datetime

def save_tool_messages(response):
    messages = response.get("messages", [])

    for msg in messages:
        # Check if this is a tool message
        if msg.__class__.__name__ == "ToolMessage":
            
            content = getattr(msg, "content", "{}")

            # Try parsing JSON safely
            try:
                parsed = json.loads(content)
            except:
                parsed = {"raw_content": content}

            # Unique filename using timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"tool_output_{timestamp}.json"

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=4)

            print(f"Saved: {filename}")        

from fpdf import FPDF

def save_to_pdf(text: str, filename: str = "agent_result.pdf"):
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

def save_to_pdf_with_TAD(text: str, filename: str = None):
    if filename is None:
        # Generate timestamp in a filesystem-safe format
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"agent_result_{timestamp}.pdf"
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=11)
    pdf.set_auto_page_break(auto=True, margin=15)
    
    for line in text.splitlines():
        # Safe encoding for special characters
        safe_line = line.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, safe_line)
    
    pdf.output(filename)
    print(f"Saved: {filename}")
    return filename   # optional – can be useful for logging    


################################################################################################################################################    
def extract_clean_content(messages) -> str:
    """
    Turns list of messages into nice readable text for PDF
    Filters out noise, adds clear labels
    """
    lines = []
    lines.append("═══════════════════════════════════════════════")
    lines.append("             AGENT CONVERSATION LOG")
    lines.append("═══════════════════════════════════════════════\n")

    for msg in messages:
        msg_type = type(msg).__name__
        content = getattr(msg, "content", None) or ""

        # Skip empty or very internal messages
        if not content or content.strip() == "":
            continue

        if "AIMessage" in msg_type:
            prefix = "🤖 Agent:"
            if getattr(msg, "tool_calls", None):
                prefix = "🤖 Agent (planning tool calls):"
            lines.append(f"{prefix}\n{content.strip()}\n")

        elif "ToolMessage" in msg_type or "FunctionMessage" in msg_type:
            tool_name = getattr(msg, "name", "tool") or "tool"
            lines.append(f"🛠️  {tool_name} result:")
            lines.append(content.strip())
            lines.append("")  # empty line after tool output

        elif "HumanMessage" in msg_type:
            # optional – comment out if you don't want to see user input again
            lines.append(f"👤 You:")
            lines.append(content.strip())
            lines.append("")

        else:
            # Other messages (SystemMessage, ChatMessage, etc.) – usually skip
            continue

        lines.append("─" * 60)

    lines.append("\nFinal Answer Summary:")
    # Usually the last AIMessage is the final one
    if messages and "AIMessage" in type(messages[-1]).__name__:
        final = messages[-1].content.strip()
        lines.append(final)

    return "\n".join(lines)


def save_clean_pdf(messages_or_result, filename=None):
    # 1. Get messages list
    if isinstance(messages_or_result, dict):
        messages = messages_or_result.get("messages", [])
    elif hasattr(messages_or_result, "messages"):  # sometimes it's an object
        messages = messages_or_result.messages
    elif isinstance(messages_or_result, list):
        messages = messages_or_result
    else:
        messages = []

    if not messages:
        text = str(messages_or_result)  # fallback
    else:
        text = extract_clean_content(messages)

    # 2. Generate filename if not given
    if filename is None:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"agent_run_{ts}.pdf"

    # 3. Create PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=10)        # monospaced → good alignment
    pdf.set_auto_page_break(auto=True, margin=12)

    for line in text.splitlines():
        # Handle encoding safely
        safe_line = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 5.5, safe_line)

    pdf.output(filename)
    print(f"Saved clean PDF → {filename}")