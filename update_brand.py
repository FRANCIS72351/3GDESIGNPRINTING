import os
import re

ROOT_DIR = "."
ALLOWED_EXTENSIONS = ('.py', '.html', '.css', '.js', '.json', '.txt', '.md', '.yml', '.yaml')
IGNORED_FOLDERS = {'.venv', 'venv', '.git', '__pycache__', 'node_modules', 'instance'}

def run_full_update():
    changes_count = 0
    
    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_FOLDERS]
        
        for filename in filenames:
            if filename.endswith(ALLOWED_EXTENSIONS):
                if filename == "update_brand.py":
                    continue
                    
                file_path = os.path.join(dirpath, filename)
                
                try:
                    content = None
                    for encoding in ('utf-8', 'latin-1'):
                        try:
                            with open(file_path, 'r', encoding=encoding) as f:
                                content = f.read()
                            break
                        except UnicodeDecodeError:
                            continue
                            
                    if content is None:
                        continue
                    
                    original_content = content
                    
                    # 1. Replace standard variations case-insensitively
                    # This targets "3g design", "3G Design", "3G DESIGN" etc.
                    content = re.sub(r'3g\s+design', '3G DESIGN GLOBAL', content, flags=re.IGNORECASE)
                    
                    # 2. Fix cases where "3G" and "DESIGN" might have an HTML tag splitting them 
                    # e.g., <span>3G</span> DESIGN
                    content = re.sub(r'3g\s*(</?[^>]+>)+\s*design', r'3G DESIGN GLOBAL', content, flags=re.IGNORECASE)

                    # If changes were made and it doesn't already say 3G DESIGN GLOBAL redundantly
                    if content != original_content:
                        # Clean up any accidental double "GLOBAL GLOBAL"
                        content = content.replace('3G DESIGN GLOBAL GLOBAL', '3G DESIGN GLOBAL')
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                            
                        print(f"Updated: {file_path}")
                        changes_count += 1
                        
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

    print(f"\nDone! Successfully updated branding in {changes_count} files.")

if __name__ == "__main__":
    run_full_update()