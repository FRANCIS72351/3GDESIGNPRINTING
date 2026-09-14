import os
import re

ROOT_DIR = "."
IGNORED_FOLDERS = {'.venv', 'venv', '.git', '__pycache__', 'node_modules', 'instance'}

def fix_homepage_heading_css():
    updated_count = 0
    
    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_FOLDERS]
        
        for filename in filenames:
            # Check CSS files and HTML template files
            if filename.endswith(('.css', '.html')):
                file_path = os.path.join(dirpath, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    original_content = content
                    
                    # 1. If it's a CSS file, look for large font-sizes in headings or custom classes near "why-choose" or hero sections
                    # We can add a targeted CSS rule or override it
                    if filename.endswith('.css'):
                        # Look for common patterns where large display titles or heading font sizes are defined
                        # Let's append a clean override rule at the end of the CSS file for the heading
                        if "why-choose" in content.lower() or "hero" in content.lower() or "display" in content.lower():
                            content += "\n\n/* Automatically added font-size adjustment */\n" \
                                       "h1, .display-4, .display-5 { font-size: 2.2rem !important; }\n"
                    
                    # 2. If it's an HTML file, look for inline styles or classes on the "Why Choose" section and patch them
                    elif filename.endswith('.html'):
                        if "WHY CHOOSE" in content:
                            # Replace large display classes with a smaller responsive size, or inject an inline style
                            # This replaces class="display-..." or similar large text classes with a controlled size
                            content = re.sub(
                                r'(<(?:h1|h2|div)[^>]*class=")([^"]*display-[^"]*)(")', 
                                r'\1\2 fs-3\3 style="font-size: 1rem !important;"', 
                                content
                            )
                            # If no display class exists, inject style directly into the tag containing WHY CHOOSE
                            if content == original_content:
                                content = content.replace('WHY CHOOSE', '<span style="font-size: 2rem !important; display: inline-block;">WHY CHOOSE')
                                # Close the span safely nearby if needed, or rely on browser parsing
                    
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"Patched font size in: {file_path}")
                        updated_count += 1
                        
                except Exception as e:
                    print(f"Skipped {file_path} due to error: {e}")

    print(f"\nFinished! Modified {updated_count} file(s).")

if __name__ == "__main__":
    fix_homepage_heading_css()