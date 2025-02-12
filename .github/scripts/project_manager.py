import os
import json
import google.generativeai as genai
from pathlib import Path
import re
import logging
import subprocess
import traceback
from datetime import datetime
import html.parser
import cssutils
import esprima

class ProjectManager:
    def __init__(self):
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        self.project_root = Path('.')
        self.requirements_file = self.project_root / 'project_requirements.txt'
        
        # Setup logging
        self.setup_logging()
        
        # Initialize error checkers
        cssutils.log.setLevel(logging.CRITICAL)  # Suppress cssutils warnings
        self.html_parser = html.parser.HTMLParser()

    def read_requirements(self):
        """Read and parse project requirements from the requirements file."""
        try:
            if not self.requirements_file.exists():
                logging.warning(f"Requirements file not found at {self.requirements_file}")
                return []
                
            with open(self.requirements_file, 'r') as f:
                # Read lines and filter out empty ones
                requirements = [line.strip() for line in f.readlines() if line.strip()]
                
            if not requirements:
                logging.warning("Requirements file is empty")
                return []
                
            logging.info(f"Read {len(requirements)} requirements")
            return requirements
                
        except Exception as e:
            logging.error(f"Error reading requirements: {str(e)}")
            return []

    def check_implementation(self, requirement):
        """Check if a requirement is implemented by analyzing existing files."""
        try:
            files_to_check = {
                'html': self.project_root / 'index.html',
                'css': self.project_root / 'styles.css',
                'js': self.project_root / 'script.js'
            }
            
            # Get content from all existing files
            content = ''
            for file_path in files_to_check.values():
                if file_path.exists():
                    try:
                        with open(file_path, 'r') as f:
                            content += f'\n' + f.read()
                    except Exception as e:
                        logging.error(f"Error reading {file_path}: {str(e)}")
            
            if not content.strip():
                return False
                
            # Ask Gemini to check implementation
            prompt = f"""
            Analyze if this requirement is implemented in the provided code:
            
            Requirement: {requirement}
            
            Code:
            {content}
            
            Respond with only 'YES' or 'NO'.
            """
            
            response = self.model.generate_content(prompt)
            return response.text.strip().upper() == 'YES'
            
        except Exception as e:
            logging.error(f"Error checking implementation: {str(e)}")
            return False

    def setup_logging(self):
        """Setup logging configuration"""
        logs_dir = self.project_root / 'logs'
        logs_dir.mkdir(exist_ok=True)
        
        log_file = logs_dir / f'project_manager_{datetime.now().strftime("%Y%m%d")}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def check_html_errors(self, content):
        """Check HTML for syntax errors"""
        try:
            self.html_parser.feed(content)
            return None
        except Exception as e:
            return str(e)

    def check_css_errors(self, content):
        """Check CSS for syntax errors"""
        try:
            cssutils.parseString(content)
            return None
        except Exception as e:
            return str(e)

    def check_js_errors(self, content):
        """Check JavaScript for syntax errors"""
        try:
            esprima.parseScript(content)
            return None
        except Exception as e:
            return str(e)

    def fix_code_error(self, code, error, language):
        """Use Gemini to fix code errors"""
        prompt = f"""
        Fix the following {language} code that has this error:
        Error: {error}
        
        Code:
        {code}
        
        Provide only the fixed code without any explanations.
        """
        
        try:
            response = self.model.generate_content(prompt)
            fixed_code = response.text.strip()
            
            # Verify the fix worked
            if language == 'HTML':
                new_error = self.check_html_errors(fixed_code)
            elif language == 'CSS':
                new_error = self.check_css_errors(fixed_code)
            elif language == 'JavaScript':
                new_error = self.check_js_errors(fixed_code)
                
            if new_error:
                logging.error(f"Fix attempt failed. New error: {new_error}")
                return None
                
            return fixed_code
            
        except Exception as e:
            logging.error(f"Error during fix attempt: {str(e)}")
            return None
        
    def check_and_fix_file(self, file_path):
        """Check a file for errors and fix if necessary"""
        with open(file_path, 'r') as f:
            content = f.read()
            
        file_type = file_path.suffix.lower()
        error = None
        
        if file_type == '.html':
            error = self.check_html_errors(content)
            language = 'HTML'
        elif file_type == '.css':
            error = self.check_css_errors(content)
            language = 'CSS'
        elif file_type == '.js':
            error = self.check_js_errors(content)
            language = 'JavaScript'
        else:
            return
            
        if error:
            logging.warning(f"Found error in {file_path}: {error}")
            fixed_code = self.fix_code_error(content, error, language)
            
            if fixed_code:
                # Backup original file
                backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
                with open(backup_path, 'w') as f:
                    f.write(content)
                    
                # Write fixed code
                with open(file_path, 'w') as f:
                    f.write(fixed_code)
                    
                logging.info(f"Fixed error in {file_path}. Original backed up to {backup_path}")
                
                # Log the fix details
                self.log_fix(file_path, error, content, fixed_code)
                
    def log_fix(self, file_path, error, original_code, fixed_code):
        """Log details of code fixes"""
        fixes_log_dir = self.project_root / 'logs' / 'fixes'
        fixes_log_dir.mkdir(exist_ok=True)
        
        log_file = fixes_log_dir / f'fix_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{file_path.name}.log'
        
        with open(log_file, 'w') as f:
            f.write(f"File: {file_path}\n")
            f.write(f"Error: {error}\n")
            f.write("\nOriginal Code:\n")
            f.write(original_code)
            f.write("\n\nFixed Code:\n")
            f.write(fixed_code)

    def _update_file(self, filename, content):
        """Update or create a file with new content."""
        try:
            file_path = self.project_root / filename
            
            # Create file if it doesn't exist
            if not file_path.exists():
                file_path.touch()
                
            # Read existing content
            existing_content = ''
            if file_path.stat().st_size > 0:
                with open(file_path, 'r') as f:
                    existing_content = f.read()
            
            # Append new content if it's not already there
            if content.strip() not in existing_content:
                with open(file_path, 'a') as f:
                    f.write('\n' + content)
                    
            logging.info(f"Updated {filename}")
            
        except Exception as e:
            logging.error(f"Error updating {filename}: {str(e)}")

    def _update_readme(self, requirement, description):
        """Update README.md with new implementation details."""
        try:
            readme_path = self.project_root / 'README.md'
            
            # Create README if it doesn't exist
            if not readme_path.exists():
                content = "# Auto-Generated Project\n\n## Implemented Features\n\n"
            else:
                with open(readme_path, 'r') as f:
                    content = f.read()

            # Add new feature section if not present
            if "## Implemented Features" not in content:
                content += "\n## Implemented Features\n\n"
            
            # Add new feature
            feature_entry = f"### {requirement}\n{description}\n\n"
            if feature_entry not in content:
                content += feature_entry
                
            with open(readme_path, 'w') as f:
                f.write(content)
                
            logging.info("Updated README.md")
            
        except Exception as e:
            logging.error(f"Error updating README: {str(e)}")

    def implement_requirement(self, requirement):
        """Implement a new requirement using Gemini."""
        prompt = f"""
        Implement the following requirement for a web project:
        {requirement}
        
        Provide the necessary HTML, CSS, and JavaScript code.
        Format the response as JSON with the following structure:
        {{
            "html": "code here",
            "css": "code here",
            "js": "code here",
            "description": "feature description"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            # Log the full response structure for debugging
            logging.info(f"Raw API Response: {response}")
            
            try:
                # Extract text content properly from the response
                raw_text = response.candidates[0].content.parts[0].text.strip()
            
                # Strip triple-backtick formatting if present
                clean_text = raw_text.strip("```json").strip("```")
            
                # Parse JSON safely
                implementation = json.loads(clean_text)
            
            except json.JSONDecodeError as e:
                logging.error(f"JSON Parsing Failed! Error: {e}, Response: {raw_text}")
                raise  # Re-raise for debugging
            except AttributeError as e:
                logging.error(f"Unexpected Response Format! Error: {e}, Response: {response}")
                raise  # Re-raise for debugging
            
            # Update files
            if implementation.get('html'):
                self._update_file('index.html', implementation['html'])
            if implementation.get('css'):
                self._update_file('styles.css', implementation['css'])
            if implementation.get('js'):
                self._update_file('script.js', implementation['js'])
            
            # Check for errors in updated files
            for file_name in ['index.html', 'styles.css', 'script.js']:
                file_path = self.project_root / file_name
                if file_path.exists():
                    self.check_and_fix_file(file_path)
            
            # Update README
            self._update_readme(requirement, implementation['description'])
            
        except Exception as e:
            logging.error(f"Error implementing requirement: {str(e)}\n{traceback.format_exc()}")

    def run(self):
        """Main execution method."""
        logging.info("Starting project manager run")
        
        try:
            requirements = self.read_requirements()
            
            for requirement in requirements:
                logging.info(f"Processing requirement: {requirement}")
                if not self.check_implementation(requirement):
                    logging.info(f"Implementing requirement: {requirement}")
                    self.implement_requirement(requirement)
                else:
                    logging.info(f"Requirement already implemented: {requirement}")
            
            # Check all existing files for errors
            for file_type in ['.html', '.css', '.js']:
                for file_path in self.project_root.rglob(f'*{file_type}'):
                    self.check_and_fix_file(file_path)
                    
        except Exception as e:
            logging.error(f"Error in main execution: {str(e)}\n{traceback.format_exc()}")
        
        logging.info("Completed project manager run")

if __name__ == "__main__":
    manager = ProjectManager()
    manager.run()
